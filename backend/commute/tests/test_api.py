"""Endpoint-level tests through the Django test client (full request cycle:
URL routing, serializer validation, view logic, JSON responses)."""

import datetime as dt
import json
from unittest import mock

from django.test import TestCase

from commute.models import Setting
from commute.services import google_maps
from commute.tests.factories import DEST, ORIGIN, dm_response, make_sample

# ANALYSIS_MAX_WORKERS=1 runs analyze inline (transaction-friendly in tests)
NO_KEY = {"GOOGLE_MAPS_API_KEY": "", "ANALYSIS_MAX_WORKERS": "1"}
FAKE_KEY = {"GOOGLE_MAPS_API_KEY": "test-key", "ANALYSIS_MAX_WORKERS": "1"}


def post_json(client, path, payload):
    return client.post(path, json.dumps(payload), content_type="application/json")


class SetupApiTests(TestCase):
    @mock.patch.dict("os.environ", NO_KEY)
    def test_status_unconfigured(self):
        res = self.client.get("/api/setup/status")
        self.assertEqual(res.json(), {"configured": False})

    @mock.patch.dict("os.environ", FAKE_KEY)
    def test_status_configured_via_env(self):
        res = self.client.get("/api/setup/status")
        self.assertEqual(res.json(), {"configured": True})

    @mock.patch.dict("os.environ", NO_KEY)
    def test_status_configured_via_db(self):
        Setting.objects.create(key=google_maps.API_KEY_SETTING, value="db-key")
        res = self.client.get("/api/setup/status")
        self.assertEqual(res.json(), {"configured": True})

    @mock.patch.object(google_maps, "validate_key")
    def test_valid_key_is_saved(self, validate):
        res = post_json(self.client, "/api/setup", {"api_key": "  good-key  "})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(
            Setting.objects.get(key=google_maps.API_KEY_SETTING).value, "good-key"
        )
        validate.assert_called_once_with("good-key")

    @mock.patch.object(
        google_maps, "validate_key", side_effect=google_maps.GoogleMapsError("bad key")
    )
    def test_invalid_key_rejected_and_not_saved(self, _validate):
        res = post_json(self.client, "/api/setup", {"api_key": "bad"})
        self.assertEqual(res.status_code, 400)
        self.assertIn("bad key", res.json()["error"])
        self.assertEqual(Setting.objects.count(), 0)


class GeocodeApiTests(TestCase):
    @mock.patch.dict("os.environ", NO_KEY)
    def test_no_key_returns_409(self):
        res = post_json(self.client, "/api/geocode", {"query": "Boston"})
        self.assertEqual(res.status_code, 409)

    @mock.patch.object(google_maps, "geocode")
    def test_candidates_and_region_forwarded(self, geocode):
        geocode.return_value = [
            {"lat": 42.7, "lng": -71.2, "address": "3 Hampshire St, Methuen, MA"}
        ]
        res = post_json(self.client, "/api/geocode", {"query": "3 hampshire st", "region": "us"})
        self.assertEqual(res.status_code, 200)
        self.assertEqual(len(res.json()["results"]), 1)
        geocode.assert_called_once_with("3 hampshire st", region="us")

    @mock.patch.object(google_maps, "geocode", return_value=[])
    def test_no_matches_returns_empty_list(self, _geocode):
        res = post_json(self.client, "/api/geocode", {"query": "xyzzy"})
        self.assertEqual(res.json(), {"results": []})


class AnalyzeValidationTests(TestCase):
    def analyze(self, **overrides):
        payload = dict(
            origin=ORIGIN,
            destination=DEST,
            vector="departure",
            start_hour=8,
            end_hour=9,
            interval_minutes=30,
            days=[0],
            timezone="America/New_York",
        )
        payload.update(overrides)
        return post_json(self.client, "/api/analyze", payload)

    def test_end_hour_before_start_hour_rejected(self):
        self.assertEqual(self.analyze(start_hour=9, end_hour=7).status_code, 400)

    def test_unknown_timezone_rejected(self):
        self.assertEqual(self.analyze(timezone="Mars/Olympus").status_code, 400)

    def test_invalid_interval_rejected(self):
        self.assertEqual(self.analyze(interval_minutes=7).status_code, 400)

    def test_empty_days_rejected(self):
        self.assertEqual(self.analyze(days=[]).status_code, 400)

    def test_duplicate_days_rejected(self):
        self.assertEqual(self.analyze(days=[0, 0]).status_code, 400)

    def test_invalid_vector_rejected(self):
        self.assertEqual(self.analyze(vector="teleport").status_code, 400)

    def test_out_of_range_coordinates_rejected(self):
        self.assertEqual(
            self.analyze(origin={"lat": 95.0, "lng": 0.0}).status_code, 400
        )


class AnalyzeApiTests(TestCase):
    # Anonymous (ANON tier): interval 60 + one morning weekday keeps the request
    # within ANON limits so these exercise the run itself, not tier rejection.
    PAYLOAD = dict(
        origin=ORIGIN,
        destination=DEST,
        vector="departure",
        start_hour=8,
        end_hour=8,
        interval_minutes=60,
        days=[0],
        timezone="America/New_York",
    )

    @mock.patch.dict("os.environ", FAKE_KEY)
    def test_full_run_with_mocked_google(self):
        def fake_request(url, params, label):
            return dm_response({"optimistic": 1100, "best_guess": 1400, "pessimistic": 2000}[
                params["traffic_model"]
            ])

        with mock.patch.object(google_maps, "_request", side_effect=fake_request):
            res = post_json(self.client, "/api/analyze", self.PAYLOAD)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(body["labels"], ["08:00"])
        self.assertEqual(body["results"][0]["day_name"], "Monday")
        self.assertEqual(body["results"][0]["points"][0]["typical_s"], 1400)
        self.assertEqual(body["meta"]["api_calls"], 3)

    @mock.patch.dict("os.environ", NO_KEY)
    def test_cached_data_served_without_any_key(self):
        """FE preview mode: seeded cache data must work with no key at all."""
        make_sample(day_of_week=0, time_of_day=dt.time(8, 0))
        res = post_json(self.client, "/api/analyze", self.PAYLOAD)
        self.assertEqual(res.status_code, 200)
        point = res.json()["results"][0]["points"][0]
        self.assertTrue(point["cached"])
        self.assertEqual(point["typical_s"], 1200)

    @mock.patch.dict("os.environ", NO_KEY)
    def test_cache_miss_without_key_fails_per_point_not_whole_request(self):
        res = post_json(self.client, "/api/analyze", self.PAYLOAD)
        self.assertEqual(res.status_code, 200)
        body = res.json()
        self.assertEqual(len(body["meta"]["errors"]), 1)
        self.assertIn("not configured", body["meta"]["errors"][0]["error"])
