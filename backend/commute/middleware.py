"""Anonymous identity cookie.

Issues a signed, httpOnly ``anon_id`` cookie to unauthenticated visitors so ANON
tier limits / abuse counting can be keyed on a stable id (alongside IP), and so
later conversion tracking (#37) and the ANON day-lock (#34) have something to
hang off. Signed with SECRET_KEY, so a client can't forge or rotate it freely.

It is purely a tracking id — never an authentication credential.
"""

import uuid

ANON_COOKIE = "anon_id"
ANON_COOKIE_MAX_AGE = 60 * 60 * 24 * 365  # 1 year


class AnonCookieMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        existing = request.get_signed_cookie(ANON_COOKIE, default=None)
        issue = None
        if existing:
            request.anon_id = existing
        else:
            request.anon_id = issue = uuid.uuid4().hex

        response = self.get_response(request)

        # Only (re)issue for anonymous requests — authenticated users are keyed
        # on their account, not the cookie.
        authed = getattr(request, "user", None) and request.user.is_authenticated
        if issue and not authed:
            response.set_signed_cookie(
                ANON_COOKIE,
                issue,
                max_age=ANON_COOKIE_MAX_AGE,
                httponly=True,
                samesite="Lax",
                secure=request.is_secure(),
            )
        return response
