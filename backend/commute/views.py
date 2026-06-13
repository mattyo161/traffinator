import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from rest_framework import status
from rest_framework.decorators import api_view
from rest_framework.response import Response

from commute.models import Setting
from commute.serializers import (
    AnalyzeRequestSerializer,
    GeocodeRequestSerializer,
    SetupRequestSerializer,
)
from commute.services import analysis, google_maps

logger = logging.getLogger("commute.views")


@api_view(["GET"])
def setup_status(request):
    return Response({"configured": google_maps.is_configured()})


@api_view(["POST"])
def setup(request):
    serializer = SetupRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    key = serializer.validated_data["api_key"].strip()
    try:
        google_maps.validate_key(key)
    except google_maps.GoogleMapsError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    Setting.objects.update_or_create(
        key=google_maps.API_KEY_SETTING, defaults={"value": key}
    )
    logger.info("Google Maps API key validated and saved to database.")
    return Response({"configured": True})


@api_view(["POST"])
def geocode(request):
    serializer = GeocodeRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        results = google_maps.geocode(
            serializer.validated_data["query"],
            region=serializer.validated_data["region"] or None,
        )
    except google_maps.ApiKeyMissing as exc:
        return Response({"error": str(exc)}, status=status.HTTP_409_CONFLICT)
    except google_maps.GoogleMapsError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
    return Response({"results": results})


@api_view(["POST"])
def analyze(request):
    serializer = AnalyzeRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    try:
        ZoneInfo(data["timezone"])
    except (ZoneInfoNotFoundError, ValueError):
        return Response({"error": f"Unknown timezone '{data['timezone']}'."},
                        status=status.HTTP_400_BAD_REQUEST)
    try:
        result = analysis.run_analysis(
            origin=data["origin"],
            destination=data["destination"],
            vector=data["vector"],
            start_hour=data["start_hour"],
            end_hour=data["end_hour"],
            interval_minutes=data["interval_minutes"],
            days=data["days"],
            timezone_name=data["timezone"],
        )
    except google_maps.ApiKeyMissing as exc:
        return Response({"error": str(exc)}, status=status.HTTP_409_CONFLICT)
    except google_maps.GoogleMapsError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
    return Response(result)
