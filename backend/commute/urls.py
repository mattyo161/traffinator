from django.urls import path
from rest_framework.routers import DefaultRouter

from commute import views

router = DefaultRouter()
router.register("saved-addresses", views.SavedAddressViewSet, basename="saved-address")
router.register("saved-routes", views.SavedRouteViewSet, basename="saved-route")

urlpatterns = [
    path("config", views.config),
    path("setup/status", views.setup_status),
    path("setup", views.setup),
    path("geocode", views.geocode),
    path("route", views.route),
    path("analyze", views.analyze),
    path("auth/google", views.google_login),
    path("auth/logout", views.logout),
    path("auth/me", views.me),
] + router.urls
