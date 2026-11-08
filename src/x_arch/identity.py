"""Zero-auth passive identity and registration verification.

Utilizes public, unauthenticated Twitter edge endpoints to check registration status
without needing API tokens, browser session cookies, or burner credentials.

Derived from proven techniques in:
- megadose/holehe
- rawfilejson/awesome-osint-arsenal (Socialscan / Maigret)
"""

from __future__ import annotations

import base64
import binascii
import json
import re
from typing import Any

import httpx

from .snowflake import snowflake_to_datetime

EMAIL_AVAILABLE_ENDPOINT = "https://api.twitter.com/i/users/email_available.json"
USERNAME_AVAILABLE_ENDPOINT = "https://api.twitter.com/i/users/username_available.json"

DEFAULT_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json",
}


def _detect_edge_block(resp: httpx.Response) -> str | None:
    """Detect if response is a Cloudflare/WAF block, bot challenge, or unexpected HTML page."""
    content_type = resp.headers.get("content-type", "").lower()
    text_sample = resp.text[:1200].lower()

    # Cloudflare challenge indicators: specific challenge markers or error status with cf-ray
    has_cf_challenge = (
        "just a moment" in text_sample
        or "challenge-platform" in text_sample
        or "turnstile" in text_sample
        or "attention required! | cloudflare" in text_sample
        or ("cloudflare" in text_sample and resp.status_code in (403, 429, 503))
        or ("cf-ray" in resp.headers and resp.status_code in (403, 429))
    )
    if has_cf_challenge:
        return (
            f"Cloudflare / Bot protection challenge encountered on Twitter edge (HTTP {resp.status_code})."
        )

    is_html = (
        "text/html" in content_type
        or text_sample.strip().startswith(("<!doctype html", "<html", "<head", "<body"))
    )
    if is_html:
        return f"Unexpected HTML response from Twitter edge (HTTP {resp.status_code})."

    return None


def check_email_registered(
    email: str, client: httpx.Client | None = None
) -> dict[str, Any]:
    """Check if an email address is registered on X/Twitter using zero-auth registration API.

    Returns dict with keys:
        email: str
        registered: bool (True if taken)
        taken: bool
        valid: bool
        msg: str
        error: str | None
    """
    email_clean = email.strip()
    result: dict[str, Any] = {
        "email": email_clean,
        "registered": False,
        "taken": False,
        "valid": True,
        "msg": "",
        "error": None,
    }

    if not email_clean or "@" not in email_clean or "." not in email_clean.split("@")[-1]:
        result["valid"] = False
        result["error"] = "Invalid email address format."
        return result

    own_client = client is None
    c = client or httpx.Client(headers=DEFAULT_HEADERS, timeout=10.0)

    try:
        resp = c.get(EMAIL_AVAILABLE_ENDPOINT, params={"email": email_clean})
        if resp.status_code == 429:
            result["error"] = "Rate limit exceeded (HTTP 429) on Twitter edge."
            result["msg"] = "Rate limited"
            return result

        block_err = _detect_edge_block(resp)
        if block_err:
            result["error"] = block_err
            return result

        if resp.status_code != 200:
            result["error"] = f"Twitter returned HTTP status {resp.status_code}."
            return result

        try:
            data = resp.json()
        except (json.JSONDecodeError, ValueError) as exc:
            result["error"] = f"Failed to parse response: non-JSON payload from Twitter edge ({exc})"
            return result

        if not isinstance(data, dict):
            result["error"] = "Unexpected response structure from Twitter edge."
            return result

        if "errors" in data or "error" in data:
            if "errors" in data and isinstance(data["errors"], list) and data["errors"]:
                err_msg = data["errors"][0].get("message", "Unknown API error")
            else:
                err_msg = str(data.get("error", "Unknown API error"))
            result["error"] = f"Twitter API error: {err_msg}"
            return result

        taken = bool(data.get("taken", False))
        valid = bool(data.get("valid", True))
        msg = str(data.get("msg", ""))

        result["taken"] = taken
        result["registered"] = taken
        result["valid"] = valid
        result["msg"] = msg

    except httpx.RequestError as exc:
        result["error"] = f"Network error contacting Twitter: {exc}"
    except Exception as exc:
        result["error"] = f"Failed to parse response: {exc}"
    finally:
        if own_client:
            c.close()

    return result


def check_username_available(
    username: str, client: httpx.Client | None = None
) -> dict[str, Any]:
    """Check if a username/handle is currently registered on X/Twitter.

    Returns dict with keys:
        username: str
        taken: bool
        valid: bool
        msg: str
        error: str | None
    """
    clean_name = username.lstrip("@").strip()
    result: dict[str, Any] = {
        "username": clean_name,
        "taken": False,
        "valid": True,
        "msg": "",
        "error": None,
    }

    if not clean_name:
        result["valid"] = False
        result["error"] = "Username cannot be empty."
        return result

    own_client = client is None
    c = client or httpx.Client(headers=DEFAULT_HEADERS, timeout=10.0)

    try:
        resp = c.get(USERNAME_AVAILABLE_ENDPOINT, params={"username": clean_name})
        if resp.status_code == 429:
            result["error"] = "Rate limit exceeded (HTTP 429) on Twitter edge."
            result["msg"] = "Rate limited"
            return result

        block_err = _detect_edge_block(resp)
        if block_err:
            result["error"] = block_err
            return result

        if resp.status_code != 200:
            result["error"] = f"Twitter returned HTTP status {resp.status_code}."
            return result

        try:
            data = resp.json()
        except (json.JSONDecodeError, ValueError) as exc:
            result["error"] = f"Failed to parse response: non-JSON payload from Twitter edge ({exc})"
            return result

        if not isinstance(data, dict):
            result["error"] = "Unexpected response structure from Twitter edge."
            return result

        if "errors" in data or "error" in data:
            if "errors" in data and isinstance(data["errors"], list) and data["errors"]:
                err_msg = data["errors"][0].get("message", "Unknown API error")
            else:
                err_msg = str(data.get("error", "Unknown API error"))
            result["error"] = f"Twitter API error: {err_msg}"
            return result

        valid = bool(data.get("valid", False))
        msg = str(data.get("msg", ""))
        desc = str(data.get("desc", ""))

        msg_lower = (msg + " " + desc).lower()
        taken = not valid and (
            "taken" in msg_lower
            or "already" in msg_lower
            or "in use" in msg_lower
            or bool(data.get("taken", False))
        )

        result["taken"] = taken
        result["valid"] = valid
        result["msg"] = msg or desc

    except httpx.RequestError as exc:
        result["error"] = f"Network error contacting Twitter: {exc}"
    except Exception as exc:
        result["error"] = f"Failed to parse response: {exc}"
    finally:
        if own_client:
            c.close()

    return result


def decode_base64_user_id(b64_str: str) -> int | None:
    """Decode a Base64-encoded User ID (used in GraphQL / Maigret).

    Example:
        'VXNlcjoxMzA2MTE0MDIyODg2OTczNDQw' -> 'User:1306114022886973440' -> 1306114022886973440
    """
    if not b64_str or not isinstance(b64_str, str):
        return None

    try:
        # Add padding if needed
        missing_padding = len(b64_str) % 4
        if missing_padding:
            b64_str += "=" * (4 - missing_padding)

        decoded = base64.b64decode(b64_str, validate=False).decode("utf-8", errors="ignore")
        match = re.search(r"User:(\d+)", decoded)
        if match:
            return int(match.group(1))

        # Check if the decoded string is directly an integer
        if decoded.isdigit():
            return int(decoded)

    except (ValueError, binascii.Error, UnicodeDecodeError):
        pass

    return None


def snowflake_to_base64_user_id(snowflake_id: int) -> str:
    """Encode an integer Snowflake User ID into standard GraphQL Base64 format."""
    raw = f"User:{snowflake_id}".encode("utf-8")
    return base64.b64encode(raw).decode("utf-8")
