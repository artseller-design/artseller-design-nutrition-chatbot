"""API 요청과 응답에서 사용하는 Pydantic 모델입니다."""

from datetime import date, datetime, timezone
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, Field, FiniteFloat


def _now() -> datetime:
    return datetime.now(timezone.utc)


class MealRecord(BaseModel):
    user_id: str = Field(min_length=1)
    food_name: str = Field(min_length=1)
    calories: float = Field(ge=0)
    meal_type: str | None = None
    recorded_at: datetime = Field(default_factory=_now)


NutrientAmount = Annotated[FiniteFloat, Field(ge=0)]


class FoodEntryCreate(BaseModel):
    """A meal and the nutrient totals for the portion the user consumed."""

    model_config = ConfigDict(str_strip_whitespace=True)

    recorded_at: datetime
    meal_type: str = Field(min_length=1, max_length=40)
    meal_id: str | None = None
    food_name: str = Field(min_length=1, max_length=200)
    amount: FiniteFloat = Field(gt=0)
    unit: str = Field(min_length=1, max_length=30)
    nutrients: dict[str, NutrientAmount] = Field(default_factory=dict)
    memo: str = Field(default="", max_length=2000)
    source: str = Field(default="manual", max_length=40)


class FoodEntryMealItem(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    food_name: str = Field(min_length=1, max_length=200)
    amount: FiniteFloat = Field(gt=0)
    unit: str = Field(min_length=1, max_length=30)
    nutrients: dict[str, NutrientAmount] = Field(default_factory=dict)
    source: str = Field(default="manual", max_length=40)


class FoodEntryMealCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    recorded_at: datetime
    meal_type: str = Field(min_length=1, max_length=40)
    foods: list[FoodEntryMealItem] = Field(min_length=1, max_length=50)
    memo: str = Field(default="", max_length=2000)


class FoodEntry(FoodEntryCreate):
    id: str
    created_at: datetime


class AnalysisSummary(BaseModel):
    user_id: str
    period_start: date
    period_end: date
    entry_count: int
    food_entry_count: int = 0
    daily_nutrient_averages: dict[str, float]
    nutrient_totals: dict[str, float]
    daily_entry_counts: dict[str, int]
    notes: list[str]
    generated_at: datetime


class DataRecordCreate(BaseModel):
    """One dated numeric observation and its optional note."""

    model_config = ConfigDict(str_strip_whitespace=True)

    date: date
    value: FiniteFloat = Field(ge=0)
    memo: str = Field(default="", max_length=2000)


class DataRecord(DataRecordCreate):
    id: str
    user_id: str
    created_at: datetime
    updated_at: datetime


class DataSummary(BaseModel):
    user_id: str
    period_start: date
    period_end: date
    count: int
    average: float | None
    median: float | None
    standard_deviation: float | None
    maximum: float | None
    minimum: float | None
    trend: dict[str, Any]
    generated_at: datetime


class ConversationMessage(BaseModel):
    role: Literal["user", "assistant"] = "user"
    content: str = Field(min_length=1, max_length=12000)
    created_at: datetime = Field(default_factory=_now)


class ConversationCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    user_id: str = Field(min_length=1, max_length=128)
    title: str = Field(default="새 대화", min_length=1, max_length=160)
    messages: list[ConversationMessage] = Field(default_factory=list, max_length=100)


class ChatRequest(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)

    user_id: str = Field(min_length=1, max_length=128)
    message: str = Field(min_length=1, max_length=12000)
    conversation_id: str | None = None


class WeatherRecord(BaseModel):
    user_id: str = Field(min_length=1)
    city: str = Field(min_length=1)
    temperature_c: float
    condition: str = "unknown"
    humidity_percent: float | None = Field(default=None, ge=0, le=100)
    precipitation_mm: float | None = Field(default=None, ge=0)
    observation_date: date | None = None
    recorded_at: datetime = Field(default_factory=_now)


class ActivityRecord(BaseModel):
    user_id: str = Field(min_length=1)
    steps: int = Field(default=0, ge=0)
    exercise_minutes: int = Field(default=0, ge=0)
    recorded_at: datetime = Field(default_factory=_now)


class RecommendationRequest(BaseModel):
    user_id: str = Field(min_length=1)
    city: str | None = None
    daily_calorie_target: float = Field(default=1800, gt=0)


class RecommendationResponse(BaseModel):
    id: str | None = None
    user_id: str
    daily_calorie_target: float
    calories_consumed: float
    calories_remaining: float
    situation: list[str]
    food_queries: list[str]
    foods: list[dict[str, Any]]
    rationale: str
    created_at: datetime = Field(default_factory=_now)


class KmaWeatherSyncRequest(BaseModel):
    """기상청 관측소와 동기화할 과거 기간."""

    user_id: str = Field(min_length=1)
    station_id: int = Field(ge=1, le=999)
    start_date: date
    end_date: date


class WeatherCsvRecommendationRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    target_date: date
    csv_text: str = Field(min_length=1, max_length=5_000_000)


class SavedWeatherRecommendationRequest(BaseModel):
    user_id: str = Field(min_length=1, max_length=128)
    target_date: date


class DietLogInput(BaseModel):
    """사용자가 먹은 음식 한 건과 영양 정보."""

    user_id: str = Field(min_length=1)
    date: date
    food_name: str = Field(min_length=1)
    calories: float = Field(default=0, ge=0)
    carbohydrate: float = Field(default=0, ge=0)
    protein: float = Field(default=0, ge=0)
    fat: float = Field(default=0, ge=0)
    sodium: float = Field(default=0, ge=0)
    memo: str | None = None


class WeatherInput(BaseModel):
    """한 날짜의 기온, 습도, 날씨 상태."""

    temperature: float
    humidity: float = Field(ge=0, le=100)
    condition: str = "unknown"
    precipitation_mm: float = Field(default=0, ge=0)


class WeatherLogInput(WeatherInput):
    user_id: str = Field(min_length=1)
    date: date


class ActivityInput(BaseModel):
    """걸음 수와 운동 강도."""

    steps: int = Field(default=0, ge=0)
    exercise_minutes: int = Field(default=0, ge=0)
    intensity: Literal["low", "moderate", "high"] = "low"


class ActivityLogInput(ActivityInput):
    user_id: str = Field(min_length=1)
    date: date


class DietGoal(BaseModel):
    target_calories: float = Field(gt=0)
    goal: str = "weight_loss"


class RecommendRequest(BaseModel):
    """날씨·활동량과 목표를 포함하는 추천 요청."""

    user_id: str = Field(min_length=1)
    date: date
    weather: WeatherInput
    activity: ActivityInput
    diet_goal: DietGoal


class RecommendedFood(BaseModel):
    food_name: str
    calories: float | None = None
    carbohydrate: float | None = None
    protein: float | None = None
    fat: float | None = None
    sodium: float | None = None
    reason: str


class RecommendResponse(BaseModel):
    situation_summary: str
    recommendation_reason: str
    recommended_foods: list[RecommendedFood]
