"""Seed 100 clearly labeled synthetic weather-based food recommendations."""

from __future__ import annotations

import argparse
import random
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.firebase import get_firestore  # noqa: E402

USER_ID = "demo-user"
KST = timezone(timedelta(hours=9))
UTC = timezone.utc

MENU_SETS = {
    "hot": [
        ("콩나물국밥", 520, 22, 78, 12),
        ("오이냉국과 현미밥", 460, 15, 76, 10),
        ("두부채소비빔밥", 610, 25, 88, 16),
    ],
    "cold": [
        ("순두부찌개와 잡곡밥", 640, 29, 82, 20),
        ("들깨버섯칼국수", 590, 18, 86, 18),
        ("고등어구이와 현미밥", 630, 34, 72, 23),
    ],
    "mild": [
        ("채소비빔밥", 620, 21, 92, 17),
        ("닭가슴살채소덮밥", 590, 38, 72, 13),
        ("버섯두부덮밥", 560, 23, 78, 15),
    ],
    "rain": [
        ("바지락칼국수", 570, 24, 82, 12),
        ("김치수제비", 530, 16, 88, 9),
        ("소고기무국과 밥", 610, 28, 76, 18),
    ],
}


def make_record(day: date, rng: random.Random) -> dict:
    # Seasonal curve approximates a plausible Changwon year, with deterministic noise.
    seasonal = 15 + 11 * __import__("math").sin(2 * __import__("math").pi * (day.timetuple().tm_yday - 110) / 365)
    temperature = round(seasonal + rng.uniform(-3.5, 3.5), 1)
    rain = round(rng.choice([0, 0, 0, 0.8, 2.4, 6.2, 12.5, 21.0]), 1)
    humidity = rng.randint(38, 91)
    if rain > 0:
        menu_key = "rain"
        reason = "가상 강수 기록을 반영해 따뜻한 국물 메뉴를 포함했습니다."
        queries = ["국물 메뉴", "한식", "따뜻한 음식"]
    elif temperature >= 27:
        menu_key = "hot"
        reason = "가상 기온이 높아 부담이 적고 수분이 있는 메뉴를 골랐습니다."
        queries = ["시원한 한식", "두부", "채소"]
    elif temperature <= 7:
        menu_key = "cold"
        reason = "가상 기온이 낮아 따뜻하고 균형 잡힌 메뉴를 골랐습니다."
        queries = ["찌개", "국수", "생선구이"]
    else:
        menu_key = "mild"
        reason = "가상 기온을 바탕으로 단백질과 채소를 곁들인 한식 메뉴를 골랐습니다."
        queries = ["비빔밥", "닭고기", "두부"]

    foods = []
    for name, calories, protein, carbs, fat in MENU_SETS[menu_key]:
        foods.append({
            "food_name": name,
            "calories_kcal": calories,
            "protein_g": protein,
            "carbohydrate_g": carbs,
            "fat_g": fat,
            "nutrient_basis_g": 400,
            "reason": "가상 날씨 조건에 맞춘 한식 메뉴 시연 후보입니다.",
        })
    return {
        "user_id": USER_ID,
        "target_date": day.isoformat(),
        "weather": {
            "date": day.isoformat(),
            "temperature_c": temperature,
            "precipitation_mm": rain,
            "humidity_percent": humidity,
            "city": "창원",
            "station_id": "synthetic-demo",
            "source": "synthetic_demo",
        },
        "recent_weather_days": 7,
        "missing_days_in_recent_week": 0,
        "duplicate_rows_for_target_date": 1,
        "recommendation_reason": reason,
        "food_queries": queries,
        "foods": foods,
        "source": "synthetic_demo",
        "is_synthetic": True,
        "created_at": datetime.combine(day, datetime.min.time(), tzinfo=UTC),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", default=USER_ID)
    parser.add_argument("--end-date", type=date.fromisoformat, default=datetime.now(KST).date())
    args = parser.parse_args()
    db = get_firestore()
    if db is None:
        raise RuntimeError("Firestore에 연결되지 않았습니다. backend/.env 설정을 확인하세요.")

    start = args.end_date - timedelta(days=99)
    collection = db.collection("users").document(args.user_id).collection("weather_recommendations")
    batch = db.batch()
    for offset in range(100):
        day = start + timedelta(days=offset)
        record = make_record(day, random.Random(20261023 + offset))
        record["user_id"] = args.user_id
        batch.set(collection.document(f"synthetic-demo-{day.isoformat()}"), record)
    batch.commit()
    saved_count = sum(
        1 for _ in collection.where("source", "==", "synthetic_demo").stream()
    )
    if saved_count != 100:
        raise RuntimeError(f"가상 추천 저장 건수가 100건이 아닙니다: {saved_count}건")
    print(f"Seeded 100 synthetic weather recommendations for {args.user_id}: {start} through {args.end_date}.")


if __name__ == "__main__":
    main()
