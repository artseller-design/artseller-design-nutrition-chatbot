"""날씨 기록 저장·조회 및 기상청 과거 관측자료 동기화 API."""

import csv
import io
from datetime import date, datetime, timezone, timedelta

from fastapi import APIRouter, HTTPException, Query

from app.firebase import get_firestore, get_user_collection
from app.models import (
    KmaWeatherSyncRequest,
    SavedWeatherRecommendationRequest,
    WeatherCsvRecommendationRequest,
    WeatherLogInput,
)
from app.services.kma_weather import fetch_daily_weather
from app.services.food_api import search_foods
from app.services.weather_csv import normalize_weather_rows, save_weather_rows

router = APIRouter(prefix="/api/weather", tags=["날씨"])


def _csv_number(value: str | None) -> float | None:
    value = (value or "").strip()
    if value in {"", "-", "NA", "NaN"}:
        return None
    try:
        return float(value.replace(",", ""))
    except ValueError:
        return None


def _parse_weather_csv(csv_text: str) -> list[dict]:
    reader = csv.DictReader(io.StringIO(csv_text.lstrip("\ufeff")))
    if not reader.fieldnames:
        raise HTTPException(status_code=422, detail="CSV 헤더를 읽을 수 없습니다.")
    aliases = {
        "date": ("tm", "date", "observation_date", "일시", "날짜"),
        "temperature": ("avgTa", "temperature_c", "temperature", "평균기온", "평균기온(℃)"),
        "precipitation": ("sumRn", "precipitation_mm", "precipitation", "일강수량", "일강수량(mm)"),
        "humidity": ("avgRhm", "humidity_percent", "humidity", "평균상대습도", "평균상대습도(%)"),
        "city": ("stnNm", "city", "지점명", "지역"),
        "station_id": ("stnId", "station_id", "지점"),
    }
    normalized = {name.strip().casefold(): name for name in reader.fieldnames}
    columns = {
        key: next((normalized[name.casefold()] for name in names if name.casefold() in normalized), None)
        for key, names in aliases.items()
    }
    if not columns["date"] or not columns["temperature"]:
        raise HTTPException(status_code=422, detail="CSV에는 날짜(tm/date)와 평균기온(avgTa/temperature_c) 열이 필요합니다.")
    rows = []
    for line, row in enumerate(reader, start=2):
        raw_date = (row.get(columns["date"]) or "").strip()
        if not raw_date:
            continue
        try:
            observed = date.fromisoformat(raw_date[:10]) if "-" in raw_date else datetime.strptime(raw_date[:8], "%Y%m%d").date()
        except ValueError as error:
            raise HTTPException(status_code=422, detail=f"CSV {line}행 날짜를 해석할 수 없습니다.") from error
        temperature = _csv_number(row.get(columns["temperature"]))
        if temperature is None:
            continue
        rows.append({
            "date": observed.isoformat(),
            "temperature_c": temperature,
            "precipitation_mm": _csv_number(row.get(columns["precipitation"])) if columns["precipitation"] else None,
            "humidity_percent": _csv_number(row.get(columns["humidity"])) if columns["humidity"] else None,
            "city": (row.get(columns["city"]) or "창원").strip() if columns["city"] else "창원",
            "station_id": (row.get(columns["station_id"]) or "").strip() if columns["station_id"] else "",
        })
    if not rows:
        raise HTTPException(status_code=422, detail="유효한 날짜와 평균기온이 있는 행을 찾지 못했습니다.")
    return rows


@router.post("/csv/recommend")
async def recommend_from_weather_csv(
    request: WeatherCsvRecommendationRequest,
    persist_observations: bool = True,
):
    """CSV 일별 날씨 자료를 저장하고 선택 날짜의 조건으로 음식을 추천합니다."""
    db = get_firestore()
    if db is None:
        raise HTTPException(status_code=503, detail="Firestore에 연결되지 않았습니다.")
    rows = _parse_weather_csv(request.csv_text)
    daily = normalize_weather_rows(rows)
    target = next((item for item in daily if item["date"] == request.target_date.isoformat()), None)
    if target is None:
        raise HTTPException(status_code=422, detail="CSV에 선택한 날짜의 유효한 기온 관측값이 없습니다.")
    recent_start = request.target_date - timedelta(days=6)
    recent = [item for item in daily if recent_start.isoformat() <= item["date"] <= request.target_date.isoformat()]
    expected_days = (request.target_date - recent_start).days + 1
    temp = target["temperature_c"]
    queries = []
    reasons = []
    if temp >= 28:
        queries.extend(["샐러드", "두부", "오이"])
        reasons.append("기온이 높아 가벼운 메뉴를 우선했습니다.")
    elif temp <= 5:
        queries.extend(["국", "생선구이", "두부"])
        reasons.append("기온이 낮아 따뜻하고 균형 잡힌 메뉴를 우선했습니다.")
    else:
        queries.extend(["현미밥", "생선구이", "채소"])
        reasons.append("당일 기온에 맞춰 균형 잡힌 메뉴를 골랐습니다.")
    rainy_days = sum(1 for item in recent if (item["precipitation_mm"] or 0) > 0)
    if (target["precipitation_mm"] or 0) > 0 or rainy_days >= 2:
        queries = ["콩나물국", "미역국", *queries]
        reasons.append("당일 또는 최근 비가 관측되어 따뜻한 국물 메뉴를 포함했습니다.")

    if persist_observations:
        try:
            daily = save_weather_rows(request.user_id, rows)
        except RuntimeError as error:
            raise HTTPException(status_code=503, detail=str(error)) from error

    try:
        candidates = []
        for query in dict.fromkeys(queries):
            candidates.extend(await search_foods(query, limit=5))
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"식품 영양정보 검색에 실패했습니다: {error}") from error
    unique = {}
    for food in candidates:
        unique.setdefault(food.get("food_name", ""), food)
    foods = [{
        "food_name": item["food_name"],
        "calories_kcal": item.get("calories"),
        "protein_g": item.get("protein"),
        "carbohydrate_g": item.get("carbohydrate"),
        "fat_g": item.get("fat"),
        "nutrient_basis_g": item.get("basis_amount_g"),
        "reason": "공공 식품 영양정보 검색 결과이며 날씨 조건을 고려한 메뉴 후보입니다.",
    } for item in list(unique.values())[:8]]
    result = {
        "user_id": request.user_id,
        "target_date": request.target_date.isoformat(),
        "weather": target,
        "recent_weather_days": len(recent),
        "missing_days_in_recent_week": max(0, expected_days - len(recent)),
        "duplicate_rows_for_target_date": target["duplicate_count"],
        "recommendation_reason": " ".join(reasons),
        "food_queries": list(dict.fromkeys(queries)),
        "foods": foods,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    db.collection("users").document(request.user_id).collection("weather_recommendations").add(result)
    return result


@router.post("/recommend-saved")
async def recommend_from_saved_weather(request: SavedWeatherRecommendationRequest):
    """Use previously imported CSV/KMA observations without uploading the file again."""
    db = get_firestore()
    if db is None:
        raise HTTPException(status_code=503, detail="Firestore에 연결되지 않았습니다.")
    start = request.target_date - timedelta(days=6)
    collection = db.collection("users").document(request.user_id).collection("weather_logs")
    records = [document.to_dict() or {} for document in collection.stream()]
    grouped: dict[str, list[dict]] = {}
    for record in records:
        day = str(record.get("date") or record.get("observation_date") or "")[:10]
        if start.isoformat() <= day <= request.target_date.isoformat():
            grouped.setdefault(day, []).append(record)
    rows = []
    for day, day_records in sorted(grouped.items()):
        forecasts = [record for record in day_records if record.get("source") == "kma_apihub_midta_forecast"]
        selected_records = (
            [max(forecasts, key=lambda record: str(record.get("forecast_issue_time", "")))]
            if forecasts
            else day_records
        )
        for record in selected_records:
            rows.append({
                "tm": day,
                "avgTa": record.get("temperature_c", record.get("temperature")),
                "sumRn": record.get("precipitation_mm"),
                "avgRhm": record.get("humidity_percent", record.get("humidity")),
                "stnNm": record.get("city", "창원"),
                "stnId": record.get("station_id", ""),
            })
    if not rows:
        raise HTTPException(status_code=404, detail="선택 날짜의 저장된 날씨 자료가 없습니다. CSV 자동 수집 설정을 확인하거나 파일을 직접 올려 주세요.")
    output = io.StringIO()
    writer = csv.DictWriter(output, fieldnames=["tm", "avgTa", "sumRn", "avgRhm", "stnNm", "stnId"])
    writer.writeheader()
    writer.writerows(rows)
    return await recommend_from_weather_csv(
        WeatherCsvRecommendationRequest(
            user_id=request.user_id,
            target_date=request.target_date,
            csv_text=output.getvalue(),
        ),
        persist_observations=False,
    )


@router.post("", status_code=201)
def save_weather_log(log: WeatherLogInput):
    """사용자 날씨 기록을 Firestore 하위 컬렉션에 저장합니다."""
    collection = get_user_collection(log.user_id, "weather_logs")
    if collection is None:
        raise HTTPException(status_code=503, detail="Firestore에 연결되지 않았습니다.")
    data = log.model_dump()
    data["date"] = log.date.isoformat()
    reference = collection.add(data)[1]
    return {"id": reference.id, **data}


@router.get("")
def get_weather_logs(
    user_id: str = Query(min_length=1),
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(default=100, ge=1, le=500),
):
    """사용자 날씨 기록을 조회하고 필요하면 날짜 범위로 좁힙니다."""
    collection = get_user_collection(user_id, "weather_logs")
    if collection is None:
        raise HTTPException(status_code=503, detail="Firestore에 연결되지 않았습니다.")
    results = [{"id": row.id, **row.to_dict()} for row in collection.stream()]
    if start_date:
        results = [row for row in results if row.get("date", "") >= start_date.isoformat()]
    if end_date:
        results = [row for row in results if row.get("date", "") <= end_date.isoformat()]
    results.sort(key=lambda row: row.get("date", ""), reverse=True)
    return results[:limit]


@router.post("/kma/sync")
async def sync_kma_weather(request: KmaWeatherSyncRequest):
    """기상청 ASOS 일자료를 사용자별 날씨 기록으로 저장합니다."""
    if request.end_date < request.start_date:
        raise HTTPException(status_code=422, detail="end_date가 start_date보다 빠릅니다.")
    if (request.end_date - request.start_date).days > 365:
        raise HTTPException(status_code=422, detail="한 번에 최대 366일을 동기화할 수 있습니다.")
    collection = get_user_collection(request.user_id, "weather_logs")
    if collection is None or get_firestore() is None:
        raise HTTPException(status_code=503, detail="Firestore에 연결되지 않았습니다.")
    try:
        observations = await fetch_daily_weather(
            request.station_id, request.start_date, request.end_date
        )
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"기상청 자료 조회에 실패했습니다: {error}") from error

    batch = get_firestore().batch()
    for row in observations:
        observation_date = row["observation_date"]
        reference = collection.document(f"kma_{request.station_id}_{observation_date}")
        batch.set(
            reference,
            {
                "user_id": request.user_id,
                "date": observation_date,
                "temperature": row["temperature_c"],
                "humidity": row.get("humidity_percent") or 0,
                "condition": row["condition"],
                "precipitation_mm": row.get("precipitation_mm") or 0,
                "station_id": request.station_id,
                "source": "kma_asos",
            },
        )
    if observations:
        batch.commit()
    return {"saved_count": len(observations), "station_id": request.station_id}
