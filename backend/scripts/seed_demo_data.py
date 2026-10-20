"""Create an explicit synthetic 120-point daily calorie series for demonstrations."""

import argparse
import math
from datetime import date, datetime, timedelta, timezone

from app.firebase import get_firestore


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--user-id", default="demo-user")
    parser.add_argument("--count", type=int, default=120)
    args = parser.parse_args()
    if not 100 <= args.count <= 1000:
        parser.error("--count는 100~1000 사이여야 합니다.")

    db = get_firestore()
    if db is None:
        parser.error(
            "Firestore가 연결되지 않았습니다. FIREBASE_SERVICE_ACCOUNT_JSON 또는 "
            "FIREBASE_KEY_PATH 설정을 확인하세요."
        )

    collection = db.collection("data")
    today = datetime.now(timezone.utc).date()
    batch = db.batch()
    now = datetime.now(timezone.utc)
    for index in range(args.count):
        recorded_on = today - timedelta(days=args.count - index - 1)
        calories = round(
            2050 - index * 1.2 + 110 * math.sin(index / 8) + 45 * math.cos(index / 3),
            1,
        )
        document_id = f"demo-calories-{args.user_id}-{recorded_on.isoformat()}"
        batch.set(
            collection.document(document_id),
            {
                "user_id": args.user_id,
                "date": recorded_on.isoformat(),
                "value": calories,
                "memo": "시연용 합성 데이터 · 실제 측정값이 아닙니다.",
                "source": "synthetic_demo",
                "created_at": now,
                "updated_at": now,
            },
        )
        if (index + 1) % 450 == 0:
            batch.commit()
            batch = db.batch()
    batch.commit()
    start = today - timedelta(days=args.count - 1)
    print(
        f"합성 시연 데이터 {args.count}개를 users={args.user_id!r}, "
        f"기간={start.isoformat()}~{today.isoformat()}로 저장했습니다."
    )


if __name__ == "__main__":
    main()
