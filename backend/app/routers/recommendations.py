"""개인화 음식 추천 및 추천 결과 저장 API."""

from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.firebase import get_firestore
from app.models import RecommendationRequest, RecommendationResponse
from app.services.food_safety import search_foods
from app.services.recommendation import analyze_situation, write_rationale

router = APIRouter(prefix="/api/recommendations", tags=["추천"])


def _latest_record(db, collection: str, user_id: str, city: str | None = None):
    records = db.collection(collection).where("user_id", "==", user_id).stream()
    values = [record.to_dict() for record in records]
    if city and collection == "weather":
        values = [record for record in values if record.get("city") == city]
    values.sort(key=lambda item: item.get("recorded_at"), reverse=True)
    return values[0] if values else None


def _weather_history(db, user_id: str, city: str | None = None):
    records = db.collection("weather").where("user_id", "==", user_id).stream()
    values = [record.to_dict() for record in records]
    if city:
        values = [record for record in values if record.get("city") == city]
    values.sort(key=lambda item: str(item.get("observation_date") or item.get("recorded_at", "")))
    return values


def _recorded_today(record: dict) -> bool:
    """Firestore 날짜를 UTC로 정규화해 오늘 기록인지 확인합니다."""
    recorded_at = record.get("recorded_at")
    if hasattr(recorded_at, "to_datetime"):
        recorded_at = recorded_at.to_datetime()
    if not isinstance(recorded_at, datetime):
        return False
    if recorded_at.tzinfo is None:
        recorded_at = recorded_at.replace(tzinfo=timezone.utc)
    return recorded_at.astimezone(timezone.utc).date() == datetime.now(timezone.utc).date()


@router.post("", response_model=RecommendationResponse)
async def recommend(request: RecommendationRequest):
    """기록을 분석하고 공공데이터포털 식품 검색 결과를 Firestore에 저장합니다."""
    db = get_firestore()
    if db is None:
        raise HTTPException(
            status_code=503,
            detail="Firestore가 연결되지 않았습니다. 서비스 계정 경로를 확인하세요.",
        )

    try:
        meals = [
            record.to_dict()
            for record in db.collection("meals").where("user_id", "==", request.user_id).stream()
        ]
        calories_consumed = sum(
            float(meal.get("calories", 0)) for meal in meals if _recorded_today(meal)
        )
        weather_history = _weather_history(db, request.user_id, request.city)
        weather = weather_history[-1] if weather_history else None
        activity = _latest_record(db, "activity", request.user_id)
        situation, queries = analyze_situation(
            weather,
            activity,
            calories_consumed,
            request.daily_calorie_target,
            weather_history,
        )

        foods = []
        for query in queries:
            foods.extend(await search_foods(query, limit=3))
        unique_foods = []
        seen = set()
        for food in foods:
            key = food.get("FOOD_NM_KR") or str(food)
            if key not in seen:
                seen.add(key)
                unique_foods.append(food)
        unique_foods = unique_foods[:8]
    except (RuntimeError, ValueError) as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"추천 데이터를 가져오지 못했습니다: {error}") from error

    remaining = max(request.daily_calorie_target - calories_consumed, 0)
    rationale = await write_rationale(situation, unique_foods, remaining)
    recommendation = RecommendationResponse(
        user_id=request.user_id,
        daily_calorie_target=request.daily_calorie_target,
        calories_consumed=calories_consumed,
        calories_remaining=remaining,
        situation=situation,
        food_queries=queries,
        foods=unique_foods,
        rationale=rationale,
        created_at=datetime.now(timezone.utc),
    )
    stored = recommendation.model_dump()
    reference = db.collection("recommendations").add(stored)[1]
    return recommendation.model_copy(update={"id": reference.id})


@router.get("")
def list_recommendations(user_id: str, limit: int = 20):
    """사용자의 저장된 추천 결과를 최신순으로 조회합니다."""
    if limit < 1 or limit > 100:
        raise HTTPException(status_code=422, detail="limit은 1~100 사이여야 합니다.")
    db = get_firestore()
    if db is None:
        raise HTTPException(
            status_code=503,
            detail="Firestore가 연결되지 않았습니다. 서비스 계정 경로를 확인하세요.",
        )
    records = db.collection("recommendations").where("user_id", "==", user_id).stream()
    result = [{"id": record.id, **record.to_dict()} for record in records]
    result.sort(key=lambda item: item.get("created_at"), reverse=True)
    return result[:limit]