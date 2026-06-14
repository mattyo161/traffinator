"""Rate limits for the paid Google-backed endpoints.

These endpoints stay publicly reachable (demo mode) but are throttled so a
client — or the whole world — can't run up the Google bill. Anonymous callers
are limited per-IP, authenticated callers get a higher per-user budget, and a
global circuit-breaker caps total billable traffic across everyone.

Rates are defined in settings.REST_FRAMEWORK["DEFAULT_THROTTLE_RATES"] and are
env-configurable (THROTTLE_* vars).
"""

from rest_framework.throttling import (
    AnonRateThrottle,
    SimpleRateThrottle,
    UserRateThrottle,
)


# analyze: heaviest endpoint (many Distance Matrix calls per request).
class AnalyzeAnonThrottle(AnonRateThrottle):
    scope = "analyze_anon"


class AnalyzeUserThrottle(UserRateThrottle):
    scope = "analyze_user"


# route + geocode: lighter (~one Google/OSRM call per request) — shared budget.
class LookupAnonThrottle(AnonRateThrottle):
    scope = "lookup_anon"


class LookupUserThrottle(UserRateThrottle):
    scope = "lookup_user"


class GlobalGoogleThrottle(SimpleRateThrottle):
    """Coarse cross-client circuit-breaker: caps total requests to the billable
    endpoints across ALL clients (one shared bucket), bounding worst-case spend
    even under distributed load. Requires a shared cache to be meaningful."""

    scope = "google_global"

    def get_cache_key(self, request, view):
        # Constant key -> a single bucket shared by every caller.
        return "throttle:google:global"
