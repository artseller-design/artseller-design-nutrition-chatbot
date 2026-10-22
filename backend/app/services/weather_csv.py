"""CSV weather ingestion shared by the API and the scheduled importer."""

import asyncio
import logging
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

from app.config import settings
from app.firebase import get_firestore

logger = logging.getLogger(__name__)
KST = timezone(timedelta(hours=9), "KST")


def normalize_weather_rows(rows: list[dict]) -> list[dict]:
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["date"], []).append(row)
    daily = []
    for day, values in sorted(grouped.items()):
        humidities = [item["humidity_percent"] for item in values if item["humidity_percent"] is not None]
        daily.append({
            "date": day,
            "temperature_c": round(sum(item["temperature_c"] for item in values) / len(values), 2),
            "precipitation_mm": max((item["precipitation_mm"] for item in values if item["precipitation_mm"] is not None), default=None),
            "humidity_percent": round(sum(humidities) / len(humidities), 2) if humidities else None,
            "duplicate_count": len(values) - 1,
            "city": values[0]["city"],
            "station_id": values[0]["station_id"],
            "source": "uploaded_weather_csv",
        })
    return daily


def _parse_csv(csv_text: str) -> list[dict]:
    # Import lazily to avoid a router/service import cycle during app startup.
    from app.routers.weather import _parse_weather_csv

    return _parse_weather_csv(csv_text)


def save_weather_rows(user_id: str, rows: list[dict]) -> list[dict]:
    db = get_firestore()
    if db is None:
        raise RuntimeError("Firestore에 연결되지 않았습니다.")
    daily = normalize_weather_rows(rows)
    collection = db.collection("users").document(user_id).collection("weather_logs")
    # Firestore batches are limited to 500 operations; keep a safety margin.
    for offset in range(0, len(daily), 400):
        batch = db.batch()
        sync_time = datetime.now(timezone.utc)
        for item in daily[offset : offset + 400]:
            batch.set(
                collection.document(f"csv_{item['date']}"),
                {**item, "user_id": user_id, "recorded_at": sync_time},
            )
        batch.commit()
    return daily


async def sync_configured_weather_csv() -> int:
    """Read the configured URL or local CSV and upsert its daily observations."""
    csv_url = settings.weather_csv_url
    csv_path = settings.weather_csv_path
    if not csv_url and not csv_path:
        return 0
    if csv_url:
        async with httpx.AsyncClient(timeout=45, follow_redirects=True) as client:
            response = await client.get(csv_url)
            response.raise_for_status()
            if len(response.content) > 5_000_000:
                raise ValueError("날씨 CSV 파일은 5MB 이하여야 합니다.")
            content_type = response.headers.get("content-type", "").lower()
            if "text/html" in content_type:
                raise ValueError("CSV 주소가 HTML 페이지를 반환했습니다. 직접 CSV 다운로드 주소인지 확인하세요.")
            content = response.content
    else:
        path = Path(csv_path)
        content = await asyncio.to_thread(path.read_bytes)
        if len(content) > 5_000_000:
            raise ValueError("날씨 CSV 파일은 5MB 이하여야 합니다.")
    csv_text = content.decode("utf-8-sig", errors="replace")
    if "\ufffd" in csv_text:
        csv_text = content.decode("euc-kr", errors="replace")
    rows = _parse_csv(csv_text)
    daily = save_weather_rows(settings.weather_csv_user_id, rows)
    return len(daily)


async def sync_recent_kma_daily_weather() -> int:
    """Fetch the latest available Changwon ASOS daily observations using data.go.kr."""
    if not settings.kma_api_key:
        return 0
    from app.services.kma_weather import fetch_daily_weather

    today = datetime.now(KST).date()
    # ASOS daily summaries are normally published after the observation day.
    end_date = today - timedelta(days=1)
    observations = await fetch_daily_weather(155, end_date - timedelta(days=6), end_date)
    db = get_firestore()
    if db is None:
        raise RuntimeError("Firestore에 연결되지 않았습니다.")

    def save_observations() -> None:
        collection = db.collection("users").document(settings.weather_csv_user_id).collection("weather_logs")
        batch = db.batch()
        for observation in observations:
            day = observation["observation_date"]
            batch.set(collection.document(f"kma_155_{day}"), {
                "user_id": settings.weather_csv_user_id,
                "date": day,
                "temperature_c": observation["temperature_c"],
                "precipitation_mm": observation["precipitation_mm"],
                "humidity_percent": observation["humidity_percent"],
                "city": "창원",
                "station_id": 155,
                "source": "kma_asos",
                "recorded_at": datetime.now(timezone.utc),
            })
        if observations:
            batch.commit()

    await asyncio.to_thread(save_observations)
    return len(observations)


def _forecast_items(payload: dict) -> list[dict]:
    response = payload.get("response", payload)
    header = response.get("header", {})
    if header and str(header.get("resultCode", "00")) not in {"00", "0"}:
        return []
    body = response.get("body", {})
    items = body.get("items", {})
    values = items.get("item", []) if isinstance(items, dict) else items
    if isinstance(values, dict):
        return [values]
    return [row for row in values if isinstance(row, dict)] if isinstance(values, list) else []


async def sync_changwon_mid_temperature_forecast() -> int:
    """Fetch KMA medium-range daily min/max forecasts for Changwon (days 4–10)."""
    if not settings.kma_apihub_key:
        return 0
    now = datetime.now(KST)
    issue_candidates = []
    for day_offset in range(2):
        issue_day = now.date() - timedelta(days=day_offset)
        for hour in (18, 6):
            issue = datetime.combine(issue_day, datetime.min.time()).replace(
                hour=hour, tzinfo=KST
            )
            if issue <= now and now - issue <= timedelta(hours=24):
                issue_candidates.append(issue)
    issue_candidates.sort(reverse=True)
    async with httpx.AsyncClient(timeout=30) as client:
        for issue in issue_candidates:
            response = await client.get(
                settings.kma_midta_api_url,
                params={
                    "pageNo": 1,
                    "numOfRows": 10,
                    "dataType": "JSON",
                    "regId": settings.kma_midta_region_id,
                    "tmFc": issue.strftime("%Y%m%d%H%M"),
                    "authKey": settings.kma_apihub_key,
                },
            )
            response.raise_for_status()
            items = _forecast_items(response.json())
            if not items:
                continue
            item = items[0]
            rows = []
            for day_offset in range(4, 11):
                minimum = item.get(f"taMin{day_offset}")
                maximum = item.get(f"taMax{day_offset}")
                try:
                    minimum_value = float(minimum)
                    maximum_value = float(maximum)
                except (TypeError, ValueError):
                    continue
                target_date = issue.date() + timedelta(days=day_offset)
                rows.append({
                    "date": target_date.isoformat(),
                    "temperature_c": round((minimum_value + maximum_value) / 2, 1),
                    "temperature_min_c": minimum_value,
                    "temperature_max_c": maximum_value,
                    "precipitation_mm": None,
                    "humidity_percent": None,
                    "precipitation_probability_pct": None,
                    "city": "창원",
                    "station_id": settings.kma_midta_region_id,
                    "source": "kma_apihub_midta_forecast",
                    "forecast_issue_time": issue.isoformat(),
                    "duplicate_count": 0,
                })
            if rows:
                db = get_firestore()
                if db is None:
                    raise RuntimeError("Firestore에 연결되지 않았습니다.")
                collection = db.collection("users").document(settings.weather_csv_user_id).collection("weather_logs")
                for row in rows:
                    collection.document(
                        f"forecast_{settings.kma_midta_region_id}_{row['date']}_{issue.strftime('%Y%m%d%H%M')}"
                    ).set({**row, "user_id": settings.weather_csv_user_id, "recorded_at": datetime.now(timezone.utc)})
                return len(rows)
    raise RuntimeError("최근 24시간의 창원 중기기온 예보를 찾지 못했습니다.")


async def weather_csv_poll_loop() -> None:
    """Refresh the configured source periodically while the API process runs."""
    interval = max(5, settings.weather_csv_refresh_minutes) * 60
    while True:
        try:
            count = await sync_configured_weather_csv()
            count += await sync_recent_kma_daily_weather()
            count += await sync_changwon_mid_temperature_forecast()
            if count:
                logger.info("Weather CSV sync stored %s daily rows", count)
        except asyncio.CancelledError:
            raise
        except Exception as error:
            logger.error("Scheduled weather import failed (%s)", type(error).__name__)
        await asyncio.sleep(interval)
