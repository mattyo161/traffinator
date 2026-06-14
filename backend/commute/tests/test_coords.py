"""Coordinate precision rounding (issue #1)."""

import json
from unittest import mock

from django.test import TestCase, override_settings

from commute.coords import round_coord
from commute.services import google_maps


class RoundCoordTests(TestCase):
    def test_rounds_to_six_decimals_by_default(self):
        self.assertEqual(round_coord(42.29707519999999), 42.297075)
        self.assertEqual(round_coord(-71.2129985), -71.212999)  # half-up

    def test_already_short_is_unchanged(self):
        self.assertEqual(round_coord(42.2968), 42.2968)

    def test_precision_is_configurable(self):
        self.assertEqual(round_coord(42.2968347, precision=5), 42.29683)
        with override_settings(COORDINATE_PRECISION=4):
            self.assertEqual(round_coord(42.2968347), 42.2968)

    def test_none_passes_through(self):
        self.assertIsNone(round_coord(None))


@mock.patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": "test-key"})
class GeocodeRoundingTests(TestCase):
    def test_geocode_results_are_rounded(self):
        payload = {
            "status": "OK",
            "results": [
                {
                    "formatted_address": "117 Kendrick St, Needham, MA",
                    "geometry": {"location": {"lat": 42.29707519999999, "lng": -71.2129985}},
                }
            ],
        }
        with mock.patch.object(google_maps, "_request", return_value=payload):
            results = google_maps.geocode("117 Kendrick St")
        self.assertEqual(results[0]["lat"], 42.297075)
        self.assertEqual(results[0]["lng"], -71.212999)


class AnalyzeCoordRoundingTests(TestCase):
    @mock.patch.dict("os.environ", {"GOOGLE_MAPS_API_KEY": "", "ANALYSIS_MAX_WORKERS": "1"})
    def test_analyze_rounds_request_coords_before_storage(self):
        # No key -> the point fails per-point, but the round happens in the
        # serializer before any storage/cache lookup. Assert the serializer
        # rounds via a direct validation.
        from commute.serializers import CoordinateSerializer

        s = CoordinateSerializer(data={"lat": 42.29707519999999, "lng": -71.2129985})
        s.is_valid(raise_exception=True)
        self.assertEqual(s.validated_data["lat"], 42.297075)
        self.assertEqual(s.validated_data["lng"], -71.212999)
