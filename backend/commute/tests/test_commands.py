import csv
import datetime as dt
import io
import os
import tempfile

from django.core.management import call_command
from django.test import TestCase

from commute.models import TrafficSample
from commute.tests.factories import make_sample


class CacheCsvRoundTripTests(TestCase):
    def test_dump_then_load_restores_samples(self):
        make_sample(day_of_week=2, time_of_day=dt.time(7, 30))
        make_sample(day_of_week=4, time_of_day=dt.time(17, 0), duration_typical_s=2000)

        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "dump.csv")
            call_command("dump_cache", path, stderr=io.StringIO())
            with open(path) as f:
                rows = list(csv.DictReader(f))
            self.assertEqual(len(rows), 2)

            call_command("load_cache", path, "--replace", stderr=io.StringIO())

        self.assertEqual(TrafficSample.objects.count(), 2)
        restored = TrafficSample.objects.get(day_of_week=4)
        self.assertEqual(restored.duration_typical_s, 2000)
        self.assertEqual(restored.time_of_day, dt.time(17, 0))
        self.assertEqual(restored.raw_response["source"], "csv-import")

    def test_load_rejects_csv_with_missing_columns(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "bad.csv")
            with open(path, "w") as f:
                f.write("origin_lat,origin_lng\n1,2\n")
            with self.assertRaises(Exception):
                call_command("load_cache", path, stderr=io.StringIO())
        self.assertEqual(TrafficSample.objects.count(), 0)

    def test_demo_fixture_loads_and_serves_as_cache(self):
        """The committed demo CSV must stay loadable and cache-valid."""
        import datetime as dt

        from commute.services import cache

        call_command("load_cache", "fixtures/demo_commute.csv", stderr=io.StringIO())
        self.assertEqual(TrafficSample.objects.count(), 45)  # 5 days x 9 slots
        hit = cache.find_cached(
            {"lat": 42.3550, "lng": -71.0656},
            {"lat": 42.3293, "lng": -71.1924},
            "departure", 0, dt.time(8, 0),
        )
        self.assertIsNotNone(hit)
