"""Runs a commute analysis: cache-first per (day, time) point, Google on miss.

Notes:
- Google's predictive traffic requires a FUTURE departure_time, so each
  selected day-of-week is resolved to its next future occurrence in the
  requester's timezone. The cache key stays (day-of-week, time-of-day), so
  results are reusable across weeks until the 7-day expiry.
- The Distance Matrix API only supports arrival_time for transit, not
  driving. For the 'arrival' vector we probe once with best_guess at the
  target time to estimate the duration D, then run the three traffic-model
  calls at departure = arrival - D. A documented approximation (+1 API call
  per point).
"""

import datetime as dt
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from zoneinfo import ZoneInfo

from django.db import close_old_connections

from commute import metrics
from commute.models import TrafficSample
from commute.services import cache, google_maps

logger = logging.getLogger("commute.analysis")

DAY_NAMES = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]

# Google rejects departure times in the past; keep a small safety margin.
MIN_LEAD = dt.timedelta(minutes=10)
# Arrival mode: margin between computing departure (= arrival - duration) and
# Google receiving the request.
DEPARTURE_MARGIN = dt.timedelta(minutes=2)


def time_slots(start_hour, end_hour, interval_minutes):
    """Inclusive HH:MM slots from start_hour:00 through end_hour:00."""
    slots = []
    minutes = start_hour * 60
    while minutes <= end_hour * 60:
        slots.append(dt.time(hour=minutes // 60, minute=minutes % 60))
        minutes += interval_minutes
    return slots


def next_occurrence(day_of_week, time_of_day, tz):
    """Next future datetime falling on day_of_week (0=Mon) at time_of_day."""
    now = dt.datetime.now(tz)
    candidate = now.replace(
        hour=time_of_day.hour, minute=time_of_day.minute, second=0, microsecond=0
    )
    days_ahead = (day_of_week - candidate.weekday()) % 7
    candidate += dt.timedelta(days=days_ahead)
    if candidate < now + MIN_LEAD:
        candidate += dt.timedelta(days=7)
    return candidate


class _Counter:
    """Thread-safe call counter, incremented as calls happen so that calls
    made before a point ultimately fails are still accounted for."""

    def __init__(self):
        self.value = 0
        self._lock = threading.Lock()

    def add(self, n=1):
        with self._lock:
            self.value += n


def _fetch_point(origin, destination, vector, day, slot, tz, api_counter, cache_radius_m):
    """Resolve one (day, time) point: cache lookup, else live Google fetch."""
    sample = cache.find_cached(origin, destination, vector, day, slot, radius_m=cache_radius_m)
    if sample:
        # A hit avoids the live Google calls this point would otherwise make:
        # 3 traffic-model probes, plus 1 best_guess duration probe for arrival.
        avoided = 4 if vector == "arrival" else 3
        metrics.record_cache_hit("google_maps", "distance_matrix", "paid", count=avoided)
        return sample, True

    target = next_occurrence(day, slot, tz)
    if vector == "arrival":
        probe = google_maps.best_guess_duration(
            origin, destination, target.timestamp(), api_counter
        )
        departure = target - dt.timedelta(seconds=probe["duration_s"])
        if departure < dt.datetime.now(tz) + DEPARTURE_MARGIN:
            # The arrival target is still ahead of us, but the trip needed to
            # make it would have already started. Too late to catch it this
            # week — analyze next week's occurrence of the same day instead.
            target += dt.timedelta(days=7)
            departure += dt.timedelta(days=7)
            logger.info(
                "Arrival %s no longer reachable (would depart in the past); "
                "shifted one week to %s", slot, target.isoformat(),
            )
        logger.info(
            "Arrival mode: target=%s estimated duration=%ss -> departure=%s",
            target.isoformat(), probe["duration_s"], departure.isoformat(),
        )
    else:
        departure = target

    pred = google_maps.predict(origin, destination, departure.timestamp(), api_counter)

    sample = TrafficSample.objects.create(
        origin_lat=origin["lat"],
        origin_lng=origin["lng"],
        dest_lat=destination["lat"],
        dest_lng=destination["lng"],
        vector=vector,
        day_of_week=day,
        time_of_day=slot,
        duration_min_s=pred["duration_min_s"],
        duration_typical_s=pred["duration_typical_s"],
        duration_max_s=pred["duration_max_s"],
        distance_m=pred["distance_m"],
        raw_response={
            "queried_departure": departure.isoformat(),
            "target_time": target.isoformat(),
            "responses": pred["raw"],
        },
    )
    return sample, False


def run_analysis(origin, destination, vector, start_hour, end_hour, interval_minutes,
                 days, timezone_name, cache_radius_m=None):
    # None -> the cache's own default radius (callers that don't tier-gate).
    if cache_radius_m is None:
        cache_radius_m = cache.MILE_METERS
    tz = ZoneInfo(timezone_name)
    slots = time_slots(start_hour, end_hour, interval_minutes)
    tasks = [(day, slot) for day in sorted(days) for slot in slots]
    logger.info(
        "Analysis start: vector=%s days=%s slots=%d (%s..%s every %dmin) tz=%s -> %d points",
        vector, sorted(days), len(slots), slots[0], slots[-1], interval_minutes,
        timezone_name, len(tasks),
    )

    api_counter = _Counter()

    def worker(task):
        day, slot = task
        try:
            return task, _fetch_point(origin, destination, vector, day, slot, tz,
                                      api_counter, cache_radius_m), None
        except Exception as exc:  # surface per-point errors without killing the run
            logger.error("Point day=%s time=%s failed: %s", day, slot, exc)
            return task, None, str(exc)

    def threaded_worker(task):
        try:
            return worker(task)
        finally:
            # Worker threads get their own DB connections; release them.
            close_old_connections()

    max_workers = max(1, int(os.environ.get("ANALYSIS_MAX_WORKERS", "8")))
    if max_workers == 1:
        # Inline execution: deterministic and transaction-friendly (tests).
        outcomes = [worker(task) for task in tasks]
    else:
        with ThreadPoolExecutor(max_workers=max_workers) as pool:
            outcomes = list(pool.map(threaded_worker, tasks))

    by_day = {day: [] for day in sorted(days)}
    cache_hits = 0
    errors = []
    for (day, slot), result, error in outcomes:
        if error:
            errors.append({"day": day, "time": slot.strftime("%H:%M"), "error": error})
            by_day[day].append({"time": slot.strftime("%H:%M"), "min_s": None,
                                "typical_s": None, "max_s": None, "cached": False})
            continue
        sample, was_cached = result
        cache_hits += 1 if was_cached else 0
        by_day[day].append({
            "time": slot.strftime("%H:%M"),
            "min_s": sample.duration_min_s,
            "typical_s": sample.duration_typical_s,
            "max_s": sample.duration_max_s,
            "distance_m": sample.distance_m,
            "cached": was_cached,
        })

    logger.info(
        "Analysis done: %d points, %d cache hits, %d Google API calls, %d errors",
        len(tasks), cache_hits, api_counter.value, len(errors),
    )
    return {
        "labels": [s.strftime("%H:%M") for s in slots],
        "results": [
            {"day": day, "day_name": DAY_NAMES[day], "points": points}
            for day, points in by_day.items()
        ],
        "meta": {
            "total_points": len(tasks),
            "cache_hits": cache_hits,
            "api_calls": api_counter.value,
            "errors": errors,
        },
    }
