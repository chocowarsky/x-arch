"""Unit tests for x_arch.identity (zero-auth registration check & base64 decoding)."""

from __future__ import annotations

import json
import httpx
import pytest

from x_arch.identity import (
    check_email_registered,
    check_username_available,
    decode_base64_user_id,
    snowflake_to_base64_user_id,
)


def test_decode_base64_user_id():
    # 'User:1306114022886973440' in base64 is 'VXNlcjoxMzA2MTE0MDIyODg2OTczNDQw'
    b64 = "VXNlcjoxMzA2MTE0MDIyODg2OTczNDQw"
    decoded = decode_base64_user_id(b64)
    assert decoded == 1306114022886973440

    # Round trip
    encoded = snowflake_to_base64_user_id(1306114022886973440)
    assert encoded == b64

    # Invalid input
    assert decode_base64_user_id("") is None
    assert decode_base64_user_id("not-base64???") is None


def test_check_email_registered_taken():
    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert "email_available.json" in str(request.url)
        return httpx.Response(
            200,
            text=json.dumps({"valid": False, "msg": "Email already in use", "taken": True}),
        )

    transport = httpx.MockTransport(mock_handler)
    client = httpx.Client(transport=transport)

    res = check_email_registered("test@example.com", client=client)
    assert res["registered"] is True
    assert res["taken"] is True
    assert res["valid"] is False
    assert res["error"] is None


def test_check_email_registered_available():
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            text=json.dumps({"valid": True, "msg": "Available!", "taken": False}),
        )

    transport = httpx.MockTransport(mock_handler)
    client = httpx.Client(transport=transport)

    res = check_email_registered("nonexistent@example.com", client=client)
    assert res["registered"] is False
    assert res["taken"] is False
    assert res["valid"] is True
    assert res["error"] is None


def test_check_email_registered_rate_limited():
    def mock_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(429, text="")

    transport = httpx.MockTransport(mock_handler)
    client = httpx.Client(transport=transport)

    res = check_email_registered("spam@example.com", client=client)
    assert "Rate limit exceeded" in str(res["error"])


def test_check_username_available():
    def mock_handler(request: httpx.Request) -> httpx.Response:
        assert "username_available.json" in str(request.url)
        return httpx.Response(
            200,
            text=json.dumps({"valid": False, "msg": "Username has already been taken"}),
        )

    transport = httpx.MockTransport(mock_handler)
    client = httpx.Client(transport=transport)

    res = check_username_available("bevanpramudt", client=client)
    assert res["username"] == "bevanpramudt"
    assert res["taken"] is True
    assert res["valid"] is False
