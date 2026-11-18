# SPDX-License-Identifier: MPL-2.0
"""Protect error responses after Django has reported a private-view exception."""


class PrivateErrorCacheMiddleware:
    """Apply no-store to errors from explicitly marked private view wrappers.

    Django's exception handler still handles and reports the original exception;
    this middleware only adjusts the response it produces.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if getattr(request, "_railet_private_response", False) and response.status_code >= 500:
            response["Cache-Control"] = "private, no-store"
            response["Pragma"] = "no-cache"
            response["Expires"] = "0"
        return response
