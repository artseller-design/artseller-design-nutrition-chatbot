"""Nutrient summaries for a user's meal entries."""

from datetime import date, datetime, time, timedelta, timezone

from fastapi import APIRouter, HTTPException, Query, status

from app.firebase import get_firestore
from app.models import AnalysisSummary

router = APIRouter(prefix="/users/{user_id}/analysis", tags=["영양 분석"])


def _build_summary(user_id: str, start_date: date, end_date: date) -> AnalysisSummary:
    if start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start_date는 end_date보다 늦을 수 없습니다.",
        )
    db = get_firestore()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firestore가 연결되지 않았습니다. 서비스 계정 설정을 확인하세요.",
        )

    start_timestamp = datetime.combine(start_date, time.min, tzinfo=timezone.utc)
    end_exclusive = datetime.combine(
        end_date + timedelta(days=1), time.min, tzinfo=timezone.utc
    )
    records = (
        db.collection("users")
        .document(user_id)
        .collection("food_entries")
        .where("recorded_at", ">=", start_timestamp)
        .where("recorded_at", "<", end_exclusive)
        .stream()
    )

    totals: dict[str, float] = {}
    daily_meals: dict[str, set[str]] = {}
    food_entry_count = 0
    for document in records:
        record = document.to_dict() or {}
        recorded_at = record.get("recorded_at")
        if isinstance(recorded_at, datetime):
            if recorded_at.tzinfo is None:
                recorded_at = recorded_at.replace(tzinfo=timezone.utc)
            day = recorded_at.astimezone(timezone.utc).date().isoformat()
        else:
            day = str(recorded_at)[:10]
        daily_meals.setdefault(day, set()).add(
            str(record.get("meal_id") or document.id)
        )
        food_entry_count += 1
        nutrients = record.get("nutrients") or {}
        for nutrient, amount in nutrients.items():
            if isinstance(amount, (int, float)):
                totals[nutrient] = totals.get(nutrient, 0.0) + float(amount)

    daily_counts = {day: len(meals) for day, meals in daily_meals.items()}
    entry_count = sum(daily_counts.values())
    day_count = (end_date - start_date).days + 1
    notes = ["일평균은 기록이 없는 날도 포함한 요청 기간 전체 날짜를 기준으로 계산했습니다."]
    if entry_count == 0:
        notes.append("해당 기간에 식사 기록이 없습니다.")

    return AnalysisSummary(
        user_id=user_id,
        period_start=start_date,
        period_end=end_date,
        entry_count=entry_count,
        food_entry_count=food_entry_count,
        daily_nutrient_averages={
            key: round(value / day_count, 2) for key, value in totals.items()
        },
        nutrient_totals={key: round(value, 2) for key, value in totals.items()},
        daily_entry_counts=dict(sorted(daily_counts.items())),
        notes=notes,
        generated_at=datetime.now(timezone.utc),
    )


@router.get("/summary", response_model=AnalysisSummary)
def get_analysis_summary(
    user_id: str,
    start_date: date = Query(..., description="포함하는 시작 날짜 (YYYY-MM-DD)"),
    end_date: date = Query(..., description="포함하는 종료 날짜 (YYYY-MM-DD)"),
):
    summary = _build_summary(user_id, start_date, end_date)
    db = get_firestore()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firestore가 연결되지 않았습니다. 서비스 계정 설정을 확인하세요.",
        )
    period_id = f"{start_date.isoformat()}_{end_date.isoformat()}"
    (
        db.collection("users")
        .document(user_id)
        .collection("analysis_summaries")
        .document(period_id)
        .set(summary.model_dump(mode="json"))
    )
    return summary


@router.get("/summaries/{period_id}", response_model=AnalysisSummary)
def get_saved_summary(user_id: str, period_id: str):
    db = get_firestore()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firestore가 연결되지 않았습니다. 서비스 계정 설정을 확인하세요.",
        )
    document = (
        db.collection("users")
        .document(user_id)
        .collection("analysis_summaries")
        .document(period_id)
        .get()
    )
    if not document.exists:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="저장된 분석 요약을 찾을 수 없습니다.",
        )
    return document.to_dict()
