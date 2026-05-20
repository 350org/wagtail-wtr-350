"""Reverse-proxy helper: optional X-Forwarded-Proto when TRUST_EDGE_TLS is set."""

from __future__ import annotations

import os


class AssumeTlsFromEdgeMiddleware:
    """If TRUST_EDGE_TLS is set and X-Forwarded-Proto is missing, assume https."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if os.environ.get("TRUST_EDGE_TLS", "").lower() in ("true", "1", "yes"):
            if not (request.META.get("HTTP_X_FORWARDED_PROTO") or "").strip():
                request.META["HTTP_X_FORWARDED_PROTO"] = "https"
        return self.get_response(request)
