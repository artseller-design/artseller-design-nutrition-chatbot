import unittest
from datetime import datetime, timezone

from fastapi.testclient import TestClient

from app import main
from app.routers import analysis, food_entries


class Snapshot:
    def __init__(self, document_id, values):
        self.id = document_id
        self.values = values
        self.exists = values is not None

    def to_dict(self):
        return self.values


class DocumentReference:
    def __init__(self, collection, document_id):
        self.parent = collection
        self.id = document_id

    def set(self, values):
        self.parent.values[self.id] = values

    def get(self):
        return Snapshot(self.id, self.parent.values.get(self.id))

    def delete(self):
        self.parent.values.pop(self.id, None)

    def collection(self, name):
        return CollectionReference(
            self.parent.database,
            (*self.parent.path, self.id, name),
        )


class CollectionReference:
    def __init__(self, database, path):
        self.database = database
        self.path = path
        self.values = database.collections.setdefault(path, {})
        self.filters = ()
        self.ordering = None
        self.result_limit = None

    def document(self, document_id):
        return DocumentReference(self, document_id)

    def collection(self, name):
        return CollectionReference(self.database, (*self.path, name))

    def where(self, field, operator, value):
        query = CollectionReference(self.database, self.path)
        query.filters = (*self.filters, (field, operator, value))
        return query

    def order_by(self, field, direction="ASCENDING"):
        query = CollectionReference(self.database, self.path)
        query.filters = self.filters
        query.ordering = (field, direction)
        return query

    def limit(self, count):
        query = CollectionReference(self.database, self.path)
        query.filters = self.filters
        query.ordering = self.ordering
        query.result_limit = count
        return query

    def stream(self):
        rows = list(self.values.items())
        for field, operator, value in self.filters:
            if operator == "==":
                rows = [(key, row) for key, row in rows if row.get(field) == value]
            elif operator == ">=":
                rows = [(key, row) for key, row in rows if row.get(field) >= value]
            elif operator == "<":
                rows = [(key, row) for key, row in rows if row.get(field) < value]
        if self.ordering:
            field, direction = self.ordering
            rows.sort(
                key=lambda item: item[1].get(field),
                reverse=direction == "DESCENDING",
            )
        if self.result_limit is not None:
            rows = rows[: self.result_limit]
        return [Snapshot(key, row) for key, row in rows]


class WriteBatch:
    def __init__(self):
        self.writes = []
        self.deletes = []

    def set(self, reference, values):
        self.writes.append((reference, values))

    def delete(self, reference):
        self.deletes.append(reference)

    def commit(self):
        for reference, values in self.writes:
            reference.set(values)
        for reference in self.deletes:
            reference.delete()


class FakeFirestore:
    def __init__(self):
        self.collections = {}

    def collection(self, name):
        return CollectionReference(self, (name,))

    def batch(self):
        return WriteBatch()


class FoodEntryApiTests(unittest.TestCase):
    def setUp(self):
        self.database = FakeFirestore()
        self.original_food_entries_get_firestore = food_entries.get_firestore
        self.original_analysis_get_firestore = analysis.get_firestore
        food_entries.get_firestore = lambda: self.database
        analysis.get_firestore = lambda: self.database
        self.client = TestClient(main.app)

    def tearDown(self):
        food_entries.get_firestore = self.original_food_entries_get_firestore
        analysis.get_firestore = self.original_analysis_get_firestore
        self.client.close()

    def test_meal_saves_multiple_foods_and_summarizes_as_one_meal(self):
        response = self.client.post(
            "/users/tester/food-entries/meal",
            json={
                "recorded_at": "2026-10-19T08:00:00Z",
                "meal_type": "breakfast",
                "foods": [
                    {
                        "food_name": "밥",
                        "amount": 210,
                        "unit": "g",
                        "nutrients": {"calories_kcal": 300},
                    },
                    {
                        "food_name": "김치",
                        "amount": 30,
                        "unit": "g",
                        "nutrients": {"calories_kcal": 15},
                    },
                ],
                "memo": "집밥",
            },
        )

        self.assertEqual(response.status_code, 201, response.text)
        saved_foods = response.json()
        self.assertEqual([food["food_name"] for food in saved_foods], ["밥", "김치"])
        self.assertEqual(saved_foods[0]["meal_id"], saved_foods[1]["meal_id"])

        summary = self.client.get(
            "/users/tester/analysis/summary",
            params={"start_date": "2026-10-19", "end_date": "2026-10-19"},
        )
        self.assertEqual(summary.status_code, 200, summary.text)
        self.assertEqual(summary.json()["entry_count"], 1)
        self.assertEqual(summary.json()["food_entry_count"], 2)
        self.assertEqual(summary.json()["daily_entry_counts"], {"2026-10-19": 1})
        self.assertEqual(summary.json()["nutrient_totals"]["calories_kcal"], 315)

    def test_meal_requires_at_least_one_food(self):
        response = self.client.post(
            "/users/tester/food-entries/meal",
            json={
                "recorded_at": datetime.now(timezone.utc).isoformat(),
                "meal_type": "lunch",
                "foods": [],
            },
        )
        self.assertEqual(response.status_code, 422)

    def test_deleting_meal_removes_every_food_in_that_meal(self):
        response = self.client.post(
            "/users/tester/food-entries/meal",
            json={
                "recorded_at": "2026-10-19T08:00:00Z",
                "meal_type": "breakfast",
                "foods": [
                    {
                        "food_name": "쌀밥",
                        "amount": 200,
                        "unit": "g",
                        "nutrients": {"calories_kcal": 300},
                    },
                    {
                        "food_name": "김치",
                        "amount": 30,
                        "unit": "g",
                        "nutrients": {"calories_kcal": 15},
                    },
                ],
            },
        )
        self.assertEqual(response.status_code, 201, response.text)
        meal_id = response.json()[0]["meal_id"]

        deleted = self.client.delete(f"/users/tester/food-entries/meals/{meal_id}")
        remaining = self.client.get("/users/tester/food-entries")

        self.assertEqual(deleted.status_code, 204)
        self.assertEqual(remaining.status_code, 200)
        self.assertEqual(remaining.json(), [])

    def test_deleting_missing_meal_returns_not_found(self):
        response = self.client.delete("/users/tester/food-entries/meals/missing")
        self.assertEqual(response.status_code, 404)


if __name__ == "__main__":
    unittest.main()
