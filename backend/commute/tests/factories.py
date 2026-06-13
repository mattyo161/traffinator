import datetime as dt

from commute.models import TrafficSample

# Demo route used across the test suite: Boston Common -> Newton Centre.
ORIGIN = {"lat": 42.3550, "lng": -71.0656}
DEST = {"lat": 42.3293, "lng": -71.1924}

# Latitude offsets (1 degree latitude ~ 69.05 miles)
HALF_MILE_DEG = 0.5 / 69.05
TWO_MILES_DEG = 2.0 / 69.05


def make_sample(**overrides):
    """Create a TrafficSample with sensible defaults. `created_at` can be
    overridden despite auto_now_add (applied via a follow-up UPDATE)."""
    created_at = overrides.pop("created_at", None)
    defaults = dict(
        origin_lat=ORIGIN["lat"],
        origin_lng=ORIGIN["lng"],
        dest_lat=DEST["lat"],
        dest_lng=DEST["lng"],
        vector="departure",
        day_of_week=0,
        time_of_day=dt.time(8, 0),
        duration_min_s=900,
        duration_typical_s=1200,
        duration_max_s=1800,
        distance_m=14200,
        raw_response={"test": True},
    )
    defaults.update(overrides)
    sample = TrafficSample.objects.create(**defaults)
    if created_at is not None:
        TrafficSample.objects.filter(pk=sample.pk).update(created_at=created_at)
        sample.refresh_from_db()
    return sample


def dm_response(duration_s=1400, element_status="OK"):
    """A Distance Matrix API payload like Google returns it."""
    element = {"status": element_status}
    if element_status == "OK":
        element.update(
            {
                "duration": {"value": duration_s},
                "duration_in_traffic": {"value": duration_s},
                "distance": {"value": 14200},
            }
        )
    return {"status": "OK", "rows": [{"elements": [element]}]}
