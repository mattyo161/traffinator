"""Import traffic samples from a CSV (as produced by `dump_cache`) into the
cache. Imported rows get a fresh timestamp, so they serve as cache hits for
the next 7 days — ideal for frontend previews without spending API calls."""

import csv
import os

from django.core.management.base import BaseCommand, CommandError

from commute.models import TrafficSample
from commute.management.commands.dump_cache import FIELDS


class Command(BaseCommand):
    help = "Import traffic samples from a CSV file into the cache."

    def add_arguments(self, parser):
        parser.add_argument("csv_path")
        parser.add_argument("--replace", action="store_true",
                            help="Delete all existing samples first.")

    def handle(self, *args, **options):
        path = options["csv_path"]
        if not os.path.exists(path):
            raise CommandError(f"File not found: {path}")

        if options["replace"]:
            deleted, _ = TrafficSample.objects.all().delete()
            self.stderr.write(f"Deleted {deleted} existing samples.")

        created = 0
        with open(path, newline="") as f:
            reader = csv.DictReader(f)
            missing = set(FIELDS) - set(reader.fieldnames or [])
            if missing:
                raise CommandError(f"CSV is missing columns: {', '.join(sorted(missing))}")
            for row in reader:
                TrafficSample.objects.create(
                    origin_lat=float(row["origin_lat"]),
                    origin_lng=float(row["origin_lng"]),
                    dest_lat=float(row["dest_lat"]),
                    dest_lng=float(row["dest_lng"]),
                    vector=row["vector"],
                    day_of_week=int(row["day_of_week"]),
                    time_of_day=row["time_of_day"],
                    duration_min_s=int(row["duration_min_s"]),
                    duration_typical_s=int(row["duration_typical_s"]),
                    duration_max_s=int(row["duration_max_s"]),
                    distance_m=int(row["distance_m"]) if row["distance_m"] else None,
                    raw_response={"source": "csv-import", "file": os.path.basename(path)},
                )
                created += 1
        self.stderr.write(f"Imported {created} samples (valid as cache hits for 7 days).")
