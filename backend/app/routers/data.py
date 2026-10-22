"""CRUD and statistics for dated numeric observations."""

from datetime import date, datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, Query, Response, status

from app.firebase import get_firestore
from app.models import DataRecord, DataRecordCreate, DataSummary
from app.services.time_series import (
    create_data_record as create_record,
    delete_data_record as delete_record,
    list_data_records as list_records,
    summarize_data_records,
    update_data_record as update_record,
)

router = APIRouter(prefix="/api/data", tags=["시계열 데이터"])


def _database():
    db = get_firestore()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firestore가 연결되지 않았습니다. FIREBASE_SERVICE_ACCOUNT_JSON 설정을 확인하세요.",
        )
    return db


def calculate_data_summary(
    user_id: str, start_date: date, end_date: date
) -> DataSummary:
    return summarize_data_records(_database(), user_id, start_date, end_date)


@router.post("", response_model=DataRecord, status_code=status.HTTP_201_CREATED)
def create_data_record(
    payload: DataRecordCreate,
    user_id: str = Query(min_length=1, max_length=128),
):
    return create_record(_database(), user_id, payload)


@router.get("", response_model=list[DataRecord])
def list_data_records(
    user_id: str = Query(min_length=1, max_length=128),
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(default=500, ge=1, le=10000),
):
    return list_records(_database(), user_id, start_date, end_date, limit)


@router.put("/{record_id}", response_model=DataRecord)
def update_data_record(
    record_id: str,
    payload: DataRecordCreate,
    user_id: str = Query(min_length=1, max_length=128),
):
    return update_record(_database(), user_id, record_id, payload)


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_data_record(
    record_id: str,
    user_id: str = Query(min_length=1, max_length=128),
):
    delete_record(_database(), user_id, record_id)


@router.get("/summary", response_model=DataSummary)
def get_data_summary(
    user_id: str = Query(min_length=1, max_length=128),
    start_date: date | None = None,
    end_date: date | None = None,
):
    today = datetime.now(timezone.utc).date()
    period_start = start_date or today - timedelta(days=29)
    period_end = end_date or today
    if (start_date is None) != (end_date is None):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start_date와 end_date를 함께 지정하세요.",
        )
    return calculate_data_summary(user_id, period_start, period_end)
