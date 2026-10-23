"""Generate an explicitly synthetic 100-day meal history for time-series work."""

from __future__ import annotations

import argparse
import json
import random
import sys
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

SEOUL = timezone(timedelta(hours=9), "KST")
ROOT = Path(__file__).resolve().parents[2]
OUTPUT = ROOT / "data" / "synthetic_meals_100days.json"
USER_ID = "demo-user"

# kcal, protein, carbohydrate, fat, sugar, sodium, serving grams
FOODS = {
    "breakfast": [
        ("\uc6b0\uc720\uc640 \ubc14\ub098\ub098 \uc624\ud2b8\ubc00", (410, 17, 66, 10, 18, 190, 330)),
        ("\ud1b5\ubc00 \ud1a0\uc2a4\ud2b8\uc640 \ub2ec\uac40", (390, 21, 43, 15, 7, 520, 240)),
        ("\ud604\ubbf8\ubc25\u00b7\uacc4\ub780\ub9d0\uc774\u00b7\uae40", (455, 19, 66, 12, 4, 610, 350)),
        ("\ub450\ubd80\ucc44\uc18c\uc8fd", (365, 16, 54, 9, 5, 480, 400)),
        ("\uadf8\ub9ad\uc694\uac70\ud2b8\u00b7\uacac\uacfc\u00b7\uacfc\uc77c", (385, 23, 48, 12, 20, 130, 300)),
        ("\uace0\uad6c\ub9c8\u00b7\uc0b6\uc740 \ub2ec\uac40\u00b7\uc6b0\uc720", (420, 22, 58, 12, 16, 260, 360)),
    ],
    "lunch": [
        ("\ucc44\uc18c \ube44\ube54\ubc25", (665, 23, 96, 18, 13, 890, 480)),
        ("\ub2ed\uac00\uc2b4\uc0b4 \ud604\ubbf8 \ub36e\ubc25", (690, 43, 83, 16, 8, 720, 450)),
        ("\uc21c\ub450\ubd80\ucc0c\uac1c\uc640 \ubc25", (650, 29, 82, 20, 7, 1080, 600)),
        ("\ub3fc\uc9c0\ubd88\uace0\uae30 \uc30c\ubc25", (745, 36, 91, 24, 14, 970, 520)),
        ("\uc5f0\uc5b4\uad6c\uc774\uc640 \uc7a1\uace1\ubc25", (700, 36, 82, 23, 6, 650, 430)),
        ("\ucc44\uc18c \uce74\ub808\ub77c\uc774\uc2a4", (680, 18, 103, 19, 12, 830, 470)),
        ("\uae40\ubc25\uacfc \uc5b4\ubb35\uad6d", (635, 22, 91, 17, 8, 1120, 500)),
        ("\ucf69\ub098\ubb3c\uad6d\ubc25", (620, 27, 89, 13, 4, 1050, 650)),
    ],
    "dinner": [
        ("\uace0\ub4f1\uc5b4\uad6c\uc774\uc640 \ud604\ubbf8\ubc25", (665, 35, 74, 25, 5, 760, 430)),
        ("\ub2ed\uace0\uae30 \ucc44\uc18c\uc0d0\ub7ec\ub4dc\uc640 \ube75", (555, 39, 54, 19, 11, 680, 420)),
        ("\ubc84\uc12f \ub450\ubd80 \ub36e\ubc25", (585, 25, 78, 17, 8, 720, 440)),
        ("\uae40\uce58\ubcf6\uc74c\ubc25\uacfc \ub2ec\uac40", (700, 22, 96, 23, 9, 1040, 420)),
        ("\ub3fc\uc9c0\uace0\uae30 \uc218\uc721\uacfc \uc30c\ucc44\uc18c", (690, 42, 53, 31, 6, 860, 390)),
        ("\uc18c\uace0\uae30 \ucc44\uc18c\ubcf6\uc74c\uacfc \ubc25", (710, 34, 78, 26, 10, 890, 450)),
        ("\ub4e4\uae68 \ubc84\uc12f\uce7c\uad6d\uc218", (640, 19, 91, 21, 5, 980, 600)),
        ("\uc0c8\uc6b0 \ud1a0\ub9c8\ud1a0 \ud30c\uc2a4\ud0c0", (675, 31, 88, 20, 12, 790, 470)),
    ],
}


def generate_records(today: date | None = None) -> dict:
    today = today or datetime.now(SEOUL).date()
    start = today - timedelta(days=99)
    rng = random.Random(20261023)
    records = []
    for day_offset in range(100):
        day = start + timedelta(days=day_offset)
        trend = 1.035 - 0.00055 * day_offset
        weekend = 1.07 if day.weekday() >= 5 else 1.0
        for meal_type, hour in (("breakfast", 8), ("lunch", 12), ("dinner", 19)):
            food_name, base = rng.choice(FOODS[meal_type])
            factor = trend * weekend * rng.uniform(0.94, 1.07)
            nutrients = {
                "calories_kcal": round(base[0] * factor, 1),
                "protein_g": round(base[1] * factor, 1),
                "carbohydrate_g": round(base[2] * factor, 1),
                "fat_g": round(base[3] * factor, 1),
                "sugar_g": round(base[4] * factor, 1),
                "sodium_mg": round(base[5] * factor, 1),
            }
            recorded_at = datetime.combine(day, time(hour, rng.choice((0, 15, 30, 45))), tzinfo=SEOUL)
            records.append({
                "id": f"synthetic-{day.isoformat()}-{meal_type}",
                "user_id": USER_ID,
                "recorded_at": recorded_at.isoformat(),
                "created_at": recorded_at.isoformat(),
                "meal_type": meal_type,
                "meal_id": f"synthetic-{day.isoformat()}-{meal_type}",
                "food_name": food_name,
                "amount": round(base[6] * factor),
                "unit": "g",
                "nutrients": nutrients,
                "memo": "\uc2dc\uacc4\uc5f4 \ubd84\uc11d\uc6a9 \uac00\uc0c1 \uc2dd\uc0ac \uae30\ub85d",
                "source": "synthetic",
            })
    return {
        "metadata": {
            "synthetic": True,
            "user_id": USER_ID,
            "start_date": start.isoformat(),
            "end_date": today.isoformat(),
            "days": 100,
            "meal_count": len(records),
            "meals_per_day": 3,
            "note": "\ubaa8\ub4e0 \uae30\ub85d\uc740 \uac00\uc0c1 \uc2dd\uc0ac \ub370\uc774\ud130\uc785\ub2c8\ub2e4.",
        },
        "records": records,
    }


def write_to_firestore(records: list[dict]) -> None:
    sys.path.insert(0, str(ROOT / "backend"))
    from app.firebase import get_firestore

    db = get_firestore()
    if db is None:
        raise RuntimeError("Firestore가 연결되지 않았습니다. backend/.env의 Firebase 설정을 확인하세요.")
    collection = db.collection("users").document(USER_ID).collection("food_entries")
    for offset in range(0, len(records), 400):
        batch = db.batch()
        for record in records[offset : offset + 400]:
            data = {key: value for key, value in record.items() if key not in {"id", "user_id"}}
            data["recorded_at"] = datetime.fromisoformat(data["recorded_at"])
            data["created_at"] = datetime.fromisoformat(data["created_at"])
            batch.set(collection.document(record["id"]), data)
        batch.commit(timeout=10, retry=None)

    start = date.fromisoformat(records[0]["recorded_at"][:10])
    end = date.fromisoformat(records[-1]["recorded_at"][:10])
    daily_totals: dict[str, float] = {}
    for snapshot in collection.stream():
        item = snapshot.to_dict() or {}
        recorded_at = item.get("recorded_at")
        if not isinstance(recorded_at, datetime):
            continue
        day = recorded_at.astimezone(SEOUL).date().isoformat()
        if start.isoformat() <= day <= end.isoformat():
            calories = (item.get("nutrients") or {}).get("calories_kcal")
            if isinstance(calories, (int, float)):
                daily_totals[day] = daily_totals.get(day, 0) + float(calories)

    data_collection = db.collection("data")
    existing_points: dict[str, list] = {}
    for snapshot in data_collection.where("user_id", "==", USER_ID).stream():
        item = snapshot.to_dict() or {}
        day = str(item.get("date") or "")
        if snapshot.id.startswith(f"demo-calories-{USER_ID}-") and start.isoformat() <= day <= end.isoformat():
            existing_points.setdefault(day, []).append(snapshot.reference)

    batch = db.batch()
    now = datetime.now(timezone.utc)
    current_day = start
    while current_day <= end:
        day = current_day.isoformat()
        total = round(daily_totals.get(day, 0), 1)
        references = existing_points.get(day, [])
        if references:
            for reference in references:
                batch.update(reference, {"value": total, "updated_at": now})
        else:
            reference = data_collection.document(f"demo-calories-{USER_ID}-{day}")
            batch.set(reference, {
                "user_id": USER_ID,
                "date": day,
                "value": total,
                "memo": "\uc2dc\uc5f0\uc6a9 \ud569\uc131 \ub370\uc774\ud130 \u00b7 \uc2e4\uc81c \uce21\uc815\uac12\uc774 \uc544\ub2d9\ub2c8\ub2e4.",
                "created_at": now,
                "updated_at": now,
            })
        current_day += timedelta(days=1)
    batch.commit(timeout=10, retry=None)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--write", action="store_true", help="Upsert these synthetic meals into Firestore for demo-user")
    args = parser.parse_args()
    dataset = generate_records()
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(dataset, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    if args.write:
        write_to_firestore(dataset["records"])
        print(f"Wrote {len(dataset['records'])} synthetic meals to Firestore for {USER_ID}.")
    print(f"Saved {len(dataset['records'])} meals ({dataset['metadata']['start_date']} through {dataset['metadata']['end_date']}) to {OUTPUT}.")


if __name__ == "__main__":
    main()
