"""Reverse-proxy helper: optional X-Forwarded-Proto when TRUST_EDGE_TLS is set."""

from __future__ import annotations

import os

from wagtail_2fa.middleware import VerifyUserMiddleware as _WagtailVerifyUserMiddleware


class AssumeTlsFromEdgeMiddleware:
    """If TRUST_EDGE_TLS is set and X-Forwarded-Proto is missing, assume https."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if os.environ.get("TRUST_EDGE_TLS", "").lower() in ("true", "1", "yes"):
            if not (request.META.get("HTTP_X_FORWARDED_PROTO") or "").strip():
                request.META["HTTP_X_FORWARDED_PROTO"] = "https"
        return self.get_response(request)


class ScopedVerifyUserMiddleware(_WagtailVerifyUserMiddleware):
    """
    wagtail_2fa's VerifyUserMiddleware checks every request site-wide, not just
    admin ones: a staff/superuser without a TOTP device browsing the public
    site — in the same browser session as their admin login — gets redirected
    to 2FA device setup on the FRONTEND too. Scope enforcement to /admin/ and
    /django-admin/ only, where it's actually meant to apply.

    Also extends the exempt url_names beyond wagtail_2fa's own list (which only
    covers Wagtail core's own JS catalog/sprite). wagtail_ai and wtrx both
    inject <script src="..."> tags globally on every admin page via
    insert_global_admin_js — including the 2FA device-setup page itself. While
    unverified, those background script requests were getting redirected back
    into /admin/2fa/devices/new, whose GET handler *deletes and recreates* the
    unconfirmed device (wagtail_2fa.utils.new_unconfirmed_device) on every hit.
    That silently invalidated the secret/QR code multiple times per minute
    during setup, well before anyone could scan + enter a code in time —
    every attempt looked like "Invalid token" even with a correct code.
    """

    _allowed_url_names = _WagtailVerifyUserMiddleware._allowed_url_names + [
        "javascript_catalog",  # wagtail_ai's admin JS i18n catalog
        "wtrx_block_visibility_js",
    ]

    def _require_verified_user(self, request):
        if not (
            request.path.startswith("/admin/")
            or request.path.startswith("/django-admin/")
        ):
            return False
        return super()._require_verified_user(request)
