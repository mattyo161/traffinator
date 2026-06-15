"""Prometheus metrics for outbound external-API usage.

Lets us track paid (Google Maps) vs free (OSRM/ORS) consumption, prove the
cache is avoiding paid calls (cost avoided), and watch per-provider latency and
errors. Exposed on /metrics (see config/urls.py).
"""

import time
from contextlib import contextmanager

from prometheus_client import Counter, Histogram

EXTERNAL_API_CALLS = Counter(
    "traffinator_external_api_calls_total",
    "Outbound external-API calls (and cache hits that avoided them).",
    ["provider", "endpoint", "billable", "outcome"],
)

EXTERNAL_API_DURATION = Histogram(
    "traffinator_external_api_duration_seconds",
    "Latency of outbound external-API calls.",
    ["provider", "endpoint"],
)


@contextmanager
def track_call(provider, endpoint, billable):
    """Time an outbound call and record it. `billable` is 'paid' | 'free'.
    Records outcome 'ok' on success, 'error' if the block raises (then re-raises).
    """
    start = time.monotonic()
    outcome = "ok"
    try:
        yield
    except Exception:
        outcome = "error"
        raise
    finally:
        EXTERNAL_API_DURATION.labels(provider, endpoint).observe(time.monotonic() - start)
        EXTERNAL_API_CALLS.labels(provider, endpoint, billable, outcome).inc()


def record_call(provider, endpoint, billable, outcome):
    """Record a call outcome without timing (e.g. when outcome is decided after
    the HTTP round-trip, or for cache hits)."""
    EXTERNAL_API_CALLS.labels(provider, endpoint, billable, outcome).inc()


def record_cache_hit(provider, endpoint, billable, count=1):
    """Record `count` external calls that a cache hit avoided."""
    EXTERNAL_API_CALLS.labels(provider, endpoint, billable, "cache_hit").inc(count)
