from django.db import models


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
