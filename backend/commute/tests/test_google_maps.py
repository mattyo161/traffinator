from unittest import mock

from django.test import TestCase

from commute.models import Setting
from commute.services import google_maps
from commute.tests.factories import DEST, ORIGIN, dm_response

FAKE_KEY = {"GOOGLE_MAPS_API_KEY": "test-key"}


def geocode_payload(n=1):
    return {
        "status": "OK",
        "results": [
            {
                "formatted_address": f"Address {i}",
                "geometry": {"location": {"lat": 42.0 + i, "lng": -71.0 - i}},
            }
            for i in range(n)
        ],
    }


class ApiKeyTests(TestCase):
    def test_missing_key_raises(self):
        with mock.patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": ""}):
            with self.assertRaises(google_maps.ApiKeyMissing):
                google_maps.get_api_key()
            self.assertFalse(google_maps.is_configured())

    def test_db_key_used_when_no_env(self):
        Setting.objects.create(key=google_maps.API_KEY_SETTING, value="db-key")
        with mock.patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": ""}):
            self.assertEqual(google_maps.get_api_key(), "db-key")

    def test_env_takes_precedence_over_db(self):
        Setting.objects.create(key=google_maps.API_KEY_SETTING, value="db-key")
        with mock.patch.dict("os.environ", FAKE_KEY):
            self.assertEqual(google_maps.get_api_key(), "test-key")


@mock.patch.dict("os.environ", FAKE_KEY)
class GeocodeTests(TestCase):
    def test_returns_multiple_candidates_capped_at_five(self):
        with mock.patch.object(
            google_maps, "_request", return_value=geocode_payload(7)
        ) as req:
            results = google_maps.geocode("3 hampshire st")
        self.assertEqual(len(results), 5)
        self.assertEqual(results[0]["address"], "Address 0")
        self.assertNotIn("region", req.call_args.args[1])

    def test_region_bias_is_passed_through(self):
        with mock.patch.object(
            google_maps, "_request", return_value=geocode_payload()
        ) as req:
            google_maps.geocode("3 hampshire st", region="us")
        self.assertEqual(req.call_args.args[1]["region"], "us")

    def test_zero_results_returns_empty_list(self):
        with mock.patch.object(
            google_maps, "_request", return_value={"status": "ZERO_RESULTS", "results": []}
        ):
            self.assertEqual(google_maps.geocode("nowhere"), [])

    def test_request_denied_raises(self):
        payload = {"status": "REQUEST_DENIED", "error_message": "API not enabled"}
        with mock.patch.object(google_maps, "_request", return_value=payload):
            with self.assertRaisesMessage(google_maps.GoogleMapsError, "API not enabled"):
                google_maps.geocode("anywhere")


@mock.patch.dict("os.environ", FAKE_KEY)
class PredictTests(TestCase):
    def test_min_max_clamped_even_if_models_disagree(self):
        # optimistic slower than pessimistic: min/max must still be ordered
        durations = {"optimistic": 2000, "best_guess": 1500, "pessimistic": 1000}

        def fake_request(url, params, label):
            return dm_response(durations[params["traffic_model"]])

        with mock.patch.object(google_maps, "_request", side_effect=fake_request):
            pred = google_maps.predict(ORIGIN, DEST, 2_000_000_000)
        self.assertEqual(pred["duration_min_s"], 1000)
        self.assertEqual(pred["duration_typical_s"], 1500)
        self.assertEqual(pred["duration_max_s"], 2000)

    def test_counter_increments_per_http_call_even_on_route_error(self):
        counter_calls = []

        class Counter:
            def add(self, n=1):
                counter_calls.append(n)

        with mock.patch.object(
            google_maps, "_request", return_value=dm_response(element_status="ZERO_RESULTS")
        ):
            with self.assertRaises(google_maps.GoogleMapsError):
                google_maps.predict(ORIGIN, DEST, 2_000_000_000, Counter())
        self.assertEqual(sum(counter_calls), 1)
