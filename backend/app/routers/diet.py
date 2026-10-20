"""사용자 식단 기록 저장 및 날짜별 조회 API."""

from fastapi import APIRouter, HTTPException, Query

from app.firebase import get_user_collection
from app.models import DietLogInput

router = APIRouter(prefix="/api/diet", tags=["식단"])


@router.post("", status_code=201)
def save_diet_log(log: DietLogInput):
    """식단 기록을 users/{user_id}/diet_logs에 저장합니다."""
    collection = get_user_collection(log.user_id, "diet_logs")
    if collection is None:
        raise HTTPException(status_code=503, detail="Firestore에 연결되지 않았습니다.")
    data = log.model_dump()
    data["date"] = log.date.isoformat()
    reference = collection.add(data)[1]
    return {"id": reference.id, **data}


@router.get("")
def get_diet_logs(
    user_id: str = Query(min_length=1),
    log_date: str | None = Query(default=None, alias="date"),
    limit: int = Query(default=100, ge=1, le=500),
):
    """사용자 식단을 최신 날짜부터 조회합니다. date를 지정하면 하루만 조회합니다."""
    collection = get_user_collection(user_id, "diet_logs")
    if collection is None:
        raise HTTPException(status_code=503, detail="Firestore에 연결되지 않았습니다.")
    records = collection.stream()
    results = [{"id": row.id, **row.to_dict()} for row in records]
    if log_date:
        results = [row for row in results if row.get("date") == log_date]
    results.sort(key=lambda row: row.get("date", ""), reverse=True)
    return results[:limit]