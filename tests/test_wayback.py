"""Tests for x_arch.wayback — mocked HTTP, no live network calls."""

from __future__ import annotations

import json

import httpx
import pytest

from x_arch.wayback import (
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

    # 3 attempts for twitter.com (2 transient errors + 1 success) + 1 attempt for x.com
    assert call_count["n"] == 4
    assert len(rows) == 3


def test_fetch_cdx_rows_searches_both_twitter_and_x_domains():
    queried_urls: list[str] = []

    sample_x_response = [
        ["timestamp", "original", "statuscode"],
        ["20230924120000", "https://x.com/bevanpramudt/status/1700000000000000000", "200"],
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        url_param = request.url.params.get("url", "")
        queried_urls.append(url_param)
        if "twitter.com" in url_param:
            return httpx.Response(200, text=json.dumps(SAMPLE_CDX_RESPONSE))
        else:
            return httpx.Response(200, text=json.dumps(sample_x_response))

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    rows = fetch_cdx_rows("@bevanpramudt", client=client)

    # Should query both twitter.com and x.com without @ prefix
    assert "twitter.com/bevanpramudt/status/*" in queried_urls
    assert "x.com/bevanpramudt/status/*" in queried_urls
    # 3 from twitter.com + 1 from x.com = 4 total snapshots
    assert len(rows) == 4
    assert any("x.com/bevanpramudt/status/1700000000000000000" in r.original_url for r in rows)


def test_fetch_archived_status_ids_merges_twitter_and_x_ids():
    sample_x_response = [
        ["timestamp", "original", "statuscode"],
        ["20230924120000", "https://x.com/bevanpramudt/status/1700000000000000000", "200"],
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        url_param = request.url.params.get("url", "")
        if "twitter.com" in url_param:
            return httpx.Response(200, text=json.dumps(SAMPLE_CDX_RESPONSE))
        return httpx.Response(200, text=json.dumps(sample_x_response))

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    ids = fetch_archived_status_ids("bevanpramudt", client=client)
    assert 1308986682906152960 in ids
    assert 1309091545048584193 in ids
    assert 1700000000000000000 in ids
    assert len(ids) == 3


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
