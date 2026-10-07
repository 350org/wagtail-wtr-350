"""
Tests for wtrx/request_context.py.
"""

from django.test import RequestFactory, SimpleTestCase

from wtrx.request_context import CurrentRequestMiddleware, get_current_request


class TestCurrentRequestMiddleware(SimpleTestCase):
    def test_context_set_during_request_and_cleared_after(self):
        seen = {}

        def get_response(request):
            seen["during"] = get_current_request()
            return "ok"

        middleware = CurrentRequestMiddleware(get_response)
        request = RequestFactory().get("/")
        result = middleware(request)

        self.assertEqual(result, "ok")
        self.assertIs(seen["during"], request)
        self.assertIsNone(get_current_request())

    def test_context_cleared_even_if_the_view_raises(self):
        def get_response(request):
            raise ValueError("boom")

        middleware = CurrentRequestMiddleware(get_response)
        request = RequestFactory().get("/")

        with self.assertRaises(ValueError):
            middleware(request)

        self.assertIsNone(get_current_request())

    def test_no_request_in_scope_returns_none(self):
        self.assertIsNone(get_current_request())
