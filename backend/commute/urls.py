from django.urls import path

from commute import views

urlpatterns = [
    path("setup/status", views.setup_status),
    path("setup", views.setup),
    path("geocode", views.geocode),
    path("analyze", views.analyze),
]
