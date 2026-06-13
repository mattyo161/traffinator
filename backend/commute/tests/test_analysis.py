"""Analysis orchestration, with Google's HTTP layer stubbed out.

Includes regression tests for two real bugs:
- ZERO_RESULTS (e.g. an intercontinental "route") must fail per-point but
  still count the API calls that were actually made and billed.
- Arrival mode where `arrival - duration` lands in the past must shift the
  whole point one week forward instead of sending Google a past departure.
"""

import datetime as dt
from unittest import mock
from zoneinfo import ZoneInfo

from django.test import TestCase

from commute.models import TrafficSample
from commute.services import analysis, google_maps
from commute.tests.factories import DEST, ORIGIN, dm_response, make_sample

TZ = "America/New_York"
DURATIONS = {"optimistic": 1100, "best_guess": 1400, "pessimistic": 2000}
# Single worker: runs inline so test-transaction data is visible and writes
# roll back with the test.
FAKE_KEY = {"GOOGLE_MAPS_API_KEY": "test-key", "ANALYSIS_MAX_WORKERS": "1"}


def fake_request_ok(url, params, label):
    return dm_response(DURATIONS[params["traffic_model"]])


def fake_request_zero_results(url, params, label):
    return dm_response(element_status="ZERO_RESULTS")


class TimeSlotTests(TestCase):
    def test_inclusive_range(self):
        slots = analysis.time_slots(7, 9, 15)
        self.assertEqual(len(slots), 9)
        self.assertEqual(slots[0], dt.time(7, 0))
        self.assertEqual(slots[-1], dt.time(9, 0))

    def test_single_hour(self):
        self.assertEqual(analysis.time_slots(8, 8, 30), [dt.time(8, 0)])


class NextOccurrenceTests(TestCase):
    def test_always_future_with_lead_and_correct_day(self):
        tz = ZoneInfo(TZ)
        now = dt.datetime.now(tz)
        for day in range(7):
            result = analysis.next_occurrence(day, dt.time(6, 0), tz)
            self.assertEqual(result.weekday(), day)
            self.assertEqual((result.hour, result.minute), (6, 0))
            self.assertGreaterEqual(result, now + analysis.MIN_LEAD)
            self.assertLessEqual(result - now, dt.timedelta(days=7, minutes=11))


@mock.patch.dict("os.environ", FAKE_KEY)
class RunAnalysisTests(TestCase):
    def run(self, vector="departure", days=(0,), **overrides):
        params = dict(
            origin=ORIGIN,
            destination=DEST,
            vector=vector,
            start_hour=8,
            end_hour=8,
            interval_minutes=30,
            days=list(days),
            timezone_name=TZ,
        )
        params.update(overrides)
        return analysis.run_analysis(**params)

    @mock.patch.object(google_maps, "_request", side_effect=fake_request_ok)
    def test_departure_happy_path(self, _req):
        result = self.run()
        self.assertEqual(result["labels"], ["08:00"])
        point = result["results"][0]["points"][0]
        self.assertEqual(point["min_s"], 1100)
        self.assertEqual(point["typical_s"], 1400)
        self.assertEqual(point["max_s"], 2000)
        self.assertFalse(point["cached"])
        self.assertEqual(result["meta"]["api_calls"], 3)
        self.assertEqual(result["meta"]["cache_hits"], 0)
        self.assertEqual(result["meta"]["errors"], [])

    @mock.patch.object(google_maps, "_request", side_effect=fake_request_ok)
    def test_results_and_raw_responses_are_persisted(self, _req):
        self.run()
        sample = TrafficSample.objects.get()
        self.assertEqual(sample.duration_typical_s, 1400)
        self.assertEqual(
            set(sample.raw_response["responses"]),
            {"optimistic", "best_guess", "pessimistic"},
        )

    def test_cache_hit_makes_no_api_calls(self):
        make_sample(day_of_week=0, time_of_day=dt.time(8, 0))
        forbidden = mock.Mock(side_effect=AssertionError("Google must not be called"))
        with mock.patch.object(google_maps, "_request", forbidden):
            result = self.run()
        point = result["results"][0]["points"][0]
        self.assertTrue(point["cached"])
        self.assertEqual(point["typical_s"], 1200)
        self.assertEqual(result["meta"]["api_calls"], 0)
        self.assertEqual(result["meta"]["cache_hits"], 1)

    @mock.patch.object(google_maps, "_request", side_effect=fake_request_zero_results)
    def test_zero_results_reports_error_and_counts_calls(self, _req):
        result = self.run()
        self.assertEqual(len(result["meta"]["errors"]), 1)
        self.assertIn("ZERO_RESULTS", result["meta"]["errors"][0]["error"])
        point = result["results"][0]["points"][0]
        self.assertIsNone(point["typical_s"])
        # Regression: the failed call was still made (and billed) — it must
        # be counted, not reported as 0.
        self.assertEqual(result["meta"]["api_calls"], 1)
        self.assertEqual(TrafficSample.objects.count(), 0)

    @mock.patch.object(google_maps, "_request", side_effect=fake_request_zero_results)
    def test_arrival_zero_results_counts_probe_call(self, _req):
        result = self.run(vector="arrival")
        self.assertEqual(len(result["meta"]["errors"]), 1)
        self.assertEqual(result["meta"]["api_calls"], 1)


@mock.patch.dict("os.environ", FAKE_KEY)
class ArrivalWeekShiftTests(TestCase):
    def test_unreachable_arrival_shifts_one_week(self):
        """An arrival target ~15 minutes out with a 30-minute drive would
        require departing in the past -> the point must move to next week."""
        tz = ZoneInfo(TZ)
        now = dt.datetime.now(tz)
        slot_dt = now + dt.timedelta(minutes=15)
        slot = dt.time(slot_dt.hour, slot_dt.minute)

        def fake_request(url, params, label):
            return dm_response(30 * 60)

        with mock.patch.object(google_maps, "_request", side_effect=fake_request):
            sample, cached = analysis._fetch_point(
                ORIGIN, DEST, "arrival", slot_dt.weekday(), slot, tz, analysis._Counter()
            )

        self.assertFalse(cached)
        departure = dt.datetime.fromisoformat(sample.raw_response["queried_departure"])
        target = dt.datetime.fromisoformat(sample.raw_response["target_time"])
        self.assertGreater(departure, now)
        self.assertGreaterEqual(target - now, dt.timedelta(days=6))
        self.assertEqual(target.weekday(), slot_dt.weekday())
        self.assertEqual(target - departure, dt.timedelta(minutes=30))

    def test_reachable_arrival_stays_this_week(self):
        """An arrival far enough out keeps its original occurrence."""
        tz = ZoneInfo(TZ)
        now = dt.datetime.now(tz)
        slot_dt = now + dt.timedelta(hours=3)
        slot = dt.time(slot_dt.hour, slot_dt.minute)

        def fake_request(url, params, label):
            return dm_response(30 * 60)

        with mock.patch.object(google_maps, "_request", side_effect=fake_request):
            sample, _ = analysis._fetch_point(
                ORIGIN, DEST, "arrival", slot_dt.weekday(), slot, tz, analysis._Counter()
            )

        target = dt.datetime.fromisoformat(sample.raw_response["target_time"])
        self.assertLess(target - now, dt.timedelta(days=1))
