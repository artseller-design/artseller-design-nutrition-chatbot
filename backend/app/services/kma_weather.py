"""기상청 ASOS 일자료 조회 및 앱 내부 날씨 데이터 변환."""

from datetime import date, datetime, timedelta, timezone
from typing import Any

import httpx

from app.config import settings

KST = timezone(timedelta(hours=9), "KST")


def _items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    response = payload.get("response", {})
    header = response.get("header", {})
    if header and str(header.get("resultCode", "00")) != "00":
        raise RuntimeError(f"기상청 API 오류: {header.get('resultMsg', '알 수 없는 오류')}")
    body = response.get("body", {})
    items = body.get("items", {})
    rows = items.get("item", []) if isinstance(items, dict) else items
    if isinstance(rows, dict):
        return [rows]
    if isinstance(rows, list):
        return [row for row in rows if isinstance(row, dict)]
    return []


def _number(value: Any) -> float | None:
    if value in (None, "", "-"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


async def fetch_daily_weather(
    station_id: int, start_date: date, end_date: date
) -> list[dict[str, Any]]:
    """ASOS 일자료를 조회해 Firestore 저장용 형식으로 반환합니다."""
    if not settings.kma_api_key:
        raise RuntimeError("KMA_API_KEY가 설정되지 않았습니다.")

    params = {
        "serviceKey": settings.kma_api_key,
        "pageNo": 1,
        "numOfRows": 366,
        "dataType": "JSON",
        "dataCd": "ASOS",
        "dateCd": "DAY",
        "startDt": start_date.strftime("%Y%m%d"),
        "endDt": end_date.strftime("%Y%m%d"),
        "stnIds": station_id,
    }
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(settings.kma_daily_api_url, params=params)
        response.raise_for_status()
        rows = _items(response.json())

    observations = []
    for row in rows:
        observed_on = date.fromisoformat(row["tm"])
        temperature = _number(row.get("avgTa"))
        if temperature is None:
            continue
        precipitation = _number(row.get("sumRn"))
        phenomenon = row.get("iscs") or ""
        if precipitation and precipitation > 0:
            condition = "rainy"
        elif "눈" in phenomenon:
            condition = "snowy"
        elif "비" in phenomenon:
            condition = "rainy"
        else:
            condition = "clear_or_cloudy"

        observations.append(
            {
                "city": row.get("stnNm") or str(station_id),
                "station_id": station_id,
                "source": "kma_asos",
                "observation_date": observed_on.isoformat(),
                "temperature_c": temperature,
                "condition": condition,
                "weather_phenomenon": phenomenon,
                "humidity_percent": _number(row.get("avgRhm")),
                "precipitation_mm": precipitation,
                "recorded_at": datetime.now(timezone.utc),
                "observed_at": datetime.combine(
                    observed_on, datetime.min.time(), tzinfo=KST
                ),
            }
        )
    return observations
