"""Spatial/temporal validation cache backed by PostgreSQL earthdistance.

A cached TrafficSample is served instead of calling Google when ALL hold:
  1. Origin AND destination are within 1 mile of the request's coordinates
     (earth_box prefilter uses the GiST index; earth_distance confirms the
     true great-circle distance).
  2. The day of the week matches exactly.
  3. The time of day is within an absolute 4-minute delta (wrapping midnight).
  4. The record is less than 7 days old.
"""

import logging

from commute.models import TrafficSample

logger = logging.getLogger("commute.cache")

MILE_METERS = 1609.344
TIME_DELTA_SECONDS = 4 * 60

_LOOKUP_SQL = """
SELECT *
FROM commute_trafficsample
WHERE vector = %(vector)s
  AND day_of_week = %(day_of_week)s
  AND created_at > now() - interval '7 days'
  AND earth_box(ll_to_earth(%(olat)s, %(olng)s), %(radius)s) @> ll_to_earth(origin_lat, origin_lng)
  AND earth_distance(ll_to_earth(%(olat)s, %(olng)s), ll_to_earth(origin_lat, origin_lng)) <= %(radius)s
  AND earth_box(ll_to_earth(%(dlat)s, %(dlng)s), %(radius)s) @> ll_to_earth(dest_lat, dest_lng)
  AND earth_distance(ll_to_earth(%(dlat)s, %(dlng)s), ll_to_earth(dest_lat, dest_lng)) <= %(radius)s
  AND LEAST(
        ABS(EXTRACT(EPOCH FROM time_of_day) - %(time_seconds)s),
        86400 - ABS(EXTRACT(EPOCH FROM time_of_day) - %(time_seconds)s)
      ) <= %(time_delta)s
ORDER BY created_at DESC
LIMIT 1
"""


def find_cached(origin, destination, vector, day_of_week, time_of_day, radius_m=MILE_METERS):
    """Return the freshest matching TrafficSample, or None on a cache miss.

    `radius_m` is the spatial match radius (per-tier; see commute.tiers). Looser
    radii reuse more cached points (cheaper, fewer paid Google calls); tighter
    radii are more precise."""
    time_seconds = time_of_day.hour * 3600 + time_of_day.minute * 60 + time_of_day.second
    params = {
        "vector": vector,
        "day_of_week": day_of_week,
        "olat": origin["lat"],
        "olng": origin["lng"],
        "dlat": destination["lat"],
        "dlng": destination["lng"],
        "radius": radius_m,
        "time_seconds": time_seconds,
        "time_delta": TIME_DELTA_SECONDS,
    }
    rows = list(TrafficSample.objects.raw(_LOOKUP_SQL, params))
    sample = rows[0] if rows else None
    logger.info(
        "Cache %s: vector=%s day=%s time=%s origin=(%.5f,%.5f) dest=(%.5f,%.5f)%s",
        "HIT" if sample else "MISS",
        vector, day_of_week, time_of_day,
        origin["lat"], origin["lng"], destination["lat"], destination["lng"],
        f" -> sample #{sample.id} from {sample.created_at:%Y-%m-%d %H:%M}" if sample else "",
    )
    return sample
