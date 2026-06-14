from unittest import mock

from django.test import TestCase

from commute.models import RouteGeometry
from commute.services import routing
from commute.tests.factories import DEST, HALF_MILE_DEG, ORIGIN, TWO_MILES_DEG

OSRM_PAYLOAD = {
    "code": "Ok",
    "routes": [
        {
            "distance": 14200.0,
            "geometry": {"coordinates": [[-71.0656, 42.3550], [-71.1924, 42.3293]]},
        }
    ],
}


class RoutingTests(TestCase):
    def test_osrm_fetch_converts_to_latlng_and_caches(self):
        resp = mock.Mock(status_code=200)
        resp.json.return_value = OSRM_PAYLOAD
        with mock.patch.dict("os.environ", {"OPENROUTESERVICE_API_KEY": ""}):
            with mock.patch.object(routing.requests, "get", return_value=resp) as get:
                result = routing.get_route(ORIGIN, DEST)
        self.assertFalse(result["cached"])
        self.assertEqual(result["provider"], "osrm")
        self.assertEqual(result["distance_m"], 14200)
        # geometry returned as [lat, lng]
        self.assertEqual(result["geometry"][0], [42.3550, -71.0656])
        self.assertEqual(RouteGeometry.objects.count(), 1)
        get.assert_called_once()

    def test_second_nearby_request_hits_cache(self):
        RouteGeometry.objects.create(
            origin_lat=ORIGIN["lat"], origin_lng=ORIGIN["lng"],
            dest_lat=DEST["lat"], dest_lng=DEST["lng"],
            provider="osrm", distance_m=14200,
            geometry=[[42.3550, -71.0656], [42.3293, -71.1924]],
        )
        near_origin = {"lat": ORIGIN["lat"] + HALF_MILE_DEG * 0.2, "lng": ORIGIN["lng"]}
        with mock.patch.object(routing.requests, "get") as get:
            result = routing.get_route(near_origin, DEST)
        self.assertTrue(result["cached"])
        get.assert_not_called()

    def test_far_request_misses_cache_and_fetches(self):
        RouteGeometry.objects.create(
            origin_lat=ORIGIN["lat"], origin_lng=ORIGIN["lng"],
            dest_lat=DEST["lat"], dest_lng=DEST["lng"],
            provider="osrm", distance_m=14200,
            geometry=[[42.3550, -71.0656]],
        )
        far_origin = {"lat": ORIGIN["lat"] + TWO_MILES_DEG, "lng": ORIGIN["lng"]}
        resp = mock.Mock(status_code=200)
        resp.json.return_value = OSRM_PAYLOAD
        with mock.patch.dict("os.environ", {"OPENROUTESERVICE_API_KEY": ""}):
            with mock.patch.object(routing.requests, "get", return_value=resp) as get:
                result = routing.get_route(far_origin, DEST)
        self.assertFalse(result["cached"])
        get.assert_called_once()

    def test_osrm_no_route_raises(self):
        resp = mock.Mock(status_code=200)
        resp.json.return_value = {"code": "NoRoute", "routes": []}
        with mock.patch.dict("os.environ", {"OPENROUTESERVICE_API_KEY": ""}):
            with mock.patch.object(routing.requests, "get", return_value=resp):
                with self.assertRaises(routing.RoutingError):
                    routing.get_route(ORIGIN, DEST)

    def test_ors_used_when_key_present(self):
        ors_payload = {
            "features": [
                {
                    "geometry": {"coordinates": [[-71.0656, 42.3550], [-71.1924, 42.3293]]},
                    "properties": {"summary": {"distance": 15000.0}},
                }
            ]
        }
        resp = mock.Mock(status_code=200)
        resp.json.return_value = ors_payload
        with mock.patch.dict("os.environ", {"OPENROUTESERVICE_API_KEY": "ors-key"}):
            with mock.patch.object(routing.requests, "post", return_value=resp) as post:
                result = routing.get_route(ORIGIN, DEST)
        self.assertEqual(result["provider"], "openrouteservice")
        self.assertEqual(result["distance_m"], 15000)
        post.assert_called_once()
