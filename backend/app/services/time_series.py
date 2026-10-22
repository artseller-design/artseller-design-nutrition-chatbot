"""Business logic for dated numeric observations and their summaries."""

from datetime import date, datetime, timezone
from uuid import uuid4

from fastapi import HTTPException, status

from app.models import DataRecordCreate, DataSummary


def _user_records(db, user_id: str):
    return db.collection("data").where("user_id", "==", user_id)


def _serialize(document) -> dict:
    return {"id": document.id, **(document.to_dict() or {})}


def create_data_record(db, user_id: str, payload: DataRecordCreate) -> dict:
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
    db.collection("data").document(record_id).set(data)
    return {"id": record_id, **data}


def list_data_records(
    db,
    user_id: str,
    start_date: date | None,
    end_date: date | None,
    limit: int,
) -> list[dict]:
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=422, detail="start_date는 end_date보다 늦을 수 없습니다.")
    records = [_serialize(document) for document in _user_records(db, user_id).limit(10000).stream()]
    if start_date:
        records = [record for record in records if record.get("date", "") >= start_date.isoformat()]
    if end_date:
        records = [record for record in records if record.get("date", "") <= end_date.isoformat()]
    records.sort(
        key=lambda item: (item.get("date", ""), str(item.get("created_at", ""))),
        reverse=True,
    )
    return records[:limit]


def update_data_record(
    db, user_id: str, record_id: str, payload: DataRecordCreate
) -> dict:
    reference = db.collection("data").document(record_id)
    snapshot = reference.get()
    existing = snapshot.to_dict() or {}
    if not snapshot.exists or existing.get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="데이터를 찾을 수 없습니다.")
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


def delete_data_record(db, user_id: str, record_id: str) -> None:
    reference = db.collection("data").document(record_id)
    snapshot = reference.get()
    if not snapshot.exists or (snapshot.to_dict() or {}).get("user_id") != user_id:
        raise HTTPException(status_code=404, detail="데이터를 찾을 수 없습니다.")
    reference.delete()


def summarize_data_records(
    db, user_id: str, start_date: date, end_date: date
) -> DataSummary:
    documents = _user_records(db, user_id).limit(10000).stream()
    records = [_serialize(document) for document in documents]
    return build_data_summary(user_id, start_date, end_date, records)


def build_data_summary(
    user_id: str,
    start_date: date,
    end_date: date,
    records: list[dict],
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

    records = sorted(
        (
            record
            for record in records
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