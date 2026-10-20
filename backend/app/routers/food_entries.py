"""Meal entry storage and date-range retrieval."""

from datetime import date, datetime, time, timedelta, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Response, status
from firebase_admin import firestore

from app.firebase import get_firestore
from app.models import FoodEntry, FoodEntryCreate, FoodEntryMealCreate

router = APIRouter(prefix="/users/{user_id}/food-entries", tags=["식사 기록"])
CHAT_FOOD_DETAIL_LIMIT = 100
CHAT_NUTRIENT_KEYS = (
    "calories_kcal",
    "protein_g",
    "carbohydrate_g",
    "fat_g",
    "sugar_g",
    "sodium_mg",
)


def _entries_collection(user_id: str):
    db = get_firestore()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firestore가 연결되지 않았습니다. 서비스 계정 설정을 확인하세요.",
        )
    return db.collection("users").document(user_id).collection("food_entries")


def _firestore_or_503():
    db = get_firestore()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firestore가 연결되지 않았습니다. 서비스 계정 설정을 확인하세요.",
        )
    return db


def _utc_timestamp(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def build_food_chat_summary(user_id: str, start_date: date, end_date: date) -> dict:
    """Build a bounded, period-specific meal summary for AI chat context."""
    start_timestamp = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    end_exclusive = datetime.combine(
        end_date + timedelta(days=1), time.min, tzinfo=timezone.utc
    )
    records = _entries_collection(user_id).where(
        "recorded_at", ">=", start_timestamp
    ).where("recorded_at", "<", end_exclusive).stream()

    totals = {key: 0.0 for key in CHAT_NUTRIENT_KEYS}
    daily: dict[str, dict] = {}
    foods = []
    meal_ids: set[tuple[str, str]] = set()
    food_count = 0
    for document in records:
        record = document.to_dict() or {}
        recorded_at = record.get("recorded_at")
        if isinstance(recorded_at, datetime):
            recorded_at = _utc_timestamp(recorded_at)
            day = recorded_at.date().isoformat()
            recorded_at_text = recorded_at.isoformat()
        else:
            recorded_at_text = str(recorded_at or "")
            day = recorded_at_text[:10]
        meal_id = str(record.get("meal_id") or document.id)
        meal_ids.add((day, meal_id))
        food_count += 1

        day_summary = daily.setdefault(
            day,
            {
                "meal_ids": set(),
                "food_count": 0,
                "nutrients": {key: 0.0 for key in CHAT_NUTRIENT_KEYS},
            },
        )
        day_summary["meal_ids"].add(meal_id)
        day_summary["food_count"] += 1

        nutrients = record.get("nutrients") or {}
        for key in CHAT_NUTRIENT_KEYS:
            value = nutrients.get(key)
            if isinstance(value, (int, float)):
                totals[key] += float(value)
                day_summary["nutrients"][key] += float(value)

        foods.append(
            {
                "date": day,
                "recorded_at": recorded_at_text,
                "meal_id": meal_id,
                "meal_type": str(record.get("meal_type") or ""),
                "food_name": str(record.get("food_name") or ""),
                "amount": record.get("amount"),
                "unit": str(record.get("unit") or ""),
                "nutrients": {
                    key: float(nutrients[key])
                    for key in CHAT_NUTRIENT_KEYS
                    if isinstance(nutrients.get(key), (int, float))
                },
            }
        )

    foods.sort(key=lambda food: food["recorded_at"])
    daily_summaries = [
        {
            "date": day,
            "meal_count": len(summary["meal_ids"]),
            "food_count": summary["food_count"],
            "nutrients": {
                key: round(value, 2)
                for key, value in summary["nutrients"].items()
            },
        }
        for day, summary in sorted(daily.items())
    ]
    return {
        "meal_count": len(meal_ids),
        "food_count": food_count,
        "nutrient_totals": {key: round(value, 2) for key, value in totals.items()},
        "daily_summaries": daily_summaries,
        "food_details": foods[-CHAT_FOOD_DETAIL_LIMIT:],
        "food_details_truncated": food_count > CHAT_FOOD_DETAIL_LIMIT,
    }


@router.post("", response_model=FoodEntry, status_code=status.HTTP_201_CREATED)
def create_food_entry(user_id: str, payload: FoodEntryCreate):
    collection = _entries_collection(user_id)
    entry_id = str(uuid4())
    created_at = datetime.now(timezone.utc)
    data = payload.model_dump()
    data["recorded_at"] = _utc_timestamp(payload.recorded_at)
    data["meal_id"] = data.get("meal_id") or str(uuid4())
    data["created_at"] = created_at
    collection.document(entry_id).set(data)
    return {"id": entry_id, **data}


@router.post(
    "/meal",
    response_model=list[FoodEntry],
    status_code=status.HTTP_201_CREATED,
)
def create_food_entry_meal(user_id: str, payload: FoodEntryMealCreate):
    db = _firestore_or_503()
    collection = db.collection("users").document(user_id).collection("food_entries")
    meal_id = str(uuid4())
    created_at = datetime.now(timezone.utc)
    recorded_at = _utc_timestamp(payload.recorded_at)
    batch = db.batch()
    entries = []
    for food in payload.foods:
        entry_id = str(uuid4())
        data = {
            "recorded_at": recorded_at,
            "meal_type": payload.meal_type,
            "meal_id": meal_id,
            "food_name": food.food_name,
            "amount": food.amount,
            "unit": food.unit,
            "nutrients": food.nutrients,
            "memo": payload.memo,
            "source": food.source,
            "created_at": created_at,
        }
        batch.set(collection.document(entry_id), data)
        entries.append({"id": entry_id, **data})
    batch.commit()
    return entries


@router.get("", response_model=list[FoodEntry])
def list_food_entries(
    user_id: str,
    start_date: date | None = Query(default=None, description="포함하는 시작 날짜 (YYYY-MM-DD)"),
    end_date: date | None = Query(default=None, description="포함하는 종료 날짜 (YYYY-MM-DD)"),
    limit: int = Query(default=100, ge=1, le=500),
):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date는 end_date보다 늦을 수 없습니다.")

    query: Any = _entries_collection(user_id)
    if start_date:
        query = query.where(
            "recorded_at",
            ">=",
            datetime.combine(start_date, time.min, tzinfo=timezone.utc),
        )
    if end_date:
        end_exclusive = datetime.combine(
            end_date + timedelta(days=1), time.min, tzinfo=timezone.utc
        )
        query = query.where("recorded_at", "<", end_exclusive)
    docs = query.order_by(
        "recorded_at", direction=firestore.Query.DESCENDING
    ).limit(limit).stream()
    return [{"id": doc.id, **doc.to_dict()} for doc in docs]


@router.delete(
    "/{entry_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_food_entry(user_id: str, entry_id: str):
    reference = _entries_collection(user_id).document(entry_id)
    if not reference.get().exists:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="식사 기록을 찾을 수 없습니다.")
    reference.delete()


@router.delete(
    "/meals/{meal_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_food_entry_meal(user_id: str, meal_id: str):
    db = _firestore_or_503()
    collection = db.collection("users").document(user_id).collection("food_entries")
    documents = list(collection.where("meal_id", "==", meal_id).stream())
    if not documents:
        legacy_entry = collection.document(meal_id).get()
        if not legacy_entry.exists:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="삭제할 한 끼 식사 기록을 찾을 수 없습니다.",
            )
        documents = [legacy_entry]

    batch = db.batch()
    for document in documents:
        batch.delete(collection.document(document.id))
    batch.commit()
