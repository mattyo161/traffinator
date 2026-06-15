from django.urls import include, path

urlpatterns = [
    path("api/", include("commute.urls")),
    # Prometheus /metrics (scraped directly off the backend Service, not via the
    # /api nginx proxy). In multiprocess mode (PROMETHEUS_MULTIPROC_DIR set) the
    # django-prometheus view aggregates across gunicorn workers.
    path("", include("django_prometheus.urls")),
]
