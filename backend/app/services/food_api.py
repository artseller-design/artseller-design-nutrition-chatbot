"""공공데이터포털 식품 영양성분을 앱 형식으로 정규화합니다."""

from typing import Any
import re

from app.services.food_safety import search_foods as _search_foods


def _first_value(item: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        value = item.get(key)
        if value not in (None, "", "-"):
            return value
    return None


def _as_number(value: Any) -> float | None:
    try:
        return float(str(value).replace(",", "")) if value is not None else None
    except (TypeError, ValueError):
        return None


def _serving_size_grams(item: dict[str, Any]) -> float | None:
    value = _first_value(
        item,
        "NUTRI_AMOUNT_SERVING",
        "DISH_ONE_SERVING",
        "Z10500",
        "serving_size_g",
        "servingSize",
    )
    amount = _as_number(value)
    if amount is not None:
        return amount if amount > 0 else None
    if value is None:
        return None
    match = re.search(r"(\d+(?:\.\d+)?)\s*(?:g|그램)", str(value), re.IGNORECASE)
    return float(match.group(1)) if match else None


def _basis_amount_grams(item: dict[str, Any]) -> float | None:
    value = _first_value(
        item,
        "SERVING_SIZE",
        "nutConSrtrQua",
        "basis_amount_g",
        "nutrient_basis",
        "nutrients_basis",
    )
    if value is None:
        return None
    amount = _as_number(value)
    if amount is not None:
        return amount if amount > 0 else None
    match = re.search(
        r"(\d+(?:\.\d+)?)\s*(kg|g|그램)", str(value), re.IGNORECASE
    )
    if not match:
        return None
    amount = float(match.group(1))
    return amount * 1000 if match.group(2).lower() == "kg" else amount


def normalize_food(item: dict[str, Any]) -> dict[str, Any]:
    """API 원본의 필드명을 통일해 추천 코드가 영양소를 비교하게 합니다."""
    return {
        "food_name": str(
            _first_value(
                item, "FOOD_NM_KR", "food_name", "foodNm", "DESC_KOR", "식품명"
            )
            or "이름 미상 음식"
        ),
        "calories": _as_number(
            _first_value(
                item, "AMT_NUM1", "enerc", "NUTR_CONT1", "calories", "energy_kcal", "열량"
            )
        ),
        "carbohydrate": _as_number(
            _first_value(
                item, "AMT_NUM6", "chocdf", "NUTR_CONT2", "carbohydrate", "carbs", "탄수화물"
            )
        ),
        "protein": _as_number(
            _first_value(item, "AMT_NUM3", "prot", "NUTR_CONT3", "protein", "단백질")
        ),
        "fat": _as_number(
            _first_value(item, "AMT_NUM4", "fatce", "NUTR_CONT4", "fat", "지방")
        ),
        "sodium": _as_number(
            _first_value(item, "AMT_NUM13", "nat", "NUTR_CONT6", "sodium", "나트륨")
        ),
        "sugar": _as_number(
            _first_value(item, "AMT_NUM7", "sugar", "NUTR_CONT5", "sugar_g", "당류")
        ),
        "basis_amount_g": _basis_amount_grams(item),
        "serving_size_g": _serving_size_grams(item),
        "raw": item,
    }


async def search_foods(query: str, limit: int = 10) -> list[dict[str, Any]]:
    """음식명으로 검색한 결과를 표준 영양 정보 형태로 반환합니다."""
    items = await _search_foods(query, limit)
    return [normalize_food(item) for item in items]