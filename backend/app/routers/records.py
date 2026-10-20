"""식단, 날씨, 활동량 기록 저장 및 조회 API."""

from datetime import date
from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.firebase import get_firestore
from app.models import ActivityRecord, KmaWeatherSyncRequest, MealRecord, WeatherRecord
from app.services.kma_weather import fetch_daily_weather

router = APIRouter(prefix="/api", tags=["기록"])


def _collection(name: str):
    db = get_firestore()
    if db is None:
        raise HTTPException(
            status_code=503,
            detail="Firestore가 연결되지 않았습니다. 서비스 계정 경로를 확인하세요.",
        )
    return db.collection(name)


def _save_record(collection: str, record: Any) -> dict[str, Any]:
    data = record.model_dump()
    if isinstance(data.get("observation_date"), date):
        data["observation_date"] = data["observation_date"].isoformat()
    reference = _collection(collection).add(data)[1]
    return {"id": reference.id, **data}


def _list_records(collection: str, user_id: str, limit: int) -> list[dict[str, Any]]:
    records = _collection(collection).where("user_id", "==", user_id).stream()
    result = [{"id": item.id, **item.to_dict()} for item in records]
    result.sort(key=lambda item: item.get("recorded_at"), reverse=True)
    return result[:limit]


@router.post("/meals", status_code=201)
def save_meal(record: MealRecord):
    return _save_record("meals", record)


@router.get("/meals")
def list_meals(user_id: str = Query(min_length=1), limit: int = Query(default=50, ge=1, le=100)):
    return _list_records("meals", user_id, limit)


@router.post("/weather", status_code=201)
def save_weather(record: WeatherRecord):
    return _save_record("weather", record)


@router.get("/weather")
def list_weather(user_id: str = Query(min_length=1), limit: int = Query(default=50, ge=1, le=100)):
    return _list_records("weather", user_id, limit)


@router.post("/weather/kma/sync")
async def sync_kma_weather(request: KmaWeatherSyncRequest):
    """기상청 ASOS 일자료를 가져와 날짜별 Firestore 문서로 저장합니다."""
    if request.end_date < request.start_date:
        raise HTTPException(status_code=422, detail="end_date는 start_date보다 빠를 수 없습니다.")
    if (request.end_date - request.start_date).days > 365:
        raise HTTPException(status_code=422, detail="한 번에 최대 366일까지만 동기화할 수 있습니다.")
    db = get_firestore()
    if db is None:
        raise HTTPException(
            status_code=503,
            detail="Firestore가 연결되지 않았습니다. 서비스 계정 경로를 확인하세요.",
        )
    try:
        observations = await fetch_daily_weather(
            request.station_id, request.start_date, request.end_date
        )
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"기상청 자료를 가져오지 못했습니다: {error}") from error

    collection = db.collection("weather")
    batch = db.batch()
    for observation in observations:
        document_id = f"kma_{request.user_id}_{request.station_id}_{observation['observation_date']}"
        batch.set(collection.document(document_id), {"user_id": request.user_id, **observation})
    if observations:
        batch.commit()
    return {"saved_count": len(observations), "station_id": request.station_id}


@router.get("/weather/history")
def list_weather_history(
    user_id: str = Query(min_length=1),
    start_date: date = Query(...),
    end_date: date = Query(...),
    limit: int = Query(default=100, ge=1, le=366),
):
    """사용자 날씨 기록 중 지정한 관측 날짜 범위를 조회합니다."""
    if end_date < start_date:
        raise HTTPException(status_code=422, detail="end_date는 start_date보다 빠를 수 없습니다.")
    records = _list_records("weather", user_id, 1000)
    result = [
        record
        for record in records
        if record.get("observation_date")
        and start_date <= date.fromisoformat(str(record["observation_date"])[:10]) <= end_date
    ]
    return result[:limit]


@router.post("/activity", status_code=201)
def save_activity(record: ActivityRecord):
    return _save_record("activity", record)


@router.get("/activity")
def list_activity(user_id: str = Query(min_length=1), limit: int = Query(default=50, ge=1, le=100)):
    return _list_records("activity", user_id, limit)