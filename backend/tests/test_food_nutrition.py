"""Tests for the data.go.kr food-nutrition lookup."""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

from app import main
from app.config import settings
from app.routers import food_nutrition
from app.services import food_api, food_safety


class FoodNutritionApiTests(unittest.TestCase):
    def setUp(self):
        food_safety._search_cache.clear()

    def test_official_dataset_fields_are_normalized_and_scaled_by_basis(self):
        result = food_api.normalize_food(
            {
                "FOOD_NM_KR": "현미밥",
                "SERVING_SIZE": "100g",
                "AMT_NUM1": "150",
                "AMT_NUM3": "3.2",
                "AMT_NUM4": "1.1",
                "AMT_NUM6": "32.1",
                "AMT_NUM7": "0.4",
                "AMT_NUM13": "4",
                "NUTRI_AMOUNT_SERVING": "210g",
            }
        )

        self.assertEqual(result["food_name"], "현미밥")
        self.assertEqual(result["basis_amount_g"], 100)
        self.assertEqual(result["serving_size_g"], 210)
        self.assertEqual(result["calories"], 150)
        self.assertEqual(result["carbohydrate"], 32.1)
        self.assertEqual(result["protein"], 3.2)
        self.assertEqual(result["fat"], 1.1)
        self.assertEqual(result["sugar"], 0.4)
        self.assertEqual(result["sodium"], 4)

    def test_food_lookup_returns_official_nutrient_basis(self):
        original_key = settings.food_api_key
        settings.food_api_key = "test-key"
        self.addCleanup(setattr, settings, "food_api_key", original_key)
        with patch.object(
            food_nutrition,
            "search_foods",
            return_value=[
                {
                    "food_name": "현미밥",
                    "basis_amount_g": 80,
                    "serving_size_g": 210,
                    "calories": 120,
                    "carbohydrate": 25,
                    "protein": 2.5,
                    "fat": 0.8,
                    "sugar": 0.2,
                    "sodium": 3,
                }
            ],
        ):
            with TestClient(main.app) as client:
                response = client.get(
                    "/api/food-nutrition", params={"query": "현미밥"}
                )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            response.json(),
            [
                {
                    "food_name": "현미밥",
                    "basis_amount_g": 80,
                    "serving_size_g": 210,
                    "nutrients_per_basis": {
                        "calories_kcal": 120,
                        "carbohydrate_g": 25,
                        "protein_g": 2.5,
                        "fat_g": 0.8,
                        "sugar_g": 0.2,
                        "sodium_mg": 3,
                    },
                }
            ],
        )

    def test_exact_food_name_is_sorted_first(self):
        original_key = settings.food_api_key
        settings.food_api_key = "test-key"
        self.addCleanup(setattr, settings, "food_api_key", original_key)
        with patch.object(
            food_nutrition,
            "search_foods",
            return_value=[
                {
                    "food_name": "김밥_김치",
                    "basis_amount_g": 100,
                    "serving_size_g": 270,
                    "calories": 130,
                },
                {
                    "food_name": "김치찌개",
                    "basis_amount_g": 100,
                    "serving_size_g": 300,
                    "calories": 40,
                },
                {
                    "food_name": "김치",
                    "basis_amount_g": 100,
                    "serving_size_g": 50,
                    "calories": 20,
                },
            ],
        ):
            with TestClient(main.app) as client:
                response = client.get(
                    "/api/food-nutrition", params={"query": "김치"}
                )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            [food["food_name"] for food in response.json()],
            ["김치", "김치찌개", "김밥_김치"],
        )

    def test_general_food_name_from_last_page_ranks_before_recipe_matches(self):
        foods = [
            {
                "food_name": "김치, 갓김치",
                "raw": {"FOOD_NM_KR": "김치, 갓김치"},
            },
            {
                "food_name": "김치, 배추 김치",
                "raw": {"FOOD_NM_KR": "김치, 배추 김치"},
            },
            {
                "food_name": "김치국",
                "raw": {"FOOD_NM_KR": "김치국"},
            },
            {
                "food_name": "김치, 얼갈이배추 김치",
                "raw": {"FOOD_NM_KR": "김치, 얼갈이배추 김치"},
            },
        ]

        ranked = food_nutrition._rank_food_matches(foods, "김치")

        self.assertEqual(ranked[0]["food_name"], "김치, 배추 김치")

    def test_common_shiraegi_typo_ranks_the_standard_food_first(self):
        foods = [
            {
                "food_name": "들깨무청시래기국",
                "raw": {"FOOD_NM_KR": "들깨무청시래기국"},
            },
            {
                "food_name": "시래기국",
                "raw": {"FOOD_NM_KR": "시래기국"},
            },
        ]

        ranked = food_nutrition._rank_food_matches(foods, "시레기 국")

        self.assertEqual(ranked[0]["food_name"], "시래기국")

    def test_search_calls_documented_data_go_kr_api(self):
        original_key = settings.food_api_key
        original_url = settings.food_safety_api_url
        settings.food_api_key = "test-key"
        settings.food_safety_api_url = (
            "https://apis.data.go.kr/1471000/FoodNtrCpntDbInfo03/getFoodNtrCpntDbInq03"
        )
        self.addCleanup(setattr, settings, "food_api_key", original_key)
        self.addCleanup(setattr, settings, "food_safety_api_url", original_url)

        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "response": {
                        "header": {"resultCode": "00"},
                        "body": {
                            "items": {
                                "item": [
                                    {"FOOD_NM_KR": "현미밥", "AMT_NUM1": "150"}
                                ]
                            }
                        },
                    }
                }

        class AsyncClient:
            calls = []

            def __init__(self, timeout):
                self.timeout = timeout

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def get(self, url, params, timeout=None):
                self.calls.append((url, params))
                return Response()

        with patch.object(food_safety.httpx, "AsyncClient", AsyncClient):
            import asyncio

            result = asyncio.run(food_safety.search_foods("현미밥", limit=3))

        self.assertEqual(result, [{"FOOD_NM_KR": "현미밥", "AMT_NUM1": "150"}])
        self.assertEqual(
            AsyncClient.calls[0][0],
            "https://apis.data.go.kr/1471000/FoodNtrCpntDbInfo03/getFoodNtrCpntDbInq03",
        )
        self.assertEqual(
            AsyncClient.calls[0][1],
            {
                "serviceKey": "test-key",
                "type": "json",
                "FOOD_NM_KR": "현미밥",
                "pageNo": 1,
                "numOfRows": 3,
            },
        )

    def test_search_normalizes_shiraegi_typo_and_spaces(self):
        original_key = settings.food_api_key
        settings.food_api_key = "test-key"
        self.addCleanup(setattr, settings, "food_api_key", original_key)

        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "response": {
                        "header": {"resultCode": "00"},
                        "body": {
                            "totalCount": 1,
                            "items": {"item": [{"FOOD_NM_KR": "시래기국"}]},
                        },
                    }
                }

        class AsyncClient:
            calls = []

            def __init__(self, timeout):
                self.timeout = timeout

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def get(self, url, params):
                self.calls.append(params)
                return Response()

        with patch.object(food_safety.httpx, "AsyncClient", AsyncClient):
            import asyncio

            results = asyncio.run(food_safety.search_foods("시레기 국", limit=10))

        self.assertEqual(AsyncClient.calls[0]["FOOD_NM_KR"], "시래기국")
        self.assertEqual(
            [item["FOOD_NM_KR"] for item in results],
            ["시래기국"],
        )

    def test_search_includes_last_page_when_first_page_has_no_exact_food(self):
        original_key = settings.food_api_key
        settings.food_api_key = "test-key"
        self.addCleanup(setattr, settings, "food_api_key", original_key)

        class Response:
            def __init__(self, page):
                self.page = page

            def raise_for_status(self):
                return None

            def json(self):
                if self.page == 1:
                    rows = [{"FOOD_NM_KR": "김치국"}]
                    total_count = 6730
                else:
                    rows = [{"FOOD_NM_KR": "김치, 배추 김치"}]
                    total_count = 6730
                return {
                    "response": {
                        "header": {"resultCode": "00"},
                        "body": {
                            "totalCount": total_count,
                            "items": {"item": rows},
                        },
                    }
                }

        class AsyncClient:
            calls = []

            def __init__(self, timeout):
                self.timeout = timeout

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def get(self, url, params, timeout=None):
                self.calls.append((params["pageNo"], params["numOfRows"]))
                return Response(params["pageNo"])

        with patch.object(food_safety.httpx, "AsyncClient", AsyncClient):
            import asyncio

            results = asyncio.run(food_safety.search_foods("김치", limit=10))

        self.assertEqual(AsyncClient.calls, [(1, 10), (135, 50)])
        self.assertEqual(
            [item["FOOD_NM_KR"] for item in results],
            ["김치국", "김치, 배추 김치"],
        )

    def test_search_returns_first_page_when_fallback_times_out(self):
        original_key = settings.food_api_key
        settings.food_api_key = "test-key"
        self.addCleanup(setattr, settings, "food_api_key", original_key)

        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "response": {
                        "header": {"resultCode": "00"},
                        "body": {
                            "totalCount": 6730,
                            "items": {"item": [{"FOOD_NM_KR": "김치국"}]},
                        },
                    }
                }

        class AsyncClient:
            calls = 0

            def __init__(self, timeout):
                self.timeout = timeout

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def get(self, url, params, timeout=None):
                type(self).calls += 1
                if type(self).calls == 2:
                    raise food_safety.httpx.ReadTimeout("fallback timed out")
                return Response()

        with patch.object(food_safety.httpx, "AsyncClient", AsyncClient):
            import asyncio

            results = asyncio.run(food_safety.search_foods("김치", limit=10))

        self.assertEqual(AsyncClient.calls, 2)
        self.assertEqual(
            [item["FOOD_NM_KR"] for item in results],
            ["김치국"],
        )

    def test_search_reuses_recent_results_for_same_query(self):
        original_key = settings.food_api_key
        settings.food_api_key = "test-key"
        self.addCleanup(setattr, settings, "food_api_key", original_key)

        class Response:
            def raise_for_status(self):
                return None

            def json(self):
                return {
                    "response": {
                        "header": {"resultCode": "00"},
                        "body": {"items": [{"FOOD_NM_KR": "김치"}]},
                    }
                }

        class AsyncClient:
            calls = 0

            def __init__(self, timeout):
                self.timeout = timeout

            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return None

            async def get(self, url, params):
                type(self).calls += 1
                return Response()

        async def search_twice():
            first = await food_safety.search_foods("김치", limit=5)
            second = await food_safety.search_foods(" 김치 ", limit=5)
            return first, second

        with patch.object(food_safety.httpx, "AsyncClient", AsyncClient):
            import asyncio

            first, second = asyncio.run(search_twice())

        self.assertEqual(first, second)
        self.assertEqual(AsyncClient.calls, 1)
