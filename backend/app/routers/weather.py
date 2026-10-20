"""날씨 기록 저장·조회 및 기상청 과거 관측자료 동기화 API."""

from datetime import date

from fastapi import APIRouter, HTTPException, Query

from app.firebase import get_firestore, get_user_collection
from app.models import KmaWeatherSyncRequest, WeatherLogInput
from app.services.kma_weather import fetch_daily_weather

router = APIRouter(prefix="/api/weather", tags=["날씨"])


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