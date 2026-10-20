"""사용자 활동량 입력과 조회 API."""

from fastapi import APIRouter, HTTPException, Query

from app.firebase import get_user_collection
from app.models import ActivityLogInput
from app.services.recommendation import estimate_burned_calories

router = APIRouter(prefix="/api/activity", tags=["활동량"])


@router.post("", status_code=201)
def save_activity_log(log: ActivityLogInput):
    """활동량과 간단한 소모 칼로리 추정치를 사용자 하위 컬렉션에 저장합니다."""
    collection = get_user_collection(log.user_id, "activity_logs")
    if collection is None:
        raise HTTPException(status_code=503, detail="Firestore에 연결되지 않았습니다.")
    data = log.model_dump()
    data["date"] = log.date.isoformat()
    data["estimated_burned_calories"] = estimate_burned_calories(log)
    reference = collection.add(data)[1]
    return {"id": reference.id, **data}


@router.get("")
def get_activity_logs(
    user_id: str = Query(min_length=1),
    log_date: str | None = Query(default=None, alias="date"),
    limit: int = Query(default=100, ge=1, le=500),
):
    """사용자 활동량 기록을 조회합니다."""
    collection = get_user_collection(user_id, "activity_logs")
    if collection is None:
        raise HTTPException(status_code=503, detail="Firestore에 연결되지 않았습니다.")
    results = [{"id": row.id, **row.to_dict()} for row in collection.stream()]
    if log_date:
        results = [row for row in results if row.get("date") == log_date]
    results.sort(key=lambda row: row.get("date", ""), reverse=True)
    return results[:limit]