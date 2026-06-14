"""Google OAuth login (token verification mocked) + owner-scoped saved data."""

import json
from unittest import mock

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from rest_framework.authtoken.models import Token

from commute.models import SavedAddress, SavedRoute
from commute.services import auth
from commute.tests.factories import DEST, ORIGIN

GOOGLE_INFO = {
    "sub": "1234567890",
    "email": "alice@example.com",
    "email_verified": True,
    "given_name": "Alice",
    "family_name": "Smith",
}


def post_json(client, path, payload, token=None):
    headers = {"HTTP_AUTHORIZATION": f"Token {token}"} if token else {}
    return client.post(path, json.dumps(payload), content_type="application/json", **headers)


@override_settings(GOOGLE_OAUTH_CLIENT_ID="test-client-id")
class GoogleLoginTests(TestCase):
    def test_valid_token_creates_user_and_returns_token(self):
        with mock.patch.object(auth.id_token, "verify_oauth2_token", return_value=GOOGLE_INFO):
            res = post_json(self.client, "/api/auth/google", {"credential": "fake"})
        self.assertEqual(res.status_code, 200)
        self.assertIn("token", res.json())
        self.assertEqual(res.json()["user"]["email"], "alice@example.com")
        self.assertEqual(User.objects.count(), 1)

    def test_repeat_login_reuses_same_user(self):
        with mock.patch.object(auth.id_token, "verify_oauth2_token", return_value=GOOGLE_INFO):
            post_json(self.client, "/api/auth/google", {"credential": "fake"})
            post_json(self.client, "/api/auth/google", {"credential": "fake"})
        self.assertEqual(User.objects.count(), 1)

    def test_created_user_has_unusable_password(self):
        with mock.patch.object(auth.id_token, "verify_oauth2_token", return_value=GOOGLE_INFO):
            post_json(self.client, "/api/auth/google", {"credential": "fake"})
        self.assertFalse(User.objects.get().has_usable_password())

    def test_existing_usable_password_is_backfilled_to_unusable(self):
        # A pre-existing google: account that somehow has a usable password gets
        # marked unusable on its next OAuth login.
        u = User.objects.create(username=f"google:{GOOGLE_INFO['sub']}")
        u.set_password("hunter2")
        u.save()
        self.assertTrue(u.has_usable_password())
        with mock.patch.object(auth.id_token, "verify_oauth2_token", return_value=GOOGLE_INFO):
            post_json(self.client, "/api/auth/google", {"credential": "fake"})
        u.refresh_from_db()
        self.assertFalse(u.has_usable_password())

    def test_unverified_email_rejected(self):
        info = {**GOOGLE_INFO, "email_verified": False}
        with mock.patch.object(auth.id_token, "verify_oauth2_token", return_value=info):
            res = post_json(self.client, "/api/auth/google", {"credential": "fake"})
        self.assertEqual(res.status_code, 401)
        self.assertEqual(User.objects.count(), 0)

    def test_invalid_token_rejected(self):
        with mock.patch.object(
            auth.id_token, "verify_oauth2_token", side_effect=ValueError("bad")
        ):
            res = post_json(self.client, "/api/auth/google", {"credential": "fake"})
        self.assertEqual(res.status_code, 401)


@override_settings(GOOGLE_OAUTH_CLIENT_ID="")
class GoogleNotConfiguredTests(TestCase):
    def test_login_fails_clearly_when_unconfigured(self):
        res = post_json(self.client, "/api/auth/google", {"credential": "fake"})
        self.assertEqual(res.status_code, 401)
        self.assertIn("not configured", res.json()["error"])


class SavedDataTests(TestCase):
    def setUp(self):
        self.alice = User.objects.create(username="google:alice")
        self.bob = User.objects.create(username="google:bob")
        self.alice_token = Token.objects.create(user=self.alice).key
        self.bob_token = Token.objects.create(user=self.bob).key

    def auth_headers(self, token):
        return {"HTTP_AUTHORIZATION": f"Token {token}"}

    def test_anonymous_cannot_list_saved_routes(self):
        self.assertEqual(self.client.get("/api/saved-routes/").status_code, 401)

    def test_create_and_list_saved_route(self):
        payload = {
            "name": "Work",
            "origin_label": "Home", "origin_lat": ORIGIN["lat"], "origin_lng": ORIGIN["lng"],
            "dest_label": "Office", "dest_lat": DEST["lat"], "dest_lng": DEST["lng"],
            "params": {"vector": "departure", "days": [0, 1]},
        }
        res = post_json(self.client, "/api/saved-routes/", payload, token=self.alice_token)
        self.assertEqual(res.status_code, 201)
        listed = self.client.get("/api/saved-routes/", **self.auth_headers(self.alice_token))
        self.assertEqual(len(listed.json()), 1)
        self.assertEqual(listed.json()[0]["name"], "Work")

    def test_users_only_see_their_own_routes(self):
        SavedRoute.objects.create(
            user=self.alice, name="Alice route",
            origin_label="A", origin_lat=ORIGIN["lat"], origin_lng=ORIGIN["lng"],
            dest_label="B", dest_lat=DEST["lat"], dest_lng=DEST["lng"], params={},
        )
        res = self.client.get("/api/saved-routes/", **self.auth_headers(self.bob_token))
        self.assertEqual(res.json(), [])

    def test_user_cannot_delete_another_users_route(self):
        route = SavedRoute.objects.create(
            user=self.alice, name="Alice route",
            origin_label="A", origin_lat=ORIGIN["lat"], origin_lng=ORIGIN["lng"],
            dest_label="B", dest_lat=DEST["lat"], dest_lng=DEST["lng"], params={},
        )
        res = self.client.delete(
            f"/api/saved-routes/{route.id}/", **self.auth_headers(self.bob_token)
        )
        self.assertEqual(res.status_code, 404)
        self.assertTrue(SavedRoute.objects.filter(id=route.id).exists())

    def test_saved_address_crud_scoped_to_user(self):
        payload = {"label": "Gym", "address": "1 Main St", "lat": 42.0, "lng": -71.0}
        res = post_json(self.client, "/api/saved-addresses/", payload, token=self.alice_token)
        self.assertEqual(res.status_code, 201)
        self.assertEqual(SavedAddress.objects.filter(user=self.alice).count(), 1)
        # Bob sees nothing
        bob_list = self.client.get("/api/saved-addresses/", **self.auth_headers(self.bob_token))
        self.assertEqual(bob_list.json(), [])
