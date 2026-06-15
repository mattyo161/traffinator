"""Driving-route geometry from a free routing provider, with a spatial cache.

Provider selection:
- If OPENROUTESERVICE_API_KEY is set, use OpenRouteService (free tier).
- Otherwise fall back to the public OSRM demo server (no key, best-effort).

The geometry is cached in Postgres keyed spatially (both endpoints within a
small radius) so repeat/near-identical requests are free and so the stored
polylines can later seed corridor/overlap analysis between commutes.
"""

import logging
import os

import requests

from commute import metrics
from commute.models import RouteGeometry

logger = logging.getLogger("commute.routing")

ORS_URL = "https://api.openrouteservice.org/v2/directions/driving-car/geojson"
OSRM_URL = "https://router.project-osrm.org/route/v1/driving"

# Endpoints within this radius (meters) reuse a cached route. Tighter than the
# traffic cache: route shape is sensitive to the actual start/end.
CACHE_RADIUS_M = 250
CACHE_MAX_AGE_DAYS = 30

_LOOKUP_SQL = """
SELECT *
FROM commute_routegeometry
WHERE created_at > now() - interval '%(max_age)s days'
  AND earth_box(ll_to_earth(%(olat)s, %(olng)s), %(radius)s) @> ll_to_earth(origin_lat, origin_lng)
  AND earth_distance(ll_to_earth(%(olat)s, %(olng)s), ll_to_earth(origin_lat, origin_lng)) <= %(radius)s
  AND earth_box(ll_to_earth(%(dlat)s, %(dlng)s), %(radius)s) @> ll_to_earth(dest_lat, dest_lng)
  AND earth_distance(ll_to_earth(%(dlat)s, %(dlng)s), ll_to_earth(dest_lat, dest_lng)) <= %(radius)s
ORDER BY created_at DESC
LIMIT 1
"""


class RoutingError(Exception):
    pass


def _find_cached(origin, destination, radius_m=CACHE_RADIUS_M):
    params = {
        "olat": origin["lat"], "olng": origin["lng"],
        "dlat": destination["lat"], "dlng": destination["lng"],
        "radius": radius_m, "max_age": CACHE_MAX_AGE_DAYS,
    }
    rows = list(RouteGeometry.objects.raw(_LOOKUP_SQL, params))
    return rows[0] if rows else None


def _fetch_ors(origin, destination, key):
    body = {"coordinates": [
        [origin["lng"], origin["lat"]],
        [destination["lng"], destination["lat"]],
    ]}
    logger.info("Route request [openrouteservice]: %s -> %s",
                (origin["lat"], origin["lng"]), (destination["lat"], destination["lng"]))
    with metrics.track_call("openrouteservice", "directions", "free"):
        resp = requests.post(ORS_URL, json=body, headers={"Authorization": key}, timeout=20)
        if resp.status_code != 200:
            raise RoutingError(f"OpenRouteService error {resp.status_code}: {resp.text[:200]}")
        feat = resp.json()["features"][0]
        coords = feat["geometry"]["coordinates"]  # [lng, lat]
        distance = feat["properties"]["summary"].get("distance")
    return [[lat, lng] for lng, lat in coords], distance, "openrouteservice"


def _fetch_osrm(origin, destination):
    url = (
        f"{OSRM_URL}/{origin['lng']},{origin['lat']};"
        f"{destination['lng']},{destination['lat']}"
        "?overview=full&geometries=geojson"
    )
    logger.info("Route request [osrm]: %s -> %s",
                (origin["lat"], origin["lng"]), (destination["lat"], destination["lng"]))
    with metrics.track_call("osrm", "directions", "free"):
        resp = requests.get(url, timeout=20)
        if resp.status_code != 200:
            raise RoutingError(f"OSRM error {resp.status_code}: {resp.text[:200]}")
        data = resp.json()
        if data.get("code") != "Ok" or not data.get("routes"):
            raise RoutingError(f"OSRM returned no route (code={data.get('code')}).")
        route = data["routes"][0]
        coords = route["geometry"]["coordinates"]  # [lng, lat]
    return [[lat, lng] for lng, lat in coords], route.get("distance"), "osrm"


def get_route(origin, destination, cache_radius_m=CACHE_RADIUS_M):
    """Return {geometry, distance_m, provider, cached}. Cache-first.

    `cache_radius_m` is the per-tier spatial reuse radius (commute.tiers)."""
    cached = _find_cached(origin, destination, radius_m=cache_radius_m)
    if cached:
        logger.info("Route cache HIT: sample #%s (%s)", cached.id, cached.provider)
        metrics.record_cache_hit(cached.provider, "directions", "free")
        return {
            "geometry": cached.geometry,
            "distance_m": cached.distance_m,
            "provider": cached.provider,
            "cached": True,
        }

    key = os.environ.get("OPENROUTESERVICE_API_KEY")
    if key:
        geometry, distance, provider = _fetch_ors(origin, destination, key)
    else:
        geometry, distance, provider = _fetch_osrm(origin, destination)

    RouteGeometry.objects.create(
        origin_lat=origin["lat"], origin_lng=origin["lng"],
        dest_lat=destination["lat"], dest_lng=destination["lng"],
        provider=provider,
        distance_m=int(distance) if distance is not None else None,
        geometry=geometry,
    )
    logger.info("Route cache MISS: fetched %d points via %s", len(geometry), provider)
    return {
        "geometry": geometry,
        "distance_m": int(distance) if distance is not None else None,
        "provider": provider,
        "cached": False,
    }
