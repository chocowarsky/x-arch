"""Zero-auth passive identity and registration verification.

Utilizes public, unauthenticated Twitter edge endpoints to check registration status
without needing API tokens, browser session cookies, or burner credentials.

Derived from proven techniques in:
- megadose/holehe
- rawfilejson/awesome-osint-arsenal (Socialscan / Maigret)
"""

from __future__ import annotations

import base64
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

    own_client = client is None
    c = client or httpx.Client(headers=DEFAULT_HEADERS, timeout=10.0)

    try:
        resp = c.get(EMAIL_AVAILABLE_ENDPOINT, params={"email": email_clean})
        if resp.status_code == 429:
            result["error"] = "Rate limit exceeded (HTTP 429) on Twitter edge."
            result["msg"] = "Rate limited"
            return result

        if resp.status_code != 200:
            result["error"] = f"Twitter returned HTTP status {resp.status_code}."
            return result

        data = resp.json()
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

    own_client = client is None
    c = client or httpx.Client(headers=DEFAULT_HEADERS, timeout=10.0)

    try:
        resp = c.get(USERNAME_AVAILABLE_ENDPOINT, params={"username": clean_name})
        if resp.status_code == 429:
            result["error"] = "Rate limit exceeded (HTTP 429) on Twitter edge."
            result["msg"] = "Rate limited"
            return result

        if resp.status_code != 200:
            result["error"] = f"Twitter returned HTTP status {resp.status_code}."
            return result

        data = resp.json()
        valid = bool(data.get("valid", False))
        msg = str(data.get("msg", ""))
        desc = str(data.get("desc", ""))

        # On username_available: if valid is False and msg indicates taken
        # E.g. {"valid": false, "msg": "Username has already been taken"}
        taken = not valid or "taken" in msg.lower() or "taken" in desc.lower()

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
    if not b64_str:
        return None

    try:
        # Add padding if needed
        missing_padding = len(b64_str) % 4
        if missing_padding:
            b64_str += "=" * (4 - missing_padding)

        decoded = base64.b64decode(b64_str).decode("utf-8", errors="ignore")
        match = re.search(r"User:(\d+)", decoded)
        if match:
            return int(match.group(1))

        # Check if the decoded string is directly an integer
        if decoded.isdigit():
            return int(decoded)

    except Exception:
        pass

    return None


def snowflake_to_base64_user_id(snowflake_id: int) -> str:
    """Encode an integer Snowflake User ID into standard GraphQL Base64 format."""
    raw = f"User:{snowflake_id}".encode("utf-8")
    return base64.b64encode(raw).decode("utf-8")
