"""User tiers — the single source of truth for tier-gated limits.

ANON (unauthenticated) / FREE (OAuth) / PRO (granted manually). Every limit the
SPA grays-out and the API enforces is defined HERE, once. The backend both
*enforces* these (in the analyze view) and *serves* them (via GET /api/config)
so the frontend renders availability/upsells from the exact same data — change a
value here and both sides follow.

Override any value without editing this file via ``settings.TIER_LIMITS_OVERRIDES``
(a partial, deeply-merged dict keyed by tier).
"""

from django.conf import settings

ANON = "ANON"
FREE = "FREE"
PRO = "PRO"
TIERS = (ANON, FREE, PRO)

# The next tier to pitch when a control is blocked (drives upsell copy).
NEXT_TIER = {ANON: FREE, FREE: PRO, PRO: None}

MILE_M = 1609.344
FOOT_M = 0.3048

# Every interval the UI knows about, in display order. A tier "enables" a
# subset; anything here but not enabled renders grayed. 5m is enabled for NO
# tier yet — it shows as "COMING SOON" everywhere (#15/#32).
ALL_INTERVALS = [60, 30, 15, 5]
COMING_SOON_INTERVALS = [5]

WEEKDAYS = [0, 1, 2, 3, 4]              # Mon–Fri
ALL_DAYS = [0, 1, 2, 3, 4, 5, 6]       # Mon–Sun
# ANON commuting windows: 5–9 AM and 3–7 PM.
ANON_FROM_HOURS = [5, 6, 7, 8, 9, 15, 16, 17, 18, 19]
ALL_HOURS = list(range(24))

# Defaults — all configurable here (or via settings.TIER_LIMITS_OVERRIDES).
# distances in miles; cache radii in meters.
_DEFAULTS = {
    ANON: {
        "intervals": [60],
        "days_allowed": WEEKDAYS,
        "days_max": 2,
        "from_hours": ANON_FROM_HOURS,
        "to_span_max": 2,
        "max_distance_mi": 50,
        "traffic_cache_radius_m": round(2.5 * MILE_M, 3),   # 2.5 mi — loosest
        "route_cache_radius_m": 1000.0,
    },
    FREE: {
        "intervals": [60, 30],
        "days_allowed": WEEKDAYS,
        "days_max": 5,
        "from_hours": ALL_HOURS,
        "to_span_max": 4,
        "max_distance_mi": 100,
        "traffic_cache_radius_m": round(1 * MILE_M, 3),     # 1 mi (current)
        "route_cache_radius_m": 250.0,                       # current default
    },
    PRO: {
        "intervals": [60, 30, 15],
        "days_allowed": ALL_DAYS,
        "days_max": 7,
        "from_hours": ALL_HOURS,
        "to_span_max": 6,
        "max_distance_mi": 500,
        "traffic_cache_radius_m": round(1500 * FOOT_M, 3),  # 1500 ft — tightest
        "route_cache_radius_m": 100.0,
    },
}


def _merged_limits():
    """Defaults deep-merged with settings.TIER_LIMITS_OVERRIDES (per tier)."""
    overrides = getattr(settings, "TIER_LIMITS_OVERRIDES", None) or {}
    merged = {}
    for tier in TIERS:
        merged[tier] = {**_DEFAULTS[tier], **(overrides.get(tier) or {})}
    return merged


def limits_for(tier):
    """The resolved limits dict for one tier (defaults + overrides)."""
    if tier not in TIERS:
        tier = ANON
    return _merged_limits()[tier]


def get_user_tier(user):
    """Effective tier for a (possibly anonymous) Django user. Authenticated
    users without a profile row default to FREE."""
    if not user or not user.is_authenticated:
        return ANON
    profile = getattr(user, "profile", None)
    return profile.tier if profile else FREE


def effective_tier(request):
    """Resolve the tier for an incoming request (token → user, else ANON)."""
    return get_user_tier(getattr(request, "user", None))


def public_matrix():
    """The full tier→limits matrix served to the SPA via /api/config, plus the
    UI-only metadata it needs (all interval options + which are 'coming soon')."""
    return {
        "intervals_all": ALL_INTERVALS,
        "intervals_coming_soon": COMING_SOON_INTERVALS,
        "limits": _merged_limits(),
        "next_tier": NEXT_TIER,
    }


def _upsell(tier):
    nxt = NEXT_TIER.get(tier)
    if nxt == FREE:
        return "Sign in for a free account to unlock this."
    if nxt == PRO:
        return "Upgrade to PRO to unlock this."
    return "This option isn't available on your plan."


def check_analyze(tier, *, interval_minutes, days, start_hour, end_hour, distance_mi):
    """Validate an analyze request against `tier`. Returns a list of human
    messages (empty == allowed). Mirrors exactly what the UI grays out."""
    lim = limits_for(tier)
    errors = []
    upsell = _upsell(tier)

    if interval_minutes in COMING_SOON_INTERVALS:
        errors.append(f"The {interval_minutes}-minute interval is coming soon.")
    elif interval_minutes not in lim["intervals"]:
        errors.append(f"The {interval_minutes}-minute interval isn't available on your plan. {upsell}")

    bad_days = sorted(set(days) - set(lim["days_allowed"]))
    if bad_days:
        names = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]
        labels = ", ".join(names[d] for d in bad_days)
        errors.append(f"These days aren't available on your plan: {labels}. {upsell}")
    if len(set(days)) > lim["days_max"]:
        errors.append(f"Your plan allows at most {lim['days_max']} day(s) per analysis. {upsell}")

    if start_hour not in lim["from_hours"]:
        errors.append(f"That From hour isn't available on your plan. {upsell}")
    if end_hour - start_hour > lim["to_span_max"]:
        errors.append(
            f"Your plan allows a window of at most {lim['to_span_max']} hour(s). {upsell}"
        )

    if distance_mi is not None and distance_mi > lim["max_distance_mi"]:
        errors.append(
            f"Origin and destination are too far apart for your plan "
            f"(limit {lim['max_distance_mi']} miles). {upsell}"
        )
    return errors
