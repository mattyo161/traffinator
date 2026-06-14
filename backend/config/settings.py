import os
from pathlib import Path

import dj_database_url

BASE_DIR = Path(__file__).resolve().parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY") or "dev-only-insecure-secret-key"
DEBUG = os.environ.get("DJANGO_DEBUG", "0") == "1"
ALLOWED_HOSTS = ["*"]

INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "rest_framework.authtoken",
    "commute",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"
WSGI_APPLICATION = "config.wsgi.application"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {"context_processors": []},
    }
]

DATABASES = {
    "default": dj_database_url.config(
        default="postgresql://commute:commute@db:5432/commute",
        conn_max_age=60,
    )
}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Decimals to round stored lat/lng to (≈6 ≈ a few feet). Keeps the cache clean
# and dedupes near-identical geocoder results. See commute/coords.py.
COORDINATE_PRECISION = int(os.environ.get("COORDINATE_PRECISION", "6"))

# Shared cache used by DRF throttling. DatabaseCache keeps throttle counters
# consistent across gunicorn workers and backend pods using the existing
# Postgres — no extra infra — so per-client limits and the global cap actually
# hold under concurrency. Swap for Redis (django-redis) for higher throughput.
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.db.DatabaseCache",
        "LOCATION": "commute_cache",
    }
}

REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework.authentication.TokenAuthentication",
    ],
    # Endpoints are public by default (demo mode); saved-data views opt in to
    # IsAuthenticated explicitly. The paid Google-backed endpoints (analyze /
    # route / geocode) stay public but are rate-limited (see commute.throttles).
    "DEFAULT_PERMISSION_CLASSES": ["rest_framework.permissions.AllowAny"],
    "DEFAULT_RENDERER_CLASSES": ["rest_framework.renderers.JSONRenderer"],
    "UNAUTHENTICATED_USER": None,
    # Rate limits (env-configurable). analyze is heaviest (many Google calls per
    # request); route+geocode share the lighter "lookup" budget; google_global
    # is a coarse cross-client daily circuit-breaker on total billable traffic.
    "DEFAULT_THROTTLE_RATES": {
        "analyze_anon": os.environ.get("THROTTLE_ANALYZE_ANON", "5/hour"),
        "analyze_user": os.environ.get("THROTTLE_ANALYZE_USER", "60/hour"),
        "lookup_anon": os.environ.get("THROTTLE_LOOKUP_ANON", "30/hour"),
        "lookup_user": os.environ.get("THROTTLE_LOOKUP_USER", "120/hour"),
        "google_global": os.environ.get("THROTTLE_GOOGLE_GLOBAL", "2000/day"),
    },
}

# Google OAuth: the SPA obtains an ID token via Google Identity Services and
# posts it to /api/auth/google, which verifies it against this client ID.
GOOGLE_OAUTH_CLIENT_ID = os.environ.get("GOOGLE_OAUTH_CLIENT_ID", "")

# Apple "Sign in with Apple" — scaffolded, disabled until configured.
APPLE_OAUTH_CLIENT_ID = os.environ.get("APPLE_OAUTH_CLIENT_ID", "")

USE_TZ = True
TIME_ZONE = "UTC"

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "verbose": {"format": "[{asctime}] {levelname} {name}: {message}", "style": "{"},
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "verbose"},
    },
    "loggers": {
        "commute": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django": {"handlers": ["console"], "level": "WARNING"},
    },
}
