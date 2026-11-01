"""Tests for x_archaeologist.wayback — mocked HTTP, no live network calls."""

from __future__ import annotations

import json

import httpx
import pytest

from x_archaeologist.wayback import (
    WaybackError,
    fetch_archived_status_ids,
    fetch_cdx_rows,
)

SAMPLE_CDX_RESPONSE = [
    ["timestamp", "original", "statuscode"],
    ["20200924042839", "https://twitter.com/bevanpramudt/status/1308986682906152960", "-"],
    ["20200924064136", "https://twitter.com/bevanpramudt/status/1308986682906152960", "200"],
    ["20200924201457", "https://twitter.com/bevanpramudt/status/1309091545048584193", "200"],
]


def _mock_transport(response_body: str, status_code: int = 200) -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status_code, text=response_body)

    return httpx.MockTransport(handler)


def test_fetch_cdx_rows_parses_valid_response():
    transport = _mock_transport(json.dumps(SAMPLE_CDX_RESPONSE))
    client = httpx.Client(transport=transport)

    rows = fetch_cdx_rows("bevanpramudt", client=client)

    assert len(rows) == 3
    assert rows[0].timestamp == "20200924042839"
    assert "1308986682906152960" in rows[0].original_url


def test_fetch_archived_status_ids_deduplicates():
    transport = _mock_transport(json.dumps(SAMPLE_CDX_RESPONSE))
    client = httpx.Client(transport=transport)

    ids = fetch_archived_status_ids("bevanpramudt", client=client)

    # Two rows share the same status ID (crawled twice) -> deduped to 2 unique IDs.
    assert ids == {1308986682906152960, 1309091545048584193}


def test_empty_cdx_response_returns_empty_set():
    transport = _mock_transport(json.dumps([["timestamp", "original", "statuscode"]]))
    client = httpx.Client(transport=transport)

    ids = fetch_archived_status_ids("some_handle_with_no_archives", client=client)

    assert ids == set()


def test_transient_outage_retries_then_succeeds():
    call_count = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        call_count["n"] += 1
        if call_count["n"] < 3:
            # Simulate archive.org's "Temporarily Offline" HTML error page.
            return httpx.Response(200, text="<html>Internet Archive: Temporarily Offline</html>")
        return httpx.Response(200, text=json.dumps(SAMPLE_CDX_RESPONSE))

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    rows = fetch_cdx_rows(
        "bevanpramudt", client=client, max_retries=5, retry_wait_seconds=0
    )

    assert call_count["n"] == 3
    assert len(rows) == 3


def test_persistent_outage_raises_wayback_error():
    transport = _mock_transport("<html>Internet Archive: Temporarily Offline</html>")
    client = httpx.Client(transport=transport)

    with pytest.raises(WaybackError):
        fetch_cdx_rows("bevanpramudt", client=client, max_retries=2, retry_wait_seconds=0)


def test_from_year_and_to_year_are_passed_as_params():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["params"] = dict(request.url.params)
        return httpx.Response(200, text=json.dumps(SAMPLE_CDX_RESPONSE))

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    fetch_cdx_rows("bevanpramudt", from_year=2019, to_year=2021, client=client)

    assert captured["params"]["from"] == "2019"
    assert captured["params"]["to"] == "2021"
