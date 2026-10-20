"""Tests for Firebase authentication and application user scoping."""

import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient
from firebase_admin import auth

from app import main
from app.config import settings


class FirebaseSecurityTests(unittest.TestCase):
    def setUp(self):
        self.original_require_auth = settings.require_firebase_auth
        self.original_allowed_uid = settings.firebase_allowed_uid
        self.original_app_user_id = settings.app_user_id
        self.original_dependency_overrides = main.app.dependency_overrides.copy()
        main.app.dependency_overrides.clear()
        settings.require_firebase_auth = True
        settings.firebase_allowed_uid = "allowed-user"
        settings.app_user_id = "demo-user"
        self.client = TestClient(main.app)

    def tearDown(self):
        self.client.close()
        settings.require_firebase_auth = self.original_require_auth
        settings.firebase_allowed_uid = self.original_allowed_uid
        settings.app_user_id = self.original_app_user_id
        main.app.dependency_overrides = self.original_dependency_overrides

    def test_health_is_public_but_session_requires_a_bearer_token(self):
        self.assertEqual(self.client.get("/health").status_code, 200)
        response = self.client.get("/api/auth/session")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["detail"], "로그인이 필요합니다.")

    def test_missing_allowed_uid_fails_closed(self):
        settings.firebase_allowed_uid = None
        response = self.client.get(
            "/api/auth/session",
            headers={"Authorization": "Bearer valid-token"},
        )
        self.assertEqual(response.status_code, 503)

    @patch("app.security.auth.verify_id_token", return_value={"uid": "allowed-user"})
    def test_allowed_firebase_user_can_read_app_session(self, verify_token):
        response = self.client.get(
            "/api/auth/session",
            headers={"Authorization": "Bearer valid-token"},
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), {"uid": "allowed-user", "user_id": "demo-user"})
        verify_token.assert_called_once_with("valid-token", check_revoked=True)

    @patch("app.security.auth.verify_id_token", return_value={"uid": "other-user"})
    def test_other_firebase_user_is_forbidden(self, _verify_token):
        response = self.client.get(
            "/api/auth/session",
            headers={"Authorization": "Bearer valid-token"},
        )
        self.assertEqual(response.status_code, 403)

    @patch(
        "app.security.auth.verify_id_token",
        side_effect=auth.InvalidIdTokenError("invalid"),
    )
    def test_invalid_firebase_token_is_rejected(self, _verify_token):
        response = self.client.get(
            "/api/auth/session",
            headers={"Authorization": "Bearer invalid-token"},
        )
        self.assertEqual(response.status_code, 401)

    @patch("app.security.auth.verify_id_token", return_value={"uid": "allowed-user"})
    def test_user_path_is_restricted_to_configured_data_user(self, _verify_token):
        response = self.client.get(
            "/users/other-user/food-entries",
            headers={"Authorization": "Bearer valid-token"},
        )
        self.assertEqual(response.status_code, 403)

    @patch("app.security.auth.verify_id_token", return_value={"uid": "allowed-user"})
    def test_user_id_in_json_body_is_restricted(self, _verify_token):
        response = self.client.post(
            "/api/activity",
            headers={"Authorization": "Bearer valid-token"},
            json={
                "user_id": "other-user",
                "date": "2026-10-19",
                "steps": 1000,
                "exercise_minutes": 10,
            },
        )
        self.assertEqual(response.status_code, 403)

    @patch("app.routers.activity.get_user_collection", return_value=None)
    @patch("app.security.auth.verify_id_token", return_value={"uid": "allowed-user"})
    def test_allowed_json_body_remains_available_to_route(self, _verify_token, _collection):
        response = self.client.post(
            "/api/activity",
            headers={"Authorization": "Bearer valid-token"},
            json={
                "user_id": "demo-user",
                "date": "2026-10-19",
                "steps": 1000,
                "exercise_minutes": 10,
            },
        )
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["detail"], "Firestore에 연결되지 않았습니다.")
