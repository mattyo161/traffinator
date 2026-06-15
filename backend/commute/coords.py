"""Coordinate precision helpers.

Geocoders return lat/lng at wildly varying precision for the same place (see
issue #1), which bloats and fragments the cache. We round all coordinates to a
fixed number of decimals on the way in. At ~6 decimals the error is a few feet —
negligible for commute analysis — and it makes cached rows dedupe and read
cleanly. Precision is configurable via settings.COORDINATE_PRECISION.
"""

import math
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings

EARTH_RADIUS_MI = 3958.7613  # mean Earth radius in miles


def round_coord(value, precision=None):
    """Round a latitude/longitude to COORDINATE_PRECISION decimals (half-up)."""
    if value is None:
        return None
    p = settings.COORDINATE_PRECISION if precision is None else precision
    quantum = Decimal(1).scaleb(-p)  # e.g. p=6 -> Decimal("0.000001")
    return float(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP))


def haversine_miles(origin, destination):
    """Great-circle distance in miles between two {lat, lng} points. Used for
    the per-tier max origin↔dest distance check (commute.tiers)."""
    lat1, lng1 = math.radians(origin["lat"]), math.radians(origin["lng"])
    lat2, lng2 = math.radians(destination["lat"]), math.radians(destination["lng"])
    dlat, dlng = lat2 - lat1, lng2 - lng1
    a = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlng / 2) ** 2
    return 2 * EARTH_RADIUS_MI * math.asin(math.sqrt(a))
