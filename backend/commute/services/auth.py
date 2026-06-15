"""Google OAuth: verify a Google ID token and map it to a Django user.

The SPA uses Google Identity Services to obtain an ID token client-side, then
posts it here. We verify the token's signature and audience server-side, so
the client never holds a long-lived secret.
"""

import logging

from django.conf import settings
from django.contrib.auth.models import User
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token

from commute.models import UserProfile

logger = logging.getLogger("commute.auth")


class AuthError(Exception):
    pass


def verify_google_token(token):
    """Validate a Google ID token; return the user (created on first sign-in)."""
    if not settings.GOOGLE_OAUTH_CLIENT_ID:
        raise AuthError("Google sign-in is not configured on the server.")
    try:
        info = id_token.verify_oauth2_token(
            token, google_requests.Request(), settings.GOOGLE_OAUTH_CLIENT_ID
        )
    except ValueError as exc:
        logger.warning("Rejected Google token: %s", exc)
        raise AuthError("Invalid Google token.") from exc

    if not info.get("email_verified"):
        raise AuthError("Google account email is not verified.")

    email = info["email"]
    sub = info["sub"]  # stable Google user id
    # Username must be unique and stable; the Google subject id is both.
    user, created = User.objects.get_or_create(
        username=f"google:{sub}",
        defaults={
            "email": email,
            "first_name": info.get("given_name", "")[:30],
            "last_name": info.get("family_name", "")[:150],
        },
    )
    updates = []
    # OAuth-only accounts must never have a usable password. get_or_create leaves
    # a new user with an empty (and, per Django, "usable") password, so mark it
    # unusable explicitly — this also backfills a pre-existing account on its
    # next login.
    if user.has_usable_password():
        user.set_unusable_password()
        updates.append("password")
    if not created and user.email != email:
        user.email = email
        updates.append("email")
    if updates:
        user.save(update_fields=updates)
    # Every authenticated user has a profile (default FREE); backfills accounts
    # created before tiers existed on their next sign-in.
    UserProfile.objects.get_or_create(user=user)
    logger.info("Google sign-in %s for %s", "created user" if created else "ok", email)
    return user
