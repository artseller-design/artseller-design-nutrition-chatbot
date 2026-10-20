"""CRUD and statistics for dated numeric observations."""

from datetime import date, datetime, timedelta, timezone
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Query, Response, status

from app.firebase import get_firestore
from app.models import DataRecord, DataRecordCreate, DataSummary

router = APIRouter(prefix="/api/data", tags=["시계열 데이터"])


def _database():
    db = get_firestore()
    if db is None:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Firestore가 연결되지 않았습니다. FIREBASE_SERVICE_ACCOUNT_JSON 설정을 확인하세요.",
        )
    return db


def _user_records(user_id: str):
    return _database().collection("data").where("user_id", "==", user_id)


def _serialize(document) -> dict:
    return {"id": document.id, **(document.to_dict() or {})}


def calculate_data_summary(
    user_id: str, start_date: date, end_date: date
) -> DataSummary:
    if start_date > end_date:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="start_date는 end_date보다 늦을 수 없습니다.",
        )
    if (end_date - start_date).days > 3660:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="요약 기간은 최대 10년까지 조회할 수 있습니다.",
        )

    documents = _user_records(user_id).limit(10000).stream()
    records = sorted(
        (
            record
            for record in (_serialize(document) for document in documents)
            if start_date.isoformat() <= record.get("date", "") <= end_date.isoformat()
        ),
        key=lambda item: (item.get("date", ""), str(item.get("created_at", ""))),
    )
    values = [float(record["value"]) for record in records]

    if len(values) >= 4:
        window_size = min(7, len(values) // 2)
        previous_values = values[-2 * window_size : -window_size]
        recent_values = values[-window_size:]
        previous_average = sum(previous_values) / len(previous_values)
        recent_average = sum(recent_values) / len(recent_values)
        change = recent_average - previous_average
        change_percent = change / abs(previous_average) * 100 if previous_average else None
        threshold = max(abs(previous_average) * 0.01, 0.01)
        direction = (
            "increase"
            if change > threshold
            else "decrease"
            if change < -threshold
            else "stable"
        )
        trend = {
            "direction": direction,
            "recent_average": round(recent_average, 2),
            "previous_average": round(previous_average, 2),
            "change": round(change, 2),
            "change_percent": round(change_percent, 2) if change_percent is not None else None,
            "compared_points": {
                "previous": len(previous_values),
                "recent": len(recent_values),
            },
        }
    else:
        trend = {
            "direction": "insufficient_data",
            "recent_average": None,
            "previous_average": None,
            "change": None,
            "change_percent": None,
            "compared_points": {"previous": 0, "recent": len(values)},
        }

    return DataSummary(
        user_id=user_id,
        period_start=start_date,
        period_end=end_date,
        count=len(values),
        average=round(sum(values) / len(values), 2) if values else None,
        maximum=max(values) if values else None,
        minimum=min(values) if values else None,
        trend=trend,
        generated_at=datetime.now(timezone.utc),
    )


@router.post("", response_model=DataRecord, status_code=status.HTTP_201_CREATED)
def create_data_record(
    payload: DataRecordCreate,
    user_id: str = Query(min_length=1, max_length=128),
):
    collection = _database().collection("data")
    record_id = str(uuid4())
    now = datetime.now(timezone.utc)
    data = {
        "user_id": user_id,
        "date": payload.date.isoformat(),
        "value": payload.value,
        "memo": payload.memo,
        "created_at": now,
        "updated_at": now,
    }
    collection.document(record_id).set(data)
    return {"id": record_id, **data}


@router.get("", response_model=list[DataRecord])
def list_data_records(
    user_id: str = Query(min_length=1, max_length=128),
    start_date: date | None = None,
    end_date: date | None = None,
    limit: int = Query(default=500, ge=1, le=10000),
):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date는 end_date보다 늦을 수 없습니다.")
    query = _user_records(user_id)
    records = [
        _serialize(document)
        for document in query.limit(10000).stream()
    ]
    if start_date:
        records = [record for record in records if record.get("date", "") >= start_date.isoformat()]
    if end_date:
        records = [record for record in records if record.get("date", "") <= end_date.isoformat()]
    records.sort(
        key=lambda item: (item.get("date", ""), str(item.get("created_at", ""))),
        reverse=True,
    )
    return records[:limit]


@router.put("/{record_id}", response_model=DataRecord)
def update_data_record(
    record_id: str,
    payload: DataRecordCreate,
    user_id: str = Query(min_length=1, max_length=128),
):
    db = _database()
    reference = db.collection("data").document(record_id)
    snapshot = reference.get()
    if not snapshot.exists or snapshot.to_dict().get("user_id") != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="데이터를 찾을 수 없습니다.")
    existing = snapshot.to_dict()
    data = {
        "user_id": user_id,
        "date": payload.date.isoformat(),
        "value": payload.value,
        "memo": payload.memo,
        "created_at": existing["created_at"],
        "updated_at": datetime.now(timezone.utc),
    }
    reference.set(data)
    return {"id": record_id, **data}


@router.delete("/{record_id}", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def delete_data_record(
    record_id: str,
    user_id: str = Query(min_length=1, max_length=128),
):
    reference = _database().collection("data").document(record_id)
    snapshot = reference.get()
    if not snapshot.exists or snapshot.to_dict().get("user_id") != user_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="데이터를 찾을 수 없습니다.")
    reference.delete()


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
