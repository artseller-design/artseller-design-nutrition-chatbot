"""날씨, 활동량, 식단 기록으로 음식 검색어와 설명을 만듭니다."""

from typing import Any

from openai import AsyncOpenAI

from app.config import settings
from app.models import ActivityInput, DietGoal, DietLogInput, RecommendedFood, WeatherInput
from app.services.food_api import search_foods
from app.services.openai_service import explain_recommendation


def analyze_situation(
    weather: dict[str, Any] | None,
    activity: dict[str, Any] | None,
    calories_consumed: float,
    calorie_target: float,
    weather_history: list[dict[str, Any]] | None = None,
) -> tuple[list[str], list[str]]:
    """규칙 기반으로 현재 상황과 검색할 음식 종류를 정합니다."""
    situation: list[str] = []
    queries: list[str] = []

    recent_weather = (weather_history or [])[-7:]
    temperatures = [
        float(record["temperature_c"])
        for record in recent_weather
        if record.get("temperature_c") is not None
    ]
    temperature = weather.get("temperature_c") if weather else None
    if not temperatures and temperature is not None:
        temperatures.append(float(temperature))
    average_temperature = sum(temperatures) / len(temperatures) if temperatures else None

    if recent_weather:
        situation.append(f"최근 {len(recent_weather)}일 기상 관측 이력을 추천에 반영했습니다.")

    if average_temperature is not None and average_temperature >= 28:
        situation.append("기온이 높아 수분 보충과 가벼운 식사가 좋습니다.")
        queries.extend(["샐러드", "두부"])
    elif average_temperature is not None and average_temperature <= 5:
        situation.append("기온이 낮아 따뜻하고 균형 잡힌 식사가 좋습니다.")
        queries.extend(["국밥", "생선구이"])
    elif weather:
        situation.append(f"{weather.get('city', '현재 지역')} 날씨를 반영했습니다.")

    rainy_days = sum(
        1
        for record in recent_weather
        if (record.get("precipitation_mm") or 0) > 0
        or any(word in str(record.get("condition", "")) for word in ("비", "눈", "강수"))
    )
    if rainy_days >= 2:
        situation.append(f"최근 관측 기간 중 비나 눈이 온 날이 {rainy_days}일입니다.")
        queries.extend(["콩나물국", "미역국"])

    steps = activity.get("steps", 0) if activity else 0
    exercise_minutes = activity.get("exercise_minutes", 0) if activity else 0
    if steps >= 8000 or exercise_minutes >= 60:
        situation.append("활동량이 많아 단백질과 복합 탄수화물을 고려했습니다.")
        queries.extend(["닭가슴살", "현미밥"])
    elif activity:
        situation.append("기록된 활동량에 맞춰 과식하지 않는 메뉴를 우선합니다.")

    remaining = max(calorie_target - calories_consumed, 0)
    if remaining < calorie_target * 0.25:
        situation.append("오늘 남은 목표 열량이 적어 저열량 메뉴를 우선합니다.")
        queries.extend(["두부", "샐러드"])
    else:
        situation.append("오늘 섭취 기록과 목표 열량을 반영했습니다.")
        queries.extend(["연어", "잡곡밥"])

    return situation, list(dict.fromkeys(queries))[:3]


async def write_rationale(
    situation: list[str], foods: list[dict[str, Any]], calories_remaining: float
) -> str:
    """OpenAI 키가 있으면 쉬운 추천 설명을 만들고, 없으면 기본 설명을 씁니다."""
    names = [
        str(food.get("FOOD_NM_KR") or food.get("food_name") or "음식")
        for food in foods[:5]
    ]
    fallback = " ".join(situation) + f" 남은 목표 열량은 약 {calories_remaining:.0f} kcal입니다."
    if not settings.openai_api_key or not names:
        return fallback

    try:
        client = AsyncOpenAI(api_key=settings.openai_api_key)
        result = await client.chat.completions.create(
            model=settings.openai_model,
            messages=[
                {
                    "role": "system",
                    "content": "한국어로 식품 정보와 주어진 상황만 근거로 한 짧은 식단 추천 설명을 작성하세요. 의료 조언은 하지 마세요.",
                },
                {
                    "role": "user",
                    "content": f"상황: {situation}\n검색 결과 음식: {names}\n남은 목표 열량: {calories_remaining:.0f} kcal",
                },
            ],
            max_tokens=180,
        )
        content = result.choices[0].message.content
        return content.strip() if content else fallback
    except Exception:
        return fallback


def estimate_burned_calories(activity: ActivityInput) -> float:
    """걸음 수와 운동 시간으로 대략적인 활동 소모 열량을 계산합니다."""
    calories_per_exercise_minute = {"low": 3.0, "moderate": 5.0, "high": 8.0}
    return round(
        activity.steps * 0.04
        + activity.exercise_minutes * calories_per_exercise_minute[activity.intensity]
    )


def build_recommendation_conditions(
    weather: WeatherInput,
    activity: ActivityInput,
    diet_logs: list[DietLogInput],
    diet_goal: DietGoal,
    weather_history: list[dict[str, Any]],
) -> dict[str, Any]:
    """오늘 기록과 환경을 요약해 검색어와 영양 필터 조건을 만듭니다."""
    total_calories = sum(item.calories for item in diet_logs)
    total_carbohydrate = sum(item.carbohydrate for item in diet_logs)
    total_protein = sum(item.protein for item in diet_logs)
    total_sodium = sum(item.sodium for item in diet_logs)
    burned_calories = estimate_burned_calories(activity)
    # 운동 추정치를 전부 식사 예산에 더하지 않도록 40%, 최대 300 kcal만 반영합니다.
    activity_calorie_credit = min(round(burned_calories * 0.4), 300)
    adjusted_calorie_target = diet_goal.target_calories + activity_calorie_credit
    remaining_calories = max(adjusted_calorie_target - total_calories, 0)

    recent = weather_history[-7:]
    temperatures = [weather.temperature] + [
        float(row.get("temperature", row.get("temperature_c", 0))) for row in recent
    ]
    average_temperature = sum(temperatures) / len(temperatures)
    rainy_days = sum(
        1
        for row in recent
        if (row.get("precipitation_mm") or 0) > 0
        or any(word in str(row.get("condition", "")) for word in ("rain", "비", "눈", "강수"))
    )
    is_hot = weather.temperature >= 28 or average_temperature >= 28
    is_cold_or_rainy = weather.temperature <= 5 or rainy_days >= 2 or any(
        word in weather.condition.lower() for word in ("rain", "비", "snow", "눈")
    )
    is_active = activity.steps >= 8000 or activity.exercise_minutes >= 45
    high_carbohydrate = total_carbohydrate >= diet_goal.target_calories * 0.5 / 4
    high_sodium = total_sodium >= 2000

    queries: list[str] = []
    if is_hot:
        queries.extend(["오이", "수박", "두부 샐러드"])
    if is_cold_or_rainy:
        queries.extend(["맑은 국", "콩나물국", "생선구이"])
    if is_active or activity.intensity == "high":
        queries.extend(["닭가슴살", "두부", "달걀"])
    if high_carbohydrate:
        queries.extend(["두부", "구운 생선", "샐러드"])
    if high_sodium:
        queries.extend(["오이", "양배추 샐러드", "무염 두부"])
    if diet_goal.goal == "weight_loss" or remaining_calories < diet_goal.target_calories * 0.3:
        queries.extend(["닭가슴살 샐러드", "버섯", "두부"])
    if not queries:
        queries.extend(["연어", "잡곡밥", "채소 샐러드"])
    queries = list(dict.fromkeys(queries))[:5]

    context = []
    if is_hot:
        context.append("덥고 습도가 높은 날씨" if weather.humidity >= 70 else "더운 날씨")
    if is_cold_or_rainy:
        context.append("최근 비·눈 또는 추운 날씨")
    if is_active:
        context.append("높은 활동량")
    if high_carbohydrate:
        context.append("오늘 탄수화물 섭취가 많은 편")
    if high_sodium:
        context.append("오늘 나트륨 섭취가 많은 편")
    if not context:
        context.append("오늘의 식단 목표와 기록")

    summary = "오늘은 " + ", ".join(context) + "을 고려했습니다."
    reason = (
        f"목표 {diet_goal.goal}, 섭취 {total_calories:.0f} kcal, "
        f"잔여 목표 {remaining_calories:.0f} kcal, 활동 소모 추정 {burned_calories:.0f} kcal입니다. "
        "공공데이터포털 식품 영양정보를 비교해 상황에 맞는 음식을 골랐습니다."
    )
    return {
        "summary": summary,
        "reason": reason,
        "queries": queries,
        "remaining_calories": remaining_calories,
        "activity_calorie_credit": activity_calorie_credit,
        "total_carbohydrate": total_carbohydrate,
        "total_sodium": total_sodium,
        "high_carbohydrate": high_carbohydrate,
        "high_sodium": high_sodium,
        "is_active": is_active,
        "diet_goal": diet_goal.goal,
    }


def _food_reason(food: dict[str, Any], conditions: dict[str, Any]) -> str:
    details = []
    if food.get("protein") is not None and food["protein"] >= 20:
        details.append("단백질이 충분해 활동 후 식사에 적합합니다")
    if conditions["high_carbohydrate"] and food.get("carbohydrate") is not None:
        if food["carbohydrate"] <= 20:
            details.append("탄수화물이 낮은 편입니다")
    if conditions["high_sodium"] and food.get("sodium") is not None:
        if food["sodium"] <= 600:
            details.append("나트륨이 비교적 낮습니다")
    if conditions["diet_goal"] == "weight_loss" and food.get("calories") is not None:
        if food["calories"] <= conditions["remaining_calories"]:
            details.append("남은 목표 열량 안에서 선택할 수 있습니다")
    if conditions["summary"].find("덥고") >= 0:
        details.append("더운 날 부담이 적은 메뉴입니다")
    return "; ".join(details) or "공공데이터포털 식품 영양정보와 오늘의 상황을 반영한 선택입니다"


async def recommend_foods(conditions: dict[str, Any]) -> list[RecommendedFood]:
    """조건에 맞는 공공데이터포털 식품 영양정보를 정렬해 추천합니다."""
    candidates = []
    for query in conditions["queries"]:
        candidates.extend(await search_foods(query, limit=8))

    unique = {}
    for food in candidates:
        unique.setdefault(food["food_name"], food)

    def score(food: dict[str, Any]) -> float:
        value = 0.0
        calories = food.get("calories")
        protein = food.get("protein")
        carbs = food.get("carbohydrate")
        sodium = food.get("sodium")
        if calories is not None and calories <= conditions["remaining_calories"]:
            value += 2
        elif calories is not None and conditions["diet_goal"] == "weight_loss":
            value -= 2
        if protein is not None and protein >= 20:
            value += 2
        if conditions["high_carbohydrate"] and carbs is not None:
            value += 2 if carbs <= 20 else -1
        if conditions["high_sodium"] and sodium is not None:
            value += 2 if sodium <= 600 else -2
        if conditions["is_active"] and protein is not None and protein >= 25:
            value += 1
        return value

    ranked = sorted(unique.values(), key=score, reverse=True)[:5]
    return [
        RecommendedFood(
            food_name=food["food_name"],
            calories=food.get("calories"),
            carbohydrate=food.get("carbohydrate"),
            protein=food.get("protein"),
            fat=food.get("fat"),
            sodium=food.get("sodium"),
            reason=_food_reason(food, conditions),
        )
        for food in ranked
    ]


async def make_recommendation(
    weather: WeatherInput,
    activity: ActivityInput,
    diet_logs: list[DietLogInput],
    diet_goal: DietGoal,
    weather_history: list[dict[str, Any]],
) -> tuple[dict[str, Any], list[RecommendedFood]]:
    """추천 조건 구성, 음식 검색, 설명 생성을 한 번에 실행합니다."""
    conditions = build_recommendation_conditions(
        weather, activity, diet_logs, diet_goal, weather_history
    )
    foods = await recommend_foods(conditions)
    conditions["reason"] = await explain_recommendation(
        conditions["summary"], conditions["reason"]
    )
    return conditions, foods