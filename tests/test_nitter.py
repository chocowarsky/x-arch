"""Unit tests for x_arch.nitter (timeline pagination and mirror fallback)."""

from __future__ import annotations

import httpx
import pytest

from x_arch.nitter import DEFAULT_NITTER_INSTANCES, fetch_nitter_timeline_ids


def test_fetch_nitter_timeline_single_page():
    page_html = """
    <html>
      <body>
        <div class="timeline-item">
          <a class="tweet-link" href="/bevanpramudt/status/1308986682906152960#m"></a>
          <a class="tweet-link" href="/bevanpramudt/status/1309091545048584193#m"></a>
        </div>
      </body>
    </html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=page_html)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    ids = fetch_nitter_timeline_ids(
        "bevanpramudt",
        instance="https://custom.nitter.org",
        client=client,
    )
    assert ids == {1308986682906152960, 1309091545048584193}


def test_fetch_nitter_timeline_cursor_pagination():
    page1 = """
    <html><body>
      <a href="/bevanpramudt/status/100#m"></a>
      <a href="/bevanpramudt?cursor=cursor_token_1">Load more</a>
    </body></html>
    """
    page2 = """
    <html><body>
      <a href="/bevanpramudt/status/200#m"></a>
    </body></html>
    """

    calls = []

    def handler(request: httpx.Request) -> httpx.Response:
        url_str = str(request.url)
        calls.append(url_str)
        if "cursor=" in url_str:
            return httpx.Response(200, text=page2)
        return httpx.Response(200, text=page1)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    ids = fetch_nitter_timeline_ids(
        "@bevanpramudt",
        instance="https://test.nitter",
        request_delay_seconds=0,
        client=client,
    )
    assert ids == {100, 200}
    assert len(calls) == 2
    assert "cursor=cursor_token_1" in calls[1]


def test_fetch_nitter_fallback_when_primary_instance_fails():
    # Instance 1 returns 502 Bad Gateway
    # Instance 2 returns valid HTML with tweets
    calls = []

    valid_html = """
    <html><body>
      <a href="/bevanpramudt/status/555555#m"></a>
    </body></html>
    """

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(str(request.url))
        if "dead-mirror.com" in str(request.url):
            return httpx.Response(502, text="Bad Gateway")
        return httpx.Response(200, text=valid_html)

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    ids = fetch_nitter_timeline_ids(
        "bevanpramudt",
        instances=["https://dead-mirror.com", "https://healthy-mirror.com"],
        request_delay_seconds=0,
        client=client,
    )

    assert ids == {555555}
    assert any("dead-mirror.com" in c for c in calls)
    assert any("healthy-mirror.com" in c for c in calls)


def test_fetch_nitter_all_instances_fail_returns_empty_set():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, text="Service Unavailable")

    transport = httpx.MockTransport(handler)
    client = httpx.Client(transport=transport)

    ids = fetch_nitter_timeline_ids(
        "bevanpramudt",
        instances=["https://dead1.com", "https://dead2.com"],
        client=client,
    )
    assert ids == set()


def test_fetch_nitter_empty_screen_name():
    ids = fetch_nitter_timeline_ids("")
    assert ids == set()
