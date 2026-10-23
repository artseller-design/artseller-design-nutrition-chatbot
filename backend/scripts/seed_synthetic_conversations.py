"""Create clearly labeled Korean demo chats grounded in the stored meal history."""

from __future__ import annotations

import json
import statistics
import urllib.error
import urllib.parse
import urllib.request
from datetime import date, datetime, timedelta, timezone

API_BASE = "http://127.0.0.1:8000"
USER_ID = "demo-user"
KST = timezone(timedelta(hours=9))
SYNTHETIC_TITLE_PREFIX = "\uac00\uc0c1 \ub300\ud654 \u00b7 "
TARGET_SYNTHETIC_CHATS = 100


def get_json(path: str):
    with urllib.request.urlopen(f"{API_BASE}{path}", timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def post_json(path: str, payload: dict):
    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"{API_BASE}{path}", data=body, headers={"Content-Type": "application/json"}
    )
    with urllib.request.urlopen(request, timeout=15) as response:
        return json.loads(response.read().decode("utf-8"))


def message(role: str, content: str) -> dict:
    return {"role": role, "content": content}


def main() -> None:
    today = datetime.now(KST).date()
    start = today - timedelta(days=99)
    query = urllib.parse.urlencode({
        "user_id": USER_ID,
        "start_date": start.isoformat(),
        "end_date": today.isoformat(),
        "limit": 500,
    })
    points = sorted(get_json(f"/api/data?{query}"), key=lambda row: row["date"])
    food_query = urllib.parse.urlencode({
        "start_date": (start - timedelta(days=1)).isoformat(),
        "end_date": today.isoformat(),
        "limit": 500,
    })
    foods = get_json(f"/users/{urllib.parse.quote(USER_ID)}/food-entries?{food_query}")
    if not points:
        raise RuntimeError("선택한 100일 구간에 칼로리 데이터가 없습니다.")

    existing = get_json(
        f"/api/conversations?{urllib.parse.urlencode({'user_id': USER_ID, 'limit': 200})}"
    )
    existing_titles = {row.get("title", "") for row in existing}
    synthetic_titles = {
        title for title in existing_titles if title.startswith(SYNTHETIC_TITLE_PREFIX)
    }
    points_by_date = {row["date"]: row for row in points}
    food_by_date: dict[str, list[dict]] = {}
    protein_total = 0.0
    for item in foods:
        timestamp = datetime.fromisoformat(item["recorded_at"].replace("Z", "+00:00"))
        day = timestamp.astimezone(KST).date().isoformat()
        food_by_date.setdefault(day, []).append(item)
        protein_total += float((item.get("nutrients") or {}).get("protein_g") or 0)

    recent = points[-7:]
    previous = points[-14:-7]
    recent_average = statistics.mean(row["value"] for row in recent)
    previous_average = statistics.mean(row["value"] for row in previous) if previous else None
    low = min(points, key=lambda row: row["value"])
    high = max(points, key=lambda row: row["value"])
    daily_protein = protein_total / 100
    today_point = points_by_date.get(today.isoformat())
    today_foods = food_by_date.get(today.isoformat(), [])
    today_lines = [
        f"- {item['food_name']}: {float(item['nutrients']['calories_kcal']):,.1f} kcal"
        for item in sorted(today_foods, key=lambda row: row["recorded_at"])
        if (item.get("nutrients") or {}).get("calories_kcal") is not None
    ]
    today_sum = sum(
        float((item.get("nutrients") or {}).get("calories_kcal") or 0)
        for item in today_foods
    )

    chats = [
        (
            "100\uc77c \uce7c\ub85c\ub9ac \ud750\ub984",
            "\uc800\uc7a5\ub41c \ucd5c\uadfc 100\uc77c \uc2dd\uc0ac \uce7c\ub85c\ub9ac\ub97c \uc694\uc57d\ud574\uc918.",
            (
                f"\uac00\uc0c1 \uc2dc\uc5f0 \ub2f5\ubcc0\uc785\ub2c8\ub2e4. {len(points)}\uc77c\uc758 \ud558\ub8e8 \ud3c9\uade0 \uc12d\ucde8\ub7c9\uc740 "
                f"{statistics.mean(row['value'] for row in points):,.1f} kcal\uc785\ub2c8\ub2e4. "
                f"\uac00\uc7a5 \ub0ae\uc558\ub358 \ub0a0\uc740 {low['date']}\uc758 {low['value']:,.1f} kcal, "
                f"\uac00\uc7a5 \ub192\uc558\ub358 \ub0a0\uc740 {high['date']}\uc758 {high['value']:,.1f} kcal\uc600\uc5b4\uc694. "
                "\uc774 \uae30\ub85d\uc740 \uc2dc\uacc4\uc5f4 \ubd84\uc11d\uc6a9 \uac00\uc0c1 \uc790\ub8cc\ub97c \ubc14\ud0d5\uc73c\ub85c \ub9cc\ub4e0 \uc2dc\uc5f0 \ub300\ud654\uc785\ub2c8\ub2e4."
            ),
        ),
        (
            "\ucd5c\uadfc 7\uc77c \uc774\uc804 \uc8fc \ube44\uad50",
            "\ucd5c\uadfc 7\uc77c\uc740 \uc774\uc804 7\uc77c\ubcf4\ub2e4 \ud3c9\uade0 \uc12d\ucde8 \uce7c\ub85c\ub9ac\uac00 \uc5b4\ub560?",
            (
                f"\uac00\uc0c1 \uc2dc\uc5f0 \ub2f5\ubcc0\uc785\ub2c8\ub2e4. \ucd5c\uadfc 7\uc77c({recent[0]['date']}~{recent[-1]['date']}) \ud3c9\uade0\uc740 "
                f"{recent_average:,.1f} kcal\uc608\uc694. "
                + (f"\uc774\uc804 7\uc77c \ud3c9\uade0 {previous_average:,.1f} kcal\ubcf4\ub2e4 {recent_average - previous_average:+,.1f} kcal \ub192\uc544\uc694." if previous_average is not None else "\ube44\uad50\ud560 \uc774\uc804 7\uc77c \uc790\ub8cc\uac00 \uc5c6\uc5b4\uc694.")
                + " \uac1c\ubcc4 \uc2dd\uc0ac \uae30\ub85d\uc5d0 \ub530\ub77c \uc77c\ubcc4 \ud3b8\ucc28\uac00 \uc788\uc73c\ub2c8 \ud3c9\uade0\uacfc \ud568\uaed8 \ubcf4\uba74 \uc88b\uc544\uc694."
            ),
        ),
        (
            "\uc624\ub298 \ubb34\uc5c7\uc744 \uba39\uc5c8\ub098\uc694",
            f"{today.isoformat()}\uc5d0 \uc800\uc7a5\ub41c \uc2dd\uc0ac\uc640 \uce7c\ub85c\ub9ac\ub97c \uc54c\ub824\uc918.",
            (
                "\uac00\uc0c1 \uc2dc\uc5f0 \ub2f5\ubcc0\uc785\ub2c8\ub2e4. \uc800\uc7a5\ub41c \uc2dd\uc0ac\ub97c \ubcf4\uba74:\n"
                + ("\n".join(today_lines) if today_lines else "- \uc624\ub298 \uc2dd\uc0ac \uc0c1\uc138 \uae30\ub85d\uc774 \uc5c6\uc5b4\uc694.")
                + f"\n\ud558\ub8e8 \uce7c\ub85c\ub9ac \ud569\uacc4\ub294 {today_sum:,.1f} kcal"
                + (f"\ub85c, \uc800\uc7a5\ub41c \uc77c\ubcc4 \uce7c\ub85c\ub9ac {today_point['value']:,.1f} kcal\uc640 \uc77c\uce58\ud574\uc694." if today_point else "\uc785\ub2c8\ub2e4.")
            ),
        ),
        (
            "\uc2dd\uc0ac \uae30\ub85d\uc758 \ub2e8\ubc31\uc9c8",
            "\ub0b4 \uc800\uc7a5 \uc2dd\uc0ac\uc5d0\uc11c \ub2e8\ubc31\uc9c8 \uc12d\ucde8\ub294 \uc5b4\ub290 \uc815\ub3c4\uc57c?",
            (
                f"\uac00\uc0c1 \uc2dc\uc5f0 \ub2f5\ubcc0\uc785\ub2c8\ub2e4. \ucd5c\uadfc 100\uc77c \ubc94\uc704\uc5d0 \uc800\uc7a5\ub41c \uc74c\uc2dd {len(foods)}\uac1c\uc758 \ub2e8\ubc31\uc9c8 \uc601\uc591\uc815\ubcf4\ub97c \ud569\uc0b0\ud558\uba74, "
                f"\ud558\ub8e8 \ud3c9\uade0 {daily_protein:,.1f} g\uc785\ub2c8\ub2e4. \uc2dd\ub2e8 \ubaa9\ud45c\ub098 \uc5f0\ub839\u00b7\uccb4\uaca9 \uc815\ubcf4\ub294 \ubc18\uc601\ud558\uc9c0 \uc54a\uc740 \uc2dc\uc5f0 \uacc4\uc0b0\uc774\uc5d0\uc694."
            ),
        ),
    ]

    # Fill the remaining history with one date-specific Korean chat per synthetic weather recommendation.
    if len(synthetic_titles) < TARGET_SYNTHETIC_CHATS:
        weather_query = urllib.parse.urlencode({"user_id": USER_ID, "limit": 500})
        recommendations = get_json(f"/api/weather/recommendations?{weather_query}")
        virtual_recommendations = sorted(
            (row for row in recommendations if row.get("is_synthetic")),
            key=lambda row: row.get("target_date", ""),
        )
        needed = TARGET_SYNTHETIC_CHATS - len(synthetic_titles)
        added_weather_chats = 0
        for recommendation in virtual_recommendations:
            day = recommendation.get("target_date", "")
            title = SYNTHETIC_TITLE_PREFIX + "\ub0a0\uc528 \uba54\ub274 \u00b7 " + day
            if title in existing_titles:
                continue
            weather = recommendation.get("weather") or {}
            menus = recommendation.get("foods") or []
            menu_names = [item.get("food_name", "\uc74c\uc2dd") for item in menus]
            question = (
                f"{day} \ucc3d\uc6d0 \ub0a0\uc528\uc5d0 \uc5b4\uc6b8\ub9ac\ub294 \ud55c\uad6d \uba54\ub274\ub97c \ucd94\ucc9c\ud574\uc918."
            )
            answer = (
                f"\uac00\uc0c1 \uc2dc\uc5f0 \ub2f5\ubcc0\uc785\ub2c8\ub2e4. {day} \ucc3d\uc6d0\uc758 \uac00\uc0c1 \uae30\uc0c1 \uc790\ub8cc\ub294 "
                f"\uae30\uc628 {weather.get('temperature_c', '\ubbf8\uae30\ub85d')}\u00b0C, \uac15\uc218 {weather.get('precipitation_mm', '\ubbf8\uae30\ub85d')} mm\uc608\uc694. "
                f"\ucd94\ucc9c \uba54\ub274\ub294 {', '.join(menu_names) if menu_names else '\uc800\uc7a5\ub41c \uba54\ub274 \uc815\ubcf4 \uc5c6\uc74c'}\uc785\ub2c8\ub2e4. "
                f"\uc800\uc7a5\ub41c \ucd94\ucc9c \uc0ac\uc720: {recommendation.get('recommendation_reason', '\ub0a0\uc528 \uc870\uac74\uc744 \ubc18\uc601\ud55c \uba54\ub274 \uc81c\uc548')} "
                "\uc774 \ub0a0\uc528\uc640 \uba54\ub274\ub294 \uc2e4\uc81c \uad00\uce21\uc774 \uc544\ub2cc \uac00\uc0c1 \uc2dc\uc5f4 \ub370\uc774\ud130\uc785\ub2c8\ub2e4."
            )
            chats.append((title[len(SYNTHETIC_TITLE_PREFIX):], question, answer))
            added_weather_chats += 1
            if added_weather_chats >= needed:
                break
        if added_weather_chats < needed:
            raise RuntimeError(
                f"가상 날씨 추천 자료가 부족합니다: {len(virtual_recommendations)}건"
            )

    created = 0
    for title_suffix, question, answer in chats:
        title = SYNTHETIC_TITLE_PREFIX + title_suffix
        if title in existing_titles:
            continue
        post_json("/api/conversations", {
            "user_id": USER_ID,
            "title": title,
            "messages": [message("user", question), message("assistant", answer)],
        })
        created += 1
        existing_titles.add(title)
    final = get_json(
        f"/api/conversations?{urllib.parse.urlencode({'user_id': USER_ID, 'limit': 200})}"
    )
    final_synthetic_count = sum(
        1 for row in final if (row.get("title") or "").startswith(SYNTHETIC_TITLE_PREFIX)
    )
    print(
        f"Created {created} synthetic Korean conversations; "
        f"verified total {final_synthetic_count}/{TARGET_SYNTHETIC_CHATS} for {USER_ID}."
    )
    if final_synthetic_count != TARGET_SYNTHETIC_CHATS:
        raise RuntimeError(f"가상 대화가 목표 100건이 아닙니다: {final_synthetic_count}건")


if __name__ == "__main__":
    main()
