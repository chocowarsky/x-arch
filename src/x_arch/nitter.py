"""Optional, best-effort live Nitter timeline pagination.

This is a SECONDARY/SUPPLEMENTARY source, not a reliable one on its own.
Public Nitter instances rate-limit aggressively and their cursor-based
pagination reliably stalls after a few dozen pages when walking deep into an
account's history — confirmed empirically (it plateaus and starts re-serving
the same first page instead of erroring). Never treat a Nitter-only result as
the true earliest tweet; it only tells you "there is activity at least this
old," which is still useful as a sanity check against X's own search index.

Always treat :mod:`x_archaeologist.wayback` as the primary, authoritative
source. This module exists to add corroborating IDs when available, nothing
more.
"""

from __future__ import annotations

import html
import re
import time

import httpx

DEFAULT_USER_AGENT = "Mozilla/5.0 (x-archaeologist/0.1)"


def fetch_nitter_timeline_ids(
    screen_name: str,
    *,
    instance: str = "https://nitter.net",
    max_pages: int = 50,
    stall_limit: int = 5,
    request_delay_seconds: float = 2.0,
    timeout: float = 25.0,
    client: httpx.Client | None = None,
) -> set[int]:
    """Best-effort scroll of a Nitter instance's timeline for ``screen_name``.

    Args:
        screen_name: The X handle, without ``@``.
        instance: Base URL of a Nitter instance. Public instances come and
            go; pass your own self-hosted instance for reliability.
        max_pages: Hard cap on pagination requests.
        stall_limit: Stop early if this many consecutive pages add zero new
            IDs (the known pagination-stall failure mode).
        request_delay_seconds: Delay between requests, to be a polite client.
        timeout: Per-request timeout in seconds.
        client: Optional pre-configured ``httpx.Client`` (for tests).

    Returns:
        A set of unique status IDs found. May be empty or incomplete — this
        is expected behavior, not an error, given known Nitter limitations.
    """
    owns_client = client is None
    http_client = client or httpx.Client(
        timeout=timeout, headers={"User-Agent": DEFAULT_USER_AGENT}, follow_redirects=True
    )

    found_ids: set[int] = set()
    url = f"{instance}/{screen_name}"
    stall_count = 0

    try:
        for _ in range(max_pages):
            try:
                response = http_client.get(url)
                response.raise_for_status()
            except httpx.HTTPError:
                break

            page_html = response.text
            page_ids = {
                int(m) for m in re.findall(rf"/{screen_name}/status/(\d+)", page_html)
            }
            before = len(found_ids)
            found_ids |= page_ids
            new_count = len(found_ids) - before

            stall_count = stall_count + 1 if new_count == 0 else 0
            if stall_count >= stall_limit:
                break

            cursor_match = re.search(
                rf'href="(/{screen_name}\?cursor=[^"]+)"', page_html
            )
            if not cursor_match:
                break
            next_url = instance + html.unescape(cursor_match.group(1))
            if next_url == url:
                break
            url = next_url
            time.sleep(request_delay_seconds)
    finally:
        if owns_client:
            http_client.close()

    return found_ids
