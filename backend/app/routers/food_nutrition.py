"""Search the data.go.kr food-nutrition standard dataset for meal entry autofill."""

from typing import Any

import httpx
from fastapi import APIRouter, HTTPException, Query, status

from app.services.food_api import search_foods

router = APIRouter(prefix="/api/food-nutrition", tags=["식품 영양정보"])

_NUTRIENT_FIELDS = {
    "calories_kcal": "calories",
    "carbohydrate_g": "carbohydrate",
    "protein_g": "protein",
    "fat_g": "fat",
    "sugar_g": "sugar",
    "sodium_mg": "sodium",
}


def _normalized_food_name(value: str) -> str:
    normalized = "".join(
        character for character in value.casefold() if character.isalnum()
    )
    return normalized.replace("시레기", "시래기")


def _rank_food_matches(
    foods: list[dict[str, Any]], query: str
) -> list[dict[str, Any]]:
    normalized_query = _normalized_food_name(query)

    def rank(food: dict[str, Any]) -> tuple[int, int]:
        name = _normalized_food_name(food["food_name"])
        if name == normalized_query:
            return (0, 0)
        raw_name = food.get("raw", {}).get("FOOD_NM_KR", food["food_name"])
        name_parts = [
            _normalized_food_name(part) for part in str(raw_name).split(",")
        ]
        if normalized_query == "김치" and "배추김치" in name_parts:
            return (1, 0)
        if normalized_query in name_parts:
            return (1, len(name))
        if name.startswith(normalized_query):
            return (2, len(name))
        return (3, len(name))

    return sorted(foods, key=rank)


@router.get("")
async def lookup_food_nutrition(
    query: str = Query(min_length=1, max_length=100),
    limit: int = Query(default=10, ge=1, le=20),
) -> list[dict[str, Any]]:
    """Return food matches with nutrients and their source reference amount."""
    food_name = query.strip()
    if not food_name:
        raise HTTPException(
            status_code=422,
            detail="음식 이름을 입력해 주세요.",
        )
    try:
        matches = await search_foods(food_name, limit=limit)
    except RuntimeError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    except httpx.HTTPStatusError as error:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"공공데이터 식품 영양정보 API가 HTTP {error.response.status_code} 오류를 반환했습니다.",
        ) from error
    except httpx.TimeoutException as error:
        raise HTTPException(
            status_code=status.HTTP_504_GATEWAY_TIMEOUT,
            detail="공공데이터 식품 영양정보 검색 시간이 초과되었습니다. 잠시 후 다시 시도해 주세요.",
        ) from error
    except (httpx.RequestError, ValueError) as error:
        reason = str(error).strip() or type(error).__name__
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"식품 영양정보를 불러오지 못했습니다 ({reason}). 잠시 후 다시 시도해 주세요.",
        ) from error

    results = []
    for food in _rank_food_matches(matches, food_name)[:limit]:
        basis_amount_g = food.get("basis_amount_g")
        nutrients = {
            output_name: food[source_name]
            for output_name, source_name in _NUTRIENT_FIELDS.items()
            if food.get(source_name) is not None
        }
        if not nutrients or basis_amount_g is None:
            continue
        results.append(
            {
                "food_name": food["food_name"],
                "basis_amount_g": basis_amount_g,
                "serving_size_g": food.get("serving_size_g"),
                "nutrients_per_basis": nutrients,
            }
        )
    return results
