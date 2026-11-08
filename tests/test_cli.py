"""Tests for x_arch.cli — end-to-end with mocked HTTP."""

from __future__ import annotations

import json

import httpx
import pytest

from x_arch import cli

SAMPLE_CDX_RESPONSE = [
    ["timestamp", "original", "statuscode"],
    ["20200924064136", "https://twitter.com/bevanpramudt/status/1308986682906152960", "200"],
]


@pytest.fixture(autouse=True)
def _patch_httpx_client(monkeypatch):
    """Route every httpx.Client() created inside the CLI through a mock
    transport, so tests never touch the network."""

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, text=json.dumps(SAMPLE_CDX_RESPONSE))

    original_client = httpx.Client

    def patched_client(*args, **kwargs):
        kwargs.setdefault("transport", httpx.MockTransport(handler))
        return original_client(*args, **kwargs)

    monkeypatch.setattr(httpx, "Client", patched_client)


def test_cli_human_readable_output(capsys):
    exit_code = cli.run(["bevanpramudt"])

    captured = capsys.readouterr()
    assert exit_code == 0
    assert "@bevanpramudt" in captured.out
    assert "1308986682906152960" in captured.out
    assert "2020-09-24" in captured.out  # decoded UTC date for this ID


def test_cli_json_output_is_valid_json(capsys):
    exit_code = cli.run(["bevanpramudt", "--json"])

    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["screen_name"] == "bevanpramudt"
    assert payload["earliest_id"] == 1308986682906152960
    assert payload["sources_used"] == ["wayback_machine"]


def test_cli_passes_year_filters_through(monkeypatch):
    captured_kwargs = {}

    def fake_fetch(screen_name, **kwargs):
        captured_kwargs.update(kwargs)
        return {1308986682906152960}

    monkeypatch.setattr(cli, "fetch_archived_status_ids", fake_fetch)

    cli.run(["bevanpramudt", "--from-year", "2019", "--to-year", "2021"])

    assert captured_kwargs["from_year"] == 2019
    assert captured_kwargs["to_year"] == 2021


def test_cli_profile_flag(capsys):
    exit_code = cli.run(["bevanpramudt", "--profile"])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "Offline Behavioral & Circadian Profile" in captured.out
    assert "Estimated Timezone" in captured.out


def test_cli_resolve_media(capsys):
    url = "https://pbs.twimg.com/media/F9abcdef?format=jpg&name=small"
    exit_code = cli.run(["--resolve-media", url])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "name=orig" in captured.out


def test_cli_clean_url(capsys):
    url = "https://x.com/user/status/123?s=20&t=abc"
    exit_code = cli.run(["--clean-url", url])
    captured = capsys.readouterr()
    assert exit_code == 0
    assert "s=" not in captured.out
    assert "t=" not in captured.out


def test_cli_handles_at_prefix(capsys):
    exit_code = cli.run(["@bevanpramudt", "--json"])
    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert payload["screen_name"] == "bevanpramudt"


def test_cli_resolve_media_json_payload(capsys):
    payload = {
        "extended_entities": {
            "media": [
                {
                    "id_str": "123",
                    "type": "photo",
                    "media_url_https": "https://pbs.twimg.com/media/pic.jpg:large",
                }
            ]
        }
    }
    exit_code = cli.run(["--resolve-media", json.dumps(payload), "--json"])
    captured = capsys.readouterr()
    assert exit_code == 0
    res = json.loads(captured.out)
    assert len(res) == 1
    assert res[0]["url"] == "https://pbs.twimg.com/media/pic.jpg:orig"


def test_cli_with_nitter_flag(monkeypatch, capsys):
    monkeypatch.setattr(cli, "fetch_nitter_timeline_ids", lambda *a, **kw: {999999999})
    exit_code = cli.run(["bevanpramudt", "--with-nitter", "--json"])
    captured = capsys.readouterr()
    assert exit_code == 0
    payload = json.loads(captured.out)
    assert any("nitter" in s for s in payload["sources_used"])
