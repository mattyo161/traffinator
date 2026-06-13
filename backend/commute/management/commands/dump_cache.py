"""Export cached traffic samples to CSV, so real runs can be recorded and
replayed later with `load_cache` (e.g. for frontend previews or test data)."""

import csv
import sys

from django.core.management.base import BaseCommand

from commute.models import TrafficSample

FIELDS = [
    "origin_lat", "origin_lng", "dest_lat", "dest_lng", "vector",
    "day_of_week", "time_of_day", "duration_min_s", "duration_typical_s",
    "duration_max_s", "distance_m",
]


class Command(BaseCommand):
    help = "Export cached traffic samples as CSV (to a file, or stdout by default)."

    def add_arguments(self, parser):
        parser.add_argument("csv_path", nargs="?", default="-",
                            help="Output file path, or '-' for stdout (default).")

    def handle(self, *args, **options):
        path = options["csv_path"]
        out = sys.stdout if path == "-" else open(path, "w", newline="")
        try:
            writer = csv.writer(out)
            writer.writerow(FIELDS)
            count = 0
            for s in TrafficSample.objects.order_by("day_of_week", "time_of_day"):
                writer.writerow([
                    s.origin_lat, s.origin_lng, s.dest_lat, s.dest_lng, s.vector,
                    s.day_of_week, s.time_of_day.strftime("%H:%M:%S"),
                    s.duration_min_s, s.duration_typical_s, s.duration_max_s,
                    s.distance_m if s.distance_m is not None else "",
                ])
                count += 1
        finally:
            if out is not sys.stdout:
                out.close()
        self.stderr.write(f"Exported {count} samples.")
