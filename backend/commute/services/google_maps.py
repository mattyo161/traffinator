"""Thin client for the Google Maps Distance Matrix and Geocoding APIs.

Every outbound request and its outcome is logged so `docker compose logs -f
backend` shows exactly what is being asked of Google and what came back.
"""

import logging
import os
import time

import requests

from commute import metrics
from commute.coords import round_coord
from commute.models import Setting

logger = logging.getLogger("commute.google")

DISTANCE_MATRIX_URL = "https://maps.googleapis.com/maps/api/distancematrix/json"
GEOCODE_URL = "https://maps.googleapis.com/maps/api/geocode/json"

API_KEY_SETTING = "google_maps_api_key"


class GoogleMapsError(Exception):
    pass


class ApiKeyMissing(GoogleMapsError):
    pass


def get_api_key():
    """ENV var takes precedence; otherwise the key saved via the setup screen."""
    key = os.environ.get("GOOGLE_MAPS_API_KEY")
    if key:
        return key
    row = Setting.objects.filter(key=API_KEY_SETTING).first()
    if row and row.value:
        return row.value
    raise ApiKeyMissing("Google Maps API key is not configured.")


def is_configured():
    try:
        get_api_key()
        return True
    except ApiKeyMissing:
        return False


def _request(url, params, label):
    redacted = {k: v for k, v in params.items() if k != "key"}
    logger.info("Google request [%s]: %s params=%s", label, url, redacted)
    # Endpoint label for metrics: "distance-matrix/best_guess" -> "distance_matrix".
    endpoint = label.split("/")[0].replace("-", "_")
    start = time.monotonic()
    try:
        resp = requests.get(url, params=params, timeout=30)
    except requests.RequestException as exc:
        metrics.EXTERNAL_API_DURATION.labels("google_maps", endpoint).observe(
            time.monotonic() - start
        )
        metrics.record_call("google_maps", endpoint, "paid", "error")
        logger.error("Google request [%s] failed: %s", label, exc)
        raise GoogleMapsError(f"Google Maps request failed: {exc}") from exc
    data = resp.json()
    status = data.get("status")
    metrics.EXTERNAL_API_DURATION.labels("google_maps", endpoint).observe(
        time.monotonic() - start
    )
    metrics.record_call(
        "google_maps", endpoint, "paid", "ok" if (resp.ok and status == "OK") else "error"
    )
    logger.info(
        "Google response [%s]: http=%s status=%s error=%s",
        label, resp.status_code, status, data.get("error_message"),
    )
    return data


def validate_key(key):
    """Cheap geocode call to confirm the key works before saving it."""
    data = _request(GEOCODE_URL, {"address": "New York, NY", "key": key}, "validate-key")
    if data.get("status") != "OK":
        raise GoogleMapsError(
            data.get("error_message") or f"Key validation failed (status={data.get('status')})."
        )


def geocode(query, region=None):
    """Return up to 5 candidate locations so the user can confirm the right
    one. `region` (ccTLD, e.g. 'us') biases — but does not restrict — results."""
    params = {"address": query, "key": get_api_key()}
    if region:
        params["region"] = region
    data = _request(GEOCODE_URL, params, "geocode")
    status = data.get("status")
    if status == "ZERO_RESULTS":
        return []
    if status != "OK" or not data.get("results"):
        raise GoogleMapsError(data.get("error_message") or f"Geocoding failed (status={status}).")
    return [
        {
            "lat": round_coord(r["geometry"]["location"]["lat"]),
            "lng": round_coord(r["geometry"]["location"]["lng"]),
            "address": r["formatted_address"],
        }
        for r in data["results"][:5]
    ]


def _distance_matrix(origin, destination, departure_epoch, traffic_model, counter=None):
    params = {
        "origins": f"{origin['lat']},{origin['lng']}",
        "destinations": f"{destination['lat']},{destination['lng']}",
        "mode": "driving",
        "departure_time": int(departure_epoch),
        "traffic_model": traffic_model,
        "key": get_api_key(),
    }
    data = _request(DISTANCE_MATRIX_URL, params, f"distance-matrix/{traffic_model}")
    if counter is not None:
        # Counted as soon as the HTTP request completes: even responses that
        # fail validation below were real (billable) API calls.
        counter.add(1)
    if data.get("status") != "OK":
        raise GoogleMapsError(
            data.get("error_message") or f"Distance Matrix failed (status={data.get('status')})."
        )
    element = data["rows"][0]["elements"][0]
    if element.get("status") != "OK":
        raise GoogleMapsError(f"No route between points (status={element.get('status')}).")
    duration_s = element.get("duration_in_traffic", element["duration"])["value"]
    logger.info(
        "  -> %s duration=%ss distance=%sm",
        traffic_model, duration_s, element.get("distance", {}).get("value"),
    )
    return {
        "duration_s": duration_s,
        "distance_m": element.get("distance", {}).get("value"),
        "raw": data,
    }


def best_guess_duration(origin, destination, departure_epoch, counter=None):
    """Single best_guess probe (used to estimate departure for arrival-mode)."""
    return _distance_matrix(origin, destination, departure_epoch, "best_guess", counter)


def predict(origin, destination, departure_epoch, counter=None):
    """Fetch optimistic / best_guess / pessimistic predictions for one departure.

    Returns min/typical/max durations (clamped so min <= typical <= max even if
    the models disagree) plus all three raw API payloads.
    """
    results = {
        model: _distance_matrix(origin, destination, departure_epoch, model, counter)
        for model in ("optimistic", "best_guess", "pessimistic")
    }
    durations = {m: r["duration_s"] for m, r in results.items()}
    typical = durations["best_guess"]
    return {
        "duration_min_s": min(durations.values()),
        "duration_typical_s": typical,
        "duration_max_s": max(durations.values()),
        "distance_m": results["best_guess"]["distance_m"],
        "raw": {m: r["raw"] for m, r in results.items()},
    }
