"""Coordinate precision helpers.

Geocoders return lat/lng at wildly varying precision for the same place (see
issue #1), which bloats and fragments the cache. We round all coordinates to a
fixed number of decimals on the way in. At ~6 decimals the error is a few feet —
negligible for commute analysis — and it makes cached rows dedupe and read
cleanly. Precision is configurable via settings.COORDINATE_PRECISION.
"""

from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings


def round_coord(value, precision=None):
    """Round a latitude/longitude to COORDINATE_PRECISION decimals (half-up)."""
    if value is None:
        return None
    p = settings.COORDINATE_PRECISION if precision is None else precision
    quantum = Decimal(1).scaleb(-p)  # e.g. p=6 -> Decimal("0.000001")
    return float(Decimal(str(value)).quantize(quantum, rounding=ROUND_HALF_UP))
