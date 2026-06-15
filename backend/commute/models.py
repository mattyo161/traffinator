from django.db import models


class UserProfile(models.Model):
    """Per-user tier + optional sub-tier label. ANON is the no-account case, so
    a profile only exists for authenticated users; new accounts default to FREE
    (see commute.services.auth). PRO is granted manually (admin/DB) for now.

    The tier→limits matrix itself lives in commute.tiers — this only records
    *which* tier a user is on."""

    TIER_CHOICES = [("FREE", "FREE"), ("PRO", "PRO")]
    # PRO sub-tiers are labels only for v1 (all share PRO limits — see #36).
    SUB_TIER_CHOICES = [
        ("", "—"),
        ("TRIAL", "TRIAL"),
        ("COMP", "COMP"),
        ("USER", "USER"),
        ("TEAM", "TEAM"),
    ]

    user = models.OneToOneField(
        "auth.User", on_delete=models.CASCADE, related_name="profile"
    )
    tier = models.CharField(max_length=8, choices=TIER_CHOICES, default="FREE")
    sub_tier = models.CharField(
        max_length=8, choices=SUB_TIER_CHOICES, blank=True, default=""
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        label = f"{self.tier}/{self.sub_tier}" if self.sub_tier else self.tier
        return f"{self.user} [{label}]"


class Setting(models.Model):
    """App-level key/value settings (e.g. the Google Maps API key entered
    through the first-launch setup screen). ENV vars take precedence."""

    key = models.CharField(max_length=64, unique=True)
    value = models.TextField()
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return self.key


class TrafficSample(models.Model):
    """One cached predictive traffic measurement for a single
    (origin, destination, vector, day-of-week, time-of-day) point.

    duration_min/typical/max come from Google's optimistic / best_guess /
    pessimistic traffic models; raw_response stores the full API payloads.
    """

    VECTOR_CHOICES = [("departure", "departure"), ("arrival", "arrival")]

    origin_lat = models.FloatField()
    origin_lng = models.FloatField()
    dest_lat = models.FloatField()
    dest_lng = models.FloatField()
    vector = models.CharField(max_length=10, choices=VECTOR_CHOICES)
    day_of_week = models.PositiveSmallIntegerField()  # 0=Monday .. 6=Sunday
    time_of_day = models.TimeField()
    duration_min_s = models.PositiveIntegerField()
    duration_typical_s = models.PositiveIntegerField()
    duration_max_s = models.PositiveIntegerField()
    distance_m = models.PositiveIntegerField(null=True, blank=True)
    raw_response = models.JSONField()
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        indexes = [
            models.Index(fields=["vector", "day_of_week"]),
        ]


class RouteGeometry(models.Model):
    """Cached driving-route geometry (the road path drawn on the map).

    Stored as an ordered list of [lat, lng] points. Cached spatially so
    near-identical requests reuse the same polyline, which also seeds future
    corridor/overlap analysis between commutes."""

    origin_lat = models.FloatField()
    origin_lng = models.FloatField()
    dest_lat = models.FloatField()
    dest_lng = models.FloatField()
    provider = models.CharField(max_length=20)
    distance_m = models.PositiveIntegerField(null=True, blank=True)
    geometry = models.JSONField()  # [[lat, lng], ...]
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)


class SavedAddress(models.Model):
    """A user's saved place (home, work, gym, ...)."""

    user = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, related_name="saved_addresses"
    )
    label = models.CharField(max_length=120)
    address = models.CharField(max_length=500)
    lat = models.FloatField()
    lng = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["label"]


class SavedRoute(models.Model):
    """A user's saved commute: endpoints plus the analysis parameters."""

    user = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, related_name="saved_routes"
    )
    name = models.CharField(max_length=120)
    origin_label = models.CharField(max_length=500)
    origin_lat = models.FloatField()
    origin_lng = models.FloatField()
    dest_label = models.CharField(max_length=500)
    dest_lat = models.FloatField()
    dest_lng = models.FloatField()
    params = models.JSONField(default=dict)  # vector, hours, interval, days, palette
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
