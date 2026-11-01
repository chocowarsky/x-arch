"""Query the Wayback Machine CDX API for archived X/Twitter status URLs.

This is the module that does the actual "digging." It never touches X.com
directly (so it is immune to Cloudflare challenges, API paywalls, and the
search-index gaps documented in the README) — it only talks to
web.archive.org, a free, independent, read-only archive.

The Internet Archive's CDX server is occasionally "Temporarily Offline" for
short windows; all requests here retry with backoff to ride that out.
"""

from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass

import httpx

CDX_ENDPOINT = "https://web.archive.org/cdx/search/cdx"
DEFAULT_USER_AGENT = "x-archaeologist/0.1 (+https://github.com/)"


class WaybackError(RuntimeError):
    """Raised when the Wayback Machine CDX API cannot be reached or parsed."""


@dataclass(frozen=True)
class ArchivedSnapshot:
    """One CDX row: a single crawl of a single URL at a single point in time."""

    timestamp: str  # e.g. "20200924064136" (YYYYMMDDHHMMSS, UTC)
    original_url: str
    status_code: str


def _extract_status_id(url: str) -> int | None:
    """Pull the numeric tweet ID out of a `/status/<id>` URL, or None."""
    match = re.search(r"/status/(\d+)", url)
    return int(match.group(1)) if match else None


def fetch_cdx_rows(
    screen_name: str,
    *,
    from_year: int | None = None,
    to_year: int | None = None,
    timeout: float = 30.0,
    max_retries: int = 6,
    retry_wait_seconds: float = 8.0,
    client: httpx.Client | None = None,
) -> list[ArchivedSnapshot]:
    """Fetch every archived `/status/<id>` snapshot the Wayback Machine has
    for a given account.

    Args:
        screen_name: The X handle, without ``@``.
        from_year: Optional lower bound (inclusive) on crawl year.
        to_year: Optional upper bound (inclusive) on crawl year.
        timeout: Per-request timeout in seconds.
        max_retries: How many times to retry on transient
            "Temporarily Offline" responses before giving up.
        retry_wait_seconds: Delay between retries.
        client: Optional pre-configured ``httpx.Client`` (for tests).

    Returns:
        A list of :class:`ArchivedSnapshot`, one per crawl event. The same
        tweet is typically crawled multiple times; callers that only need
        unique tweet IDs should deduplicate (see :func:`fetch_archived_status_ids`).

    Raises:
        WaybackError: If the CDX API never returns valid JSON within
            ``max_retries`` attempts.
    """
    params = {
        "url": f"twitter.com/{screen_name}/status/*",
        "output": "json",
        "fl": "timestamp,original,statuscode",
    }
    if from_year:
        params["from"] = str(from_year)
    if to_year:
        params["to"] = str(to_year)

    owns_client = client is None
    http_client = client or httpx.Client(
        timeout=timeout, headers={"User-Agent": DEFAULT_USER_AGENT}
    )

    try:
        last_error: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                response = http_client.get(CDX_ENDPOINT, params=params)
                response.raise_for_status()
                data = json.loads(response.text)
                break
            except (httpx.HTTPError, json.JSONDecodeError) as exc:
                last_error = exc
                if attempt < max_retries:
                    time.sleep(retry_wait_seconds)
                continue
        else:
            raise WaybackError(
                f"Wayback CDX API did not return valid data after "
                f"{max_retries} attempts for '{screen_name}'. The archive is "
                f"likely experiencing an outage — retry later. Last error: "
                f"{last_error}"
            )
    finally:
        if owns_client:
            http_client.close()

    if not data or data[0] != ["timestamp", "original", "statuscode"]:
        return []

    return [
        ArchivedSnapshot(timestamp=row[0], original_url=row[1], status_code=row[2])
        for row in data[1:]
    ]


def fetch_archived_status_ids(
    screen_name: str,
    *,
    from_year: int | None = None,
    to_year: int | None = None,
    **kwargs,
) -> set[int]:
    """Convenience wrapper: return the set of unique numeric status IDs the
    Wayback Machine has ever archived for this account.

    See :func:`fetch_cdx_rows` for parameters.
    """
    rows = fetch_cdx_rows(screen_name, from_year=from_year, to_year=to_year, **kwargs)
    ids: set[int] = set()
    for row in rows:
        status_id = _extract_status_id(row.original_url)
        if status_id is not None:
            ids.add(status_id)
    return ids
