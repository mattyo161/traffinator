"""Rate limiting on the paid Google-backed endpoints (analyze/route/geocode).

Throttle state lives in the cache; under TestCase each test runs in a
transaction that's rolled back, which also resets the DatabaseCache rows — so
tests don't leak throttle counters into each other. We still cache.clear() in
setUp for belt-and-suspenders.

Note: DRF binds `SimpleRateThrottle.THROTTLE_RATES` to the rates dict at import
time, so `override_settings(REST_FRAMEWORK=...)` does NOT change live rates. We
patch that shared dict directly to set low test limits.
"""

import json
from unittest import mock

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from rest_framework.authtoken.models import Token
from rest_framework.throttling import SimpleRateThrottle

from commute.tests.factories import DEST, ORIGIN

NO_KEY = {"GOOGLE_MAPS_API_KEY": "", "ANALYSIS_MAX_WORKERS": "1"}


def set_rates(**rates):
    """Override live throttle rates (patches the shared THROTTLE_RATES dict)."""
    return mock.patch.dict(SimpleRateThrottle.THROTTLE_RATES, rates)


def post(client, path, payload, token=None):
    headers = {"HTTP_AUTHORIZATION": f"Token {token}"} if token else {}
    return client.post(path, json.dumps(payload), content_type="application/json", **headers)


# interval 60 + a single weekday in the morning window keeps this valid for the
# ANON tier, so these tests exercise *throttling* (not tier limits — see test_tiers).
ANALYZE_PAYLOAD = dict(
    origin=ORIGIN, destination=DEST, vector="departure",
    start_hour=8, end_hour=8, interval_minutes=60, days=[0],
    timezone="America/New_York",
)
GEOCODE_PAYLOAD = {"query": "Boston, MA"}


@mock.patch.dict("os.environ", NO_KEY)
class ThrottleTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_anonymous_analyze_is_throttled(self):
        with set_rates(analyze_anon="2/hour", google_global="1000/day"):
            # No key -> 200 with per-point errors, but the request still counts.
            self.assertEqual(post(self.client, "/api/analyze", ANALYZE_PAYLOAD).status_code, 200)
            self.assertEqual(post(self.client, "/api/analyze", ANALYZE_PAYLOAD).status_code, 200)
            res = post(self.client, "/api/analyze", ANALYZE_PAYLOAD)
        self.assertEqual(res.status_code, 429)
        self.assertIn("throttled", res.json()["detail"].lower())

    def test_anonymous_geocode_is_throttled(self):
        with set_rates(lookup_anon="2/hour", google_global="1000/day"):
            # No key -> 409 per call, but the throttle still counts the requests.
            self.assertEqual(post(self.client, "/api/geocode", GEOCODE_PAYLOAD).status_code, 409)
            self.assertEqual(post(self.client, "/api/geocode", GEOCODE_PAYLOAD).status_code, 409)
            self.assertEqual(post(self.client, "/api/geocode", GEOCODE_PAYLOAD).status_code, 429)

    def test_authenticated_user_has_separate_higher_budget(self):
        user = User.objects.create(username="google:tester")
        token = Token.objects.create(user=user).key
        with set_rates(analyze_anon="1/hour", analyze_user="5/hour", google_global="1000/day"):
            # Exhaust the anon budget.
            self.assertEqual(post(self.client, "/api/analyze", ANALYZE_PAYLOAD).status_code, 200)
            self.assertEqual(post(self.client, "/api/analyze", ANALYZE_PAYLOAD).status_code, 429)
            # Authenticated request uses the per-user scope — a fresh bucket.
            self.assertEqual(
                post(self.client, "/api/analyze", ANALYZE_PAYLOAD, token=token).status_code, 200
            )

    def test_global_circuit_breaker_spans_endpoints(self):
        with set_rates(analyze_anon="100/hour", lookup_anon="100/hour", google_global="1/day"):
            # Per-endpoint budgets are generous; the global cap (1/day) trips
            # across different billable endpoints sharing the one bucket.
            self.assertEqual(post(self.client, "/api/analyze", ANALYZE_PAYLOAD).status_code, 200)
            self.assertEqual(post(self.client, "/api/geocode", GEOCODE_PAYLOAD).status_code, 429)

    def test_default_rates_allow_normal_use(self):
        # With default rates a couple of calls are fine (no 429).
        self.assertNotEqual(post(self.client, "/api/analyze", ANALYZE_PAYLOAD).status_code, 429)
        self.assertNotEqual(post(self.client, "/api/geocode", GEOCODE_PAYLOAD).status_code, 429)
