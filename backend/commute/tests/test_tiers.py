"""User-tier resolution, the central limits matrix, and enforcement."""

import json
from unittest import mock

from django.contrib.auth.models import AnonymousUser, User
from django.test import TestCase, override_settings
from rest_framework.authtoken.models import Token

from commute import tiers
from commute.middleware import ANON_COOKIE
from commute.models import UserProfile
from commute.tests.factories import DEST, ORIGIN

# A valid ANON-tier analyze request (60m, one morning weekday, short trip).
ANON_OK = dict(
    origin=ORIGIN, destination=DEST, vector="departure",
    start_hour=8, end_hour=8, interval_minutes=60, days=[0],
    timezone="America/New_York",
)


def post(client, payload, token=None):
    headers = {"HTTP_AUTHORIZATION": f"Token {token}"} if token else {}
    return client.post("/api/analyze", json.dumps(payload),
                       content_type="application/json", **headers)


class TierResolutionTests(TestCase):
    def test_anonymous_user_is_anon(self):
        self.assertEqual(tiers.get_user_tier(AnonymousUser()), tiers.ANON)
        self.assertEqual(tiers.get_user_tier(None), tiers.ANON)

    def test_authenticated_without_profile_defaults_free(self):
        user = User.objects.create(username="no-profile")
        self.assertEqual(tiers.get_user_tier(user), tiers.FREE)

    def test_profile_tier_is_used(self):
        user = User.objects.create(username="pro")
        UserProfile.objects.create(user=user, tier="PRO", sub_tier="COMP")
        self.assertEqual(tiers.get_user_tier(user), tiers.PRO)


class CheckAnalyzeTests(TestCase):
    """check_analyze returns [] when allowed, else a list of messages."""

    def ok(self, tier, **over):
        params = dict(interval_minutes=60, days=[0], start_hour=8, end_hour=8, distance_mi=5)
        params.update(over)
        return tiers.check_analyze(tier, **params)

    # --- ANON ---
    def test_anon_60m_allowed(self):
        self.assertEqual(self.ok(tiers.ANON), [])

    def test_anon_30m_rejected(self):
        self.assertTrue(self.ok(tiers.ANON, interval_minutes=30))

    def test_5m_is_coming_soon_for_all(self):
        for tier in tiers.TIERS:
            msgs = self.ok(tier, interval_minutes=5)
            self.assertTrue(any("coming soon" in m.lower() for m in msgs))

    def test_anon_weekend_day_rejected(self):
        self.assertTrue(self.ok(tiers.ANON, days=[5]))

    def test_anon_day_count_capped_at_two(self):
        self.assertEqual(self.ok(tiers.ANON, days=[0, 1]), [])
        self.assertTrue(self.ok(tiers.ANON, days=[0, 1, 2]))

    def test_anon_from_hour_outside_window_rejected(self):
        self.assertTrue(self.ok(tiers.ANON, start_hour=12, end_hour=12))

    def test_anon_span_capped(self):
        self.assertEqual(self.ok(tiers.ANON, start_hour=5, end_hour=7), [])
        self.assertTrue(self.ok(tiers.ANON, start_hour=5, end_hour=8))

    def test_anon_distance_capped(self):
        self.assertEqual(self.ok(tiers.ANON, distance_mi=40), [])
        self.assertTrue(self.ok(tiers.ANON, distance_mi=60))

    # --- FREE ---
    def test_free_allows_30m_not_15m(self):
        self.assertEqual(self.ok(tiers.FREE, interval_minutes=30), [])
        self.assertTrue(self.ok(tiers.FREE, interval_minutes=15))

    def test_free_weekdays_up_to_five(self):
        self.assertEqual(self.ok(tiers.FREE, days=[0, 1, 2, 3, 4]), [])
        self.assertTrue(self.ok(tiers.FREE, days=[5]))  # Sat still blocked

    def test_free_span_four_and_distance_hundred(self):
        self.assertEqual(self.ok(tiers.FREE, start_hour=8, end_hour=12, distance_mi=90), [])
        self.assertTrue(self.ok(tiers.FREE, start_hour=8, end_hour=13))
        self.assertTrue(self.ok(tiers.FREE, distance_mi=120))

    # --- PRO ---
    def test_pro_allows_15m_weekends_long_span_and_distance(self):
        self.assertEqual(
            self.ok(tiers.PRO, interval_minutes=15, days=[5, 6],
                    start_hour=8, end_hour=14, distance_mi=400),
            [],
        )

    def test_pro_distance_still_capped(self):
        self.assertTrue(self.ok(tiers.PRO, distance_mi=600))


class CacheRadiusTests(TestCase):
    def test_traffic_radius_loosest_for_anon_tightest_for_pro(self):
        a = tiers.limits_for(tiers.ANON)["traffic_cache_radius_m"]
        f = tiers.limits_for(tiers.FREE)["traffic_cache_radius_m"]
        p = tiers.limits_for(tiers.PRO)["traffic_cache_radius_m"]
        self.assertGreater(a, f)
        self.assertGreater(f, p)

    def test_overrides_from_settings(self):
        with self.settings(TIER_LIMITS_OVERRIDES={"ANON": {"max_distance_mi": 999}}):
            self.assertEqual(tiers.limits_for(tiers.ANON)["max_distance_mi"], 999)


class ConfigEndpointTests(TestCase):
    def test_anonymous_config_reports_anon_and_full_matrix(self):
        body = self.client.get("/api/config").json()
        self.assertEqual(body["tier"], tiers.ANON)
        self.assertEqual(set(body["tiers"]["limits"]), {"ANON", "FREE", "PRO"})
        self.assertIn(5, body["tiers"]["intervals_coming_soon"])

    def test_authenticated_pro_config_reports_pro(self):
        user = User.objects.create(username="pro2")
        UserProfile.objects.create(user=user, tier="PRO")
        token = Token.objects.create(user=user).key
        body = self.client.get(
            "/api/config", HTTP_AUTHORIZATION=f"Token {token}"
        ).json()
        self.assertEqual(body["tier"], tiers.PRO)


class AnonCookieTests(TestCase):
    def test_anonymous_request_sets_signed_cookie(self):
        res = self.client.get("/api/config")
        self.assertIn(ANON_COOKIE, res.cookies)
        self.assertTrue(res.cookies[ANON_COOKIE]["httponly"])

    def test_throttle_ident_combines_cookie_and_ip(self):
        from commute.throttles import AnalyzeAnonThrottle
        request = mock.Mock(anon_id="abc123")
        with mock.patch(
            "rest_framework.throttling.SimpleRateThrottle.get_ident", return_value="1.2.3.4"
        ):
            ident = AnalyzeAnonThrottle().get_ident(request)
        self.assertEqual(ident, "abc123:1.2.3.4")


@override_settings(TIER_ENFORCEMENT_ENABLED=True)
class AnalyzeEnforcementTests(TestCase):
    @mock.patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": "", "ANALYSIS_MAX_WORKERS": "1"})
    def test_anon_disallowed_interval_returns_403_upsell(self):
        res = post(self.client, {**ANON_OK, "interval_minutes": 30})
        self.assertEqual(res.status_code, 403)
        body = res.json()
        self.assertTrue(body["upsell"])
        self.assertEqual(body["tier"], "ANON")

    @mock.patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": "", "ANALYSIS_MAX_WORKERS": "1"})
    def test_anon_too_far_returns_403(self):
        # ~3000 mi apart (NYC -> LA) exceeds the ANON 50-mile cap.
        far = {**ANON_OK, "destination": {"lat": 34.0522, "lng": -118.2437}}
        self.assertEqual(post(self.client, far).status_code, 403)

    @mock.patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": "", "ANALYSIS_MAX_WORKERS": "1"})
    def test_pro_allowed_request_passes_tier_check(self):
        user = User.objects.create(username="pro3")
        UserProfile.objects.create(user=user, tier="PRO")
        token = Token.objects.create(user=user).key
        # 15m + weekend + 6h span: rejected for ANON/FREE, allowed for PRO. No
        # key, so the run returns 200 with per-point errors — but NOT a 403.
        payload = {**ANON_OK, "interval_minutes": 15, "days": [5, 6],
                   "start_hour": 8, "end_hour": 14}
        res = post(self.client, payload, token=token)
        self.assertEqual(res.status_code, 200)

    @override_settings(TIER_ENFORCEMENT_ENABLED=False)
    @mock.patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": "", "ANALYSIS_MAX_WORKERS": "1"})
    def test_disabled_flag_does_not_reject_out_of_tier(self):
        # Dark launch: with enforcement off, an ANON-invalid request runs (200
        # with per-point errors due to no key), never a 403.
        res = post(self.client, {**ANON_OK, "interval_minutes": 30, "days": [0, 1, 2, 3, 4]})
        self.assertEqual(res.status_code, 200)

    @mock.patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": "", "ANALYSIS_MAX_WORKERS": "1"})
    def test_pro_radius_passed_to_analysis(self):
        user = User.objects.create(username="pro4")
        UserProfile.objects.create(user=user, tier="PRO")
        token = Token.objects.create(user=user).key
        with mock.patch("commute.services.analysis.cache.find_cached", return_value=None) as fc:
            with mock.patch("commute.services.google_maps.predict",
                            return_value={"duration_min_s": 1, "duration_typical_s": 1,
                                          "duration_max_s": 1, "distance_m": 1, "raw": {}}):
                post(self.client, ANON_OK, token=token)
        radius = fc.call_args.kwargs["radius_m"]
        self.assertEqual(radius, tiers.limits_for(tiers.PRO)["traffic_cache_radius_m"])
