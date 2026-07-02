#!/usr/bin/env python3
"""Unit tests for CloudProcessor endpoint migration + 429 body-aware handling.

These tests are fully offline: the HTTP layer and file I/O are mocked, so no
API key, network access, or sample documents are required.

Regression coverage for the bug where docstrange POSTed to nanonets' deprecated
`/extract` endpoint (which now returns HTTP 429 with a *deprecation* body) and
the 429 handler blindly reported "Rate limit exceeded (10k/month)" for any key
holder — masking the real cause and falsely implying an exhausted quota.
"""

import io
import json
import unittest
from unittest import mock

from docstrange.exceptions import ConversionError
from docstrange.processors.cloud_processor import CloudConversionResult, CloudProcessor


class _FakeResponse:
    """Minimal stand-in for requests.Response."""

    def __init__(self, status_code=200, json_body=None, text=""):
        self.status_code = status_code
        self._json_body = json_body
        self.text = text

    def json(self):
        if self._json_body is None:
            raise ValueError("no json body")
        return self._json_body

    def raise_for_status(self):
        if self.status_code >= 400:
            raise AssertionError(
                f"raise_for_status() called for {self.status_code}"
            )


def _make_result(api_key=None):
    processor = CloudProcessor(api_key=api_key)
    result = CloudConversionResult(file_path="doc.pdf", cloud_processor=processor)
    return processor, result


class CloudProcessorEndpointTests(unittest.TestCase):
    def test_uses_current_sync_endpoint(self):
        processor = CloudProcessor()
        self.assertEqual(
            processor.api_url,
            "https://extraction-api.nanonets.com/api/v1/extract/sync",
        )
        self.assertNotIn("/extract\"", processor.api_url)

    def test_request_sends_output_format(self):
        processor, result = _make_result(api_key="k")
        captured = {}

        def fake_post(url, headers=None, files=None, data=None, timeout=None):
            captured["url"] = url
            captured["data"] = data
            return _FakeResponse(
                status_code=200,
                json_body={
                    "success": True,
                    "output_format": "markdown",
                    "result": {"markdown": {"content": "hello world"}},
                },
            )

        with mock.patch("builtins.open", mock.mock_open(read_data=b"x")), \
                mock.patch("docstrange.processors.cloud_processor.requests.post", fake_post):
            out = result.extract_markdown()

        self.assertEqual(out, "hello world")
        self.assertEqual(captured["url"], processor.api_url)
        # Legacy field kept for backward-compat; new field added.
        self.assertEqual(captured["data"]["output_type"], "markdown")
        self.assertEqual(captured["data"]["output_format"], "markdown")


class DeprecationAwareRateLimitTests(unittest.TestCase):
    def test_deprecation_429_is_not_reported_as_quota(self):
        _, result = _make_result(api_key="k")
        deprecation = _FakeResponse(
            status_code=429,
            json_body={
                "detail": "The /extract endpoint is deprecated. "
                          "Please migrate to /api/v1/extract."
            },
        )

        with mock.patch("builtins.open", mock.mock_open(read_data=b"x")), \
                mock.patch("docstrange.processors.cloud_processor.requests.post",
                           return_value=deprecation):
            with self.assertRaises(ConversionError) as ctx:
                result.extract_markdown()

        message = str(ctx.exception)
        self.assertIn("deprecat", message.lower())
        self.assertNotIn("10k/month", message)
        self.assertNotIn("Rate limit exceeded", message)

    def test_real_quota_429_still_reported_with_key(self):
        _, result = _make_result(api_key="k")
        quota = _FakeResponse(
            status_code=429,
            json_body={"detail": "Monthly quota exceeded."},
        )

        with mock.patch("builtins.open", mock.mock_open(read_data=b"x")), \
                mock.patch("docstrange.processors.cloud_processor.requests.post",
                           return_value=quota):
            with self.assertRaises(ConversionError) as ctx:
                result.extract_markdown()

        message = str(ctx.exception)
        self.assertIn("Rate limit exceeded", message)
        self.assertIn("Monthly quota exceeded", message)

    def test_free_tier_429_without_key_reports_login_guidance(self):
        _, result = _make_result(api_key=None)
        quota = _FakeResponse(
            status_code=429,
            json_body={"detail": "Too many requests."},
        )

        with mock.patch("builtins.open", mock.mock_open(read_data=b"x")), \
                mock.patch("docstrange.processors.cloud_processor.requests.post",
                           return_value=quota):
            with self.assertRaises(ConversionError) as ctx:
                result.extract_markdown()

        self.assertIn("free tier", str(ctx.exception).lower())


class ResponseParsingTests(unittest.TestCase):
    def test_parses_new_nested_shape(self):
        processor = CloudProcessor()
        content = processor._extract_content_from_response({
            "success": True,
            "output_format": "markdown",
            "result": {"markdown": {"content": "# Title"}},
        })
        self.assertEqual(content, "# Title")

    def test_backward_compatible_flat_shape(self):
        processor = CloudProcessor()
        content = processor._extract_content_from_response({"content": "legacy"})
        self.assertEqual(content, "legacy")

    def test_prefers_requested_output_format_block(self):
        processor = CloudProcessor()
        content = processor._extract_content_from_response({
            "output_format": "html",
            "result": {
                "markdown": {"content": "md"},
                "html": {"content": "<p>html</p>"},
            },
        })
        self.assertEqual(content, "<p>html</p>")

    def test_parse_error_detail_handles_non_json(self):
        resp = _FakeResponse(status_code=500, json_body=None, text="Internal Error")
        self.assertEqual(CloudProcessor._parse_error_detail(resp), "Internal Error")

    def test_is_deprecation_notice(self):
        self.assertTrue(CloudProcessor._is_deprecation_notice(
            "The /extract endpoint is deprecated. Please migrate to /api/v1/extract."))
        self.assertFalse(CloudProcessor._is_deprecation_notice("Monthly quota exceeded."))


if __name__ == "__main__":
    unittest.main()
