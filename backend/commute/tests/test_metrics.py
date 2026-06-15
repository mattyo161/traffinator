from unittest import mock

from django.test import TestCase
from prometheus_client import REGISTRY

import datetime as dt
from zoneinfo import ZoneInfo

from commute import metrics
from commute.services import analysis, google_maps, routing
from commute.tests.factories import DEST, ORIGIN, make_sample

CALLS = "traffinator_external_api_calls_total"
DURATION_COUNT = "traffinator_external_api_duration_seconds_count"
FAKE_KEY = {"GOOGLE_MAPS_API_KEY": "test-key"}


def calls(provider, endpoint, billable, outcome):
    """Current value of the calls counter for one label set (0 if unseen)."""
    return REGISTRY.get_sample_value(
        CALLS,
        {"provider": provider, "endpoint": endpoint, "billable": billable, "outcome": outcome},
    ) or 0.0


def duration_count(provider, endpoint):
    return REGISTRY.get_sample_value(
        DURATION_COUNT, {"provider": provider, "endpoint": endpoint}
    ) or 0.0


class HelperTests(TestCase):
    def test_track_call_records_ok_and_times_it(self):
        before = calls("p", "e", "free", "ok")
        before_dur = duration_count("p", "e")
        with metrics.track_call("p", "e", "free"):
            pass
        self.assertEqual(calls("p", "e", "free", "ok"), before + 1)
        self.assertEqual(duration_count("p", "e"), before_dur + 1)

    def test_track_call_records_error_and_reraises(self):
        before = calls("p", "e", "free", "error")
        before_dur = duration_count("p", "e")
        with self.assertRaises(ValueError):
            with metrics.track_call("p", "e", "free"):
                raise ValueError("boom")
        self.assertEqual(calls("p", "e", "free", "error"), before + 1)
        # Duration is still observed even on failure (finally block).
        self.assertEqual(duration_count("p", "e"), before_dur + 1)

    def test_record_cache_hit_counts_avoided_calls(self):
        before = calls("google_maps", "distance_matrix", "paid", "cache_hit")
        metrics.record_cache_hit("google_maps", "distance_matrix", "paid", count=3)
        self.assertEqual(
            calls("google_maps", "distance_matrix", "paid", "cache_hit"), before + 3
        )


@mock.patch.dict("os.environ", FAKE_KEY)
class GoogleRequestInstrumentationTests(TestCase):
    def test_ok_response_increments_ok_counter(self):
        before = calls("google_maps", "geocode", "paid", "ok")
        resp = mock.Mock(ok=True, status_code=200)
        resp.json.return_value = {"status": "OK", "results": []}
        with mock.patch.object(google_maps.requests, "get", return_value=resp):
            google_maps._request(google_maps.GEOCODE_URL, {"key": "k"}, "geocode")
        self.assertEqual(calls("google_maps", "geocode", "paid", "ok"), before + 1)

    def test_api_status_error_increments_error_counter(self):
        before = calls("google_maps", "geocode", "paid", "error")
        resp = mock.Mock(ok=True, status_code=200)
        resp.json.return_value = {"status": "REQUEST_DENIED"}
        with mock.patch.object(google_maps.requests, "get", return_value=resp):
            google_maps._request(google_maps.GEOCODE_URL, {"key": "k"}, "geocode")
        self.assertEqual(calls("google_maps", "geocode", "paid", "error"), before + 1)

    def test_transport_failure_increments_error_counter(self):
        before = calls("google_maps", "geocode", "paid", "error")
        with mock.patch.object(
            google_maps.requests, "get",
            side_effect=google_maps.requests.RequestException("network down"),
        ):
            with self.assertRaises(google_maps.GoogleMapsError):
                google_maps._request(google_maps.GEOCODE_URL, {"key": "k"}, "geocode")
        self.assertEqual(calls("google_maps", "geocode", "paid", "error"), before + 1)

    def test_endpoint_label_derived_from_traffic_model_label(self):
        before = calls("google_maps", "distance_matrix", "paid", "ok")
        resp = mock.Mock(ok=True, status_code=200)
        resp.json.return_value = {"status": "OK", "rows": []}
        with mock.patch.object(google_maps.requests, "get", return_value=resp):
            google_maps._request(
                google_maps.DISTANCE_MATRIX_URL, {"key": "k"}, "distance-matrix/best_guess"
            )
        self.assertEqual(calls("google_maps", "distance_matrix", "paid", "ok"), before + 1)


class RoutingCacheHitInstrumentationTests(TestCase):
    def test_route_cache_hit_records_free_cache_hit(self):
        before = calls("osrm", "directions", "free", "cache_hit")
        cached = mock.Mock(id=1, provider="osrm", geometry=[[42.0, -71.0]], distance_m=14200)
        with mock.patch.object(routing, "_find_cached", return_value=cached):
            result = routing.get_route(ORIGIN, DEST)
        self.assertTrue(result["cached"])
        self.assertEqual(calls("osrm", "directions", "free", "cache_hit"), before + 1)


class AnalysisCacheHitInstrumentationTests(TestCase):
    def _fetch_cached(self, vector):
        sample = make_sample(vector=vector)
        with mock.patch.object(analysis.cache, "find_cached", return_value=sample):
            result, was_cached = analysis._fetch_point(
                ORIGIN, DEST, vector, 0, dt.time(8, 0), ZoneInfo("UTC"), None, 1609.344
            )
        self.assertTrue(was_cached)

    def test_departure_cache_hit_avoids_three_paid_calls(self):
        before = calls("google_maps", "distance_matrix", "paid", "cache_hit")
        self._fetch_cached("departure")
        self.assertEqual(
            calls("google_maps", "distance_matrix", "paid", "cache_hit"), before + 3
        )

    def test_arrival_cache_hit_avoids_four_paid_calls(self):
        before = calls("google_maps", "distance_matrix", "paid", "cache_hit")
        self._fetch_cached("arrival")
        self.assertEqual(
            calls("google_maps", "distance_matrix", "paid", "cache_hit"), before + 4
        )
