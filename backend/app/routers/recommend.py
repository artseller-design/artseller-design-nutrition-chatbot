"""개인화 음식 추천 요청 및 Firestore 저장 API."""

from datetime import datetime, time, timedelta, timezone

from fastapi import APIRouter, HTTPException

from app.firebase import get_firestore, get_user_collection
from app.models import DietLogInput, RecommendRequest, RecommendResponse
from app.services.recommendation import estimate_burned_calories, make_recommendation

router = APIRouter(prefix="/api/recommend", tags=["추천"])


@router.post("", response_model=RecommendResponse)
async def recommend(request: RecommendRequest):
    """현재 날씨·활동량과 오늘 식단으로 음식 추천을 만들고 저장합니다."""
    db = get_firestore()
    if db is None:
        raise HTTPException(status_code=503, detail="Firestore에 연결되지 않았습니다.")

    diet_collection = get_user_collection(request.user_id, "diet_logs")
    food_entry_collection = get_user_collection(request.user_id, "food_entries")
    weather_collection = get_user_collection(request.user_id, "weather_logs")
    activity_collection = get_user_collection(request.user_id, "activity_logs")
    recommendation_collection = get_user_collection(request.user_id, "recommendations")

    # API 본문에 포함된 오늘 날씨와 활동량도 기록으로 남겨 과거 분석에 활용합니다.
    weather_data = request.weather.model_dump()
    weather_data.update({"user_id": request.user_id, "date": request.date.isoformat()})
    weather_collection.add(weather_data)
    activity_data = request.activity.model_dump()
    activity_data.update(
        {
            "user_id": request.user_id,
            "date": request.date.isoformat(),
            "estimated_burned_calories": estimate_burned_calories(request.activity),
        }
    )
    activity_collection.add(activity_data)

    diet_logs = [
        {"id": row.id, **row.to_dict()}
        for row in diet_collection.where("date", "==", request.date.isoformat()).stream()
    ]
    diet_entries = [DietLogInput.model_validate(row) for row in diet_logs]
    start_of_day = datetime.combine(request.date, time.min, tzinfo=timezone.utc)
    end_of_day = start_of_day + timedelta(days=1)
    food_entries = food_entry_collection.where(
        "recorded_at", ">=", start_of_day
    ).where("recorded_at", "<", end_of_day).stream()
    for row in food_entries:
        entry = row.to_dict()
        nutrients = entry.get("nutrients") or {}
        diet_entries.append(
            DietLogInput(
                user_id=request.user_id,
                date=request.date,
                food_name=entry["food_name"],
                calories=nutrients.get("calories_kcal", 0),
                carbohydrate=nutrients.get("carbohydrate_g", 0),
                protein=nutrients.get("protein_g", 0),
                fat=nutrients.get("fat_g", 0),
                sodium=nutrients.get("sodium_mg", 0),
                memo=entry.get("memo"),
            )
        )
    weather_history = [row.to_dict() for row in weather_collection.stream()]
    weather_history.sort(key=lambda row: row.get("date", ""))

    try:
        conditions, foods = await make_recommendation(
            request.weather,
            request.activity,
            diet_entries,
            request.diet_goal,
            weather_history,
        )
    except RuntimeError as error:
        raise HTTPException(status_code=503, detail=str(error)) from error
    except Exception as error:
        raise HTTPException(status_code=502, detail=f"음식 추천 중 오류가 발생했습니다: {error}") from error

    response = RecommendResponse(
        situation_summary=conditions["summary"],
        recommendation_reason=conditions["reason"],
        recommended_foods=foods,
    )
    saved_data = response.model_dump()
    saved_data.update(
        {
            "user_id": request.user_id,
            "date": request.date.isoformat(),
            "diet_goal": request.diet_goal.model_dump(),
        }
    )
    reference = recommendation_collection.add(saved_data)[1]
    return response