import logging
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from django.conf import settings
from rest_framework import status, viewsets
from rest_framework.authtoken.models import Token
from rest_framework.decorators import api_view, throttle_classes
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from commute import throttles, tiers
from commute.coords import haversine_miles
from commute.models import SavedAddress, SavedRoute, Setting
from commute.serializers import (
    AnalyzeRequestSerializer,
    GeocodeRequestSerializer,
    GoogleAuthSerializer,
    RouteRequestSerializer,
    SavedAddressSerializer,
    SavedRouteSerializer,
    SetupRequestSerializer,
)
from commute.services import analysis, auth, google_maps, routing

logger = logging.getLogger("commute.views")


@api_view(["GET"])
def config(request):
    """Public runtime config the SPA needs at startup, including the requester's
    effective tier and the full tier→limits matrix (so the UI grays-out/upsells
    from the same data the API enforces — see commute.tiers)."""
    return Response({
        "configured": google_maps.is_configured(),
        "google_oauth_client_id": settings.GOOGLE_OAUTH_CLIENT_ID,
        "apple_oauth_enabled": bool(settings.APPLE_OAUTH_CLIENT_ID),
        "tier": tiers.effective_tier(request),
        "tiers": tiers.public_matrix(),
    })


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
@throttle_classes([
    throttles.GlobalGoogleThrottle,
    throttles.LookupAnonThrottle,
    throttles.LookupUserThrottle,
])
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
@throttle_classes([
    throttles.GlobalGoogleThrottle,
    throttles.LookupAnonThrottle,
    throttles.LookupUserThrottle,
])
def route(request):
    serializer = RouteRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    # Per-tier route-cache radius only when enforcement is on (else default).
    route_kwargs = {}
    if settings.TIER_ENFORCEMENT_ENABLED:
        tier = tiers.effective_tier(request)
        route_kwargs["cache_radius_m"] = tiers.limits_for(tier)["route_cache_radius_m"]
    try:
        result = routing.get_route(data["origin"], data["destination"], **route_kwargs)
    except routing.RoutingError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
    return Response(result)


@api_view(["POST"])
@throttle_classes([
    throttles.GlobalGoogleThrottle,
    throttles.AnalyzeAnonThrottle,
    throttles.AnalyzeUserThrottle,
])
def analyze(request):
    serializer = AnalyzeRequestSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    data = serializer.validated_data
    try:
        ZoneInfo(data["timezone"])
    except (ZoneInfoNotFoundError, ValueError):
        return Response({"error": f"Unknown timezone '{data['timezone']}'."},
                        status=status.HTTP_400_BAD_REQUEST)

    # Tier enforcement (authoritative; mirrors the matrix the SPA grays-out
    # from). Gated by TIER_ENFORCEMENT_ENABLED so the backend can ship ahead of
    # the tier-aware SPA — when off, requests aren't rejected and the cache uses
    # its default radius (behavior unchanged). See commute.tiers / issue #32.
    tier = tiers.effective_tier(request)
    cache_radius_m = None
    if settings.TIER_ENFORCEMENT_ENABLED:
        violations = tiers.check_analyze(
            tier,
            interval_minutes=data["interval_minutes"],
            days=data["days"],
            start_hour=data["start_hour"],
            end_hour=data["end_hour"],
            distance_mi=haversine_miles(data["origin"], data["destination"]),
        )
        if violations:
            return Response(
                {"error": " ".join(violations), "tier": tier, "upsell": True},
                status=status.HTTP_403_FORBIDDEN,
            )
        cache_radius_m = tiers.limits_for(tier)["traffic_cache_radius_m"]

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
            cache_radius_m=cache_radius_m,
        )
    except google_maps.ApiKeyMissing as exc:
        return Response({"error": str(exc)}, status=status.HTTP_409_CONFLICT)
    except google_maps.GoogleMapsError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_502_BAD_GATEWAY)
    return Response(result)


@api_view(["POST"])
def google_login(request):
    serializer = GoogleAuthSerializer(data=request.data)
    serializer.is_valid(raise_exception=True)
    try:
        user = auth.verify_google_token(serializer.validated_data["credential"])
    except auth.AuthError as exc:
        return Response({"error": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)
    token, _ = Token.objects.get_or_create(user=user)
    return Response({
        "token": token.key,
        "user": {"email": user.email, "name": user.get_full_name() or user.email},
    })


@api_view(["POST"])
def logout(request):
    if request.user and request.user.is_authenticated:
        Token.objects.filter(user=request.user).delete()
    return Response({"ok": True})


@api_view(["GET"])
def me(request):
    if not (request.user and request.user.is_authenticated):
        return Response({"authenticated": False})
    user = request.user
    return Response({
        "authenticated": True,
        "user": {"email": user.email, "name": user.get_full_name() or user.email},
    })


class _OwnerScopedViewSet(viewsets.ModelViewSet):
    """ModelViewSet limited to the requesting user's own rows."""

    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        return self.queryset.filter(user=self.request.user)

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class SavedAddressViewSet(_OwnerScopedViewSet):
    queryset = SavedAddress.objects.all()
    serializer_class = SavedAddressSerializer


class SavedRouteViewSet(_OwnerScopedViewSet):
    queryset = SavedRoute.objects.all()
    serializer_class = SavedRouteSerializer
