"""The spatial/temporal cache rules:
1-mile radius on both endpoints, exact day-of-week, absolute 4-minute time
delta (wrapping midnight), and records expire after 7 days.
"""

import datetime as dt

from django.test import TestCase
from django.utils import timezone

from commute.services import cache
from commute.tests.factories import (
    DEST,
    HALF_MILE_DEG,
    ORIGIN,
    TWO_MILES_DEG,
    make_sample,
)


class CacheLookupTests(TestCase):
    def lookup(self, **overrides):
        params = dict(
            origin=ORIGIN,
            destination=DEST,
            vector="departure",
            day_of_week=0,
            time_of_day=dt.time(8, 0),
        )
        params.update(overrides)
        return cache.find_cached(**params)

    def test_exact_match_hits(self):
        sample = make_sample()
        self.assertEqual(self.lookup().pk, sample.pk)

    def test_origin_within_one_mile_hits(self):
        sample = make_sample(origin_lat=ORIGIN["lat"] + HALF_MILE_DEG)
        self.assertEqual(self.lookup().pk, sample.pk)

    def test_origin_beyond_one_mile_misses(self):
        make_sample(origin_lat=ORIGIN["lat"] + TWO_MILES_DEG)
        self.assertIsNone(self.lookup())

    def test_destination_beyond_one_mile_misses(self):
        make_sample(dest_lat=DEST["lat"] + TWO_MILES_DEG)
        self.assertIsNone(self.lookup())

    def test_wrong_day_misses(self):
        make_sample(day_of_week=1)
        self.assertIsNone(self.lookup(day_of_week=0))

    def test_wrong_vector_misses(self):
        make_sample(vector="arrival")
        self.assertIsNone(self.lookup(vector="departure"))

    def test_time_within_four_minutes_hits(self):
        sample = make_sample(time_of_day=dt.time(8, 4))
        self.assertEqual(self.lookup(time_of_day=dt.time(8, 0)).pk, sample.pk)

    def test_time_beyond_four_minutes_misses(self):
        make_sample(time_of_day=dt.time(8, 5))
        self.assertIsNone(self.lookup(time_of_day=dt.time(8, 0)))

    def test_time_delta_wraps_midnight(self):
        sample = make_sample(time_of_day=dt.time(23, 58))
        self.assertEqual(self.lookup(time_of_day=dt.time(0, 1)).pk, sample.pk)

    def test_stale_record_misses(self):
        make_sample(created_at=timezone.now() - dt.timedelta(days=8))
        self.assertIsNone(self.lookup())

    def test_six_day_old_record_still_hits(self):
        sample = make_sample(created_at=timezone.now() - dt.timedelta(days=6))
        self.assertEqual(self.lookup().pk, sample.pk)

    def test_freshest_matching_record_wins(self):
        make_sample(created_at=timezone.now() - dt.timedelta(days=3))
        newest = make_sample(created_at=timezone.now() - dt.timedelta(hours=1))
        self.assertEqual(self.lookup().pk, newest.pk)
