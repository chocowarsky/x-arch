"""Optional, best-effort live Nitter timeline pagination with automatic mirror fallback.

This is a SECONDARY/SUPPLEMENTARY source, not a reliable one on its own.
Public Nitter instances rate-limit aggressively and their cursor-based
pagination reliably stalls after a few dozen pages when walking deep into an
account's history — confirmed empirically (it plateaus and starts re-serving
the same first page instead of erroring). Never treat a Nitter-only result as
the true earliest tweet; it only tells you "there is activity at least this
old," which is still useful as a sanity check against X's own search index.

Always treat :mod:`x_arch.wayback` as the primary, authoritative
source. This module exists to add corroborating IDs when available, nothing
more.
"""

from __future__ import annotations

import html
import re
import time
from typing import Sequence

import httpx

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 (x-arch/0.2.0)"
)

DEFAULT_NITTER_INSTANCES: list[str] = [
    "https://xcancel.com",
    "https://nitter.poast.org",
    "https://nitter.privacydev.net",
]


def fetch_nitter_timeline_ids(
    screen_name: str,
    *,
    instance: str | None = None,
    instances: Sequence[str] | None = None,
    max_pages: int = 50,
    stall_limit: int = 5,
    request_delay_seconds: float = 2.0,
    timeout: float = 10.0,
    client: httpx.Client | None = None,
) -> set[int]:
    """Best-effort scroll of Nitter instance(s) timeline for ``screen_name``.

    Args:
        screen_name: The X handle, with or without ``@``.
        instance: Base URL of a single Nitter instance. If provided and dead,
            the function gracefully falls back to healthy community instances.
        instances: Ordered sequence of Nitter instances to attempt.
        max_pages: Hard cap on pagination requests per instance.
        stall_limit: Stop early if this many consecutive pages add zero new
            IDs (the known pagination-stall failure mode).
        request_delay_seconds: Delay between requests, to be a polite client.
        timeout: Per-request timeout in seconds (connect timeout is capped at 5s
            to fail fast on dead mirrors).
        client: Optional pre-configured ``httpx.Client`` (for tests).

    Returns:
        A set of unique status IDs found. May be empty or incomplete — this
        is expected behavior, not an error, given known Nitter limitations.
    """
    clean_name = screen_name.lstrip("@").strip()
    if not clean_name:
        return set()

    # Determine candidate instances in priority order
    candidate_list: list[str] = []
    if instances is not None:
        candidate_list.extend(i.rstrip("/") for i in instances if i)
    elif instance is not None:
        cleaned_inst = instance.rstrip("/")
        candidate_list.append(cleaned_inst)
        for fallback in DEFAULT_NITTER_INSTANCES:
            fb_clean = fallback.rstrip("/")
            if fb_clean != cleaned_inst and fb_clean not in candidate_list:
                candidate_list.append(fb_clean)
    else:
        candidate_list.extend(i.rstrip("/") for i in DEFAULT_NITTER_INSTANCES)

    owns_client = client is None
    httpx_timeout = httpx.Timeout(timeout, connect=min(timeout, 5.0))
    http_client = client or httpx.Client(
        timeout=httpx_timeout,
        headers={"User-Agent": DEFAULT_USER_AGENT},
        follow_redirects=True,
    )

    found_ids: set[int] = set()

    try:
        for current_instance in candidate_list:
            url = f"{current_instance}/{clean_name}"
            stall_count = 0
            instance_recovered_ids = False

            for _ in range(max_pages):
                try:
                    response = http_client.get(url)
                    response.raise_for_status()
                except httpx.HTTPError:
                    # Instance failed (unreachable, 502/503, 404, etc.) -> try next fallback
                    break

                page_html = response.text
                escaped_name = re.escape(clean_name)
                page_ids = {
                    int(m)
                    for m in re.findall(
                        rf"/{escaped_name}/status/(\d+)", page_html, re.IGNORECASE
                    )
                }
                before = len(found_ids)
                found_ids |= page_ids
                new_count = len(found_ids) - before
                if page_ids:
                    instance_recovered_ids = True

                stall_count = stall_count + 1 if new_count == 0 else 0
                if stall_count >= stall_limit:
                    break

                # Extract pagination cursor href
                cursor_match = re.search(
                    rf'href="(/(?:{escaped_name})?\?cursor=[^"]+)"',
                    page_html,
                    re.IGNORECASE,
                )
                if not cursor_match:
                    cursor_match = re.search(
                        rf'href="({re.escape(current_instance)}/{escaped_name}\?cursor=[^"]+)"',
                        page_html,
                        re.IGNORECASE,
                    )
                if not cursor_match:
                    break

                cursor_href = html.unescape(cursor_match.group(1))
                if cursor_href.startswith("http://") or cursor_href.startswith("https://"):
                    next_url = cursor_href
                elif cursor_href.startswith("/"):
                    next_url = current_instance + cursor_href
                else:
                    next_url = f"{current_instance}/{cursor_href}"

                if next_url == url:
                    break
                url = next_url
                if request_delay_seconds > 0:
                    time.sleep(request_delay_seconds)

            if instance_recovered_ids:
                break
    finally:
        if owns_client:
            http_client.close()

    return found_ids
