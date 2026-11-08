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
DEFAULT_DOMAINS: tuple[str, ...] = ("twitter.com", "x.com")
DEFAULT_USER_AGENT = "x-arch/0.2.0 (+https://github.com/chocowarsky/x-arch)"


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


def _fetch_domain_cdx_rows(
    http_client: httpx.Client,
    domain: str,
    screen_name: str,
    *,
    from_year: int | None = None,
    to_year: int | None = None,
    max_retries: int = 6,
    retry_wait_seconds: float = 8.0,
) -> list[ArchivedSnapshot]:
    """Fetch CDX rows for a single domain (e.g. twitter.com or x.com)."""
    params: dict[str, str] = {
        "url": f"{domain}/{screen_name}/status/*",
        "output": "json",
        "fl": "timestamp,original,statuscode",
    }
    if from_year:
        params["from"] = str(from_year)
    if to_year:
        params["to"] = str(to_year)

    last_error: Exception | None = None
    data: list[list[str]] | None = None

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
            f"{max_retries} attempts for '{screen_name}' on {domain}. "
            f"The archive is likely experiencing an outage — retry later. "
            f"Last error: {last_error}"
        )

    if not isinstance(data, list) or len(data) == 0:
        return []

    if data[0] != ["timestamp", "original", "statuscode"]:
        return []

    snapshots: list[ArchivedSnapshot] = []
    for row in data[1:]:
        if not isinstance(row, list) or len(row) < 3:
            continue
        ts = str(row[0]) if row[0] is not None else ""
        url = str(row[1]) if row[1] is not None else ""
        status = str(row[2]) if row[2] is not None else ""
        snapshots.append(ArchivedSnapshot(timestamp=ts, original_url=url, status_code=status))
    return snapshots


def fetch_cdx_rows(
    screen_name: str,
    *,
    from_year: int | None = None,
    to_year: int | None = None,
    timeout: float = 30.0,
    max_retries: int = 6,
    retry_wait_seconds: float = 8.0,
    domains: tuple[str, ...] = DEFAULT_DOMAINS,
    client: httpx.Client | None = None,
) -> list[ArchivedSnapshot]:
    """Fetch every archived `/status/<id>` snapshot the Wayback Machine has
    for a given account across both legacy (twitter.com) and post-rebrand (x.com) domains.

    Args:
        screen_name: The X handle, with or without ``@``.
        from_year: Optional lower bound (inclusive) on crawl year.
        to_year: Optional upper bound (inclusive) on crawl year.
        timeout: Per-request timeout in seconds.
        max_retries: How many times to retry on transient
            "Temporarily Offline" responses before giving up per domain.
        retry_wait_seconds: Delay between retries.
        domains: Domains to query for status URLs (default: twitter.com and x.com).
        client: Optional pre-configured ``httpx.Client`` (for tests).

    Returns:
        A list of :class:`ArchivedSnapshot`, one per crawl event, sorted
        chronologically ascending. Deduplicated by (timestamp, original_url).

    Raises:
        WaybackError: If the CDX API fails on all requested domains.
    """
    clean_name = screen_name.lstrip("@").strip()
    if not clean_name:
        return []

    owns_client = client is None
    http_client = client or httpx.Client(
        timeout=timeout, headers={"User-Agent": DEFAULT_USER_AGENT}
    )

    all_snapshots: list[ArchivedSnapshot] = []
    errors: list[Exception] = []

    try:
        for domain in domains:
            try:
                snapshots = _fetch_domain_cdx_rows(
                    http_client,
                    domain,
                    clean_name,
                    from_year=from_year,
                    to_year=to_year,
                    max_retries=max_retries,
                    retry_wait_seconds=retry_wait_seconds,
                )
                all_snapshots.extend(snapshots)
            except WaybackError as exc:
                errors.append(exc)

        if errors and len(errors) == len(domains):
            raise WaybackError(
                f"Wayback CDX API failed across all domains for '{clean_name}'. "
                f"Errors: {'; '.join(str(e) for e in errors)}"
            )
    finally:
        if owns_client:
            http_client.close()

    # Deduplicate snapshots across crawls & domains
    seen: set[tuple[str, str]] = set()
    deduped: list[ArchivedSnapshot] = []
    for snapshot in all_snapshots:
        key = (snapshot.timestamp, snapshot.original_url)
        if key not in seen:
            seen.add(key)
            deduped.append(snapshot)

    # Sort chronologically by timestamp
    deduped.sort(key=lambda s: s.timestamp)
    return deduped


def fetch_archived_status_ids(
    screen_name: str,
    *,
    from_year: int | None = None,
    to_year: int | None = None,
    domains: tuple[str, ...] = DEFAULT_DOMAINS,
    **kwargs,
) -> set[int]:
    """Convenience wrapper: return the set of unique numeric status IDs the
    Wayback Machine has ever archived for this account.

    See :func:`fetch_cdx_rows` for parameters.
    """
    clean_name = screen_name.lstrip("@").strip()
    if not clean_name:
        return set()
    rows = fetch_cdx_rows(
        clean_name,
        from_year=from_year,
        to_year=to_year,
        domains=domains,
        **kwargs,
    )
    ids: set[int] = set()
    for row in rows:
        status_id = _extract_status_id(row.original_url)
        if status_id is not None:
            ids.add(status_id)
    return ids
