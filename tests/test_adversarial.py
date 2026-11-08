"""Adversarial stress-test suite for x-arch.

Tests pathological inputs, boundary conditions, malicious payloads,
and error handling across all core modules.
"""

from __future__ import annotations

import datetime as dt
import json
import pytest
import httpx

from x_arch.snowflake import (
    TWITTER_EPOCH_MS,
    snowflake_to_datetime,
    sort_ids_chronologically,
)
from x_arch.wayback import (
    ArchivedSnapshot,
    WaybackError,
    fetch_cdx_rows,
    fetch_archived_status_ids,
)
from x_arch.profiler import (
    detect_quiescent_trough,
    estimate_timezone_from_trough,
    detect_dormancy_periods,
    profile_activity,
)
from x_arch.media import (
    resolve_orig_image_url,
    resolve_avatar_orig,
    resolve_banner_orig,
    select_highest_bitrate_video,
    extract_media_from_status,
)
from x_arch.identity import (
    check_email_registered,
    check_username_available,
    decode_base64_user_id,
)
from x_arch.nitter import fetch_nitter_timeline_ids
from x_arch.cli import run


# ==============================================================================
# 1. SNOWFLAKE ID EDGE CASES
# ==============================================================================

class TestSnowflakeEdgeCases:
    def test_snowflake_rejects_none(self):
        with pytest.raises((ValueError, TypeError)):
            snowflake_to_datetime(None)

    def test_snowflake_rejects_empty_and_whitespace(self):
        for bad in ("", "   ", "\t\n"):
            with pytest.raises(ValueError):
                snowflake_to_datetime(bad)

    def test_snowflake_rejects_scientific_notation(self):
        with pytest.raises(ValueError):
            snowflake_to_datetime("1e18")

    def test_snowflake_rejects_boolean(self):
        # In Python, bool is a subclass of int (True == 1, False == 0)
        # Snowflake IDs should strictly reject bool values
        with pytest.raises((ValueError, TypeError)):
            snowflake_to_datetime(True)
        with pytest.raises((ValueError, TypeError)):
            snowflake_to_datetime(False)

    def test_snowflake_handles_extreme_overflow(self):
        # Extremely large integers should raise ValueError instead of unhandled OverflowError
        with pytest.raises(ValueError):
            snowflake_to_datetime(1 << 128)

    def test_snowflake_negative_id(self):
        with pytest.raises(ValueError):
            snowflake_to_datetime(-100)

    def test_sort_ids_chronologically_invalid_and_negative(self):
        # Duplicate removal and monotonic ordering
        assert sort_ids_chronologically([200, 100, 200, 300, 100]) == [100, 200, 300]


# ==============================================================================
# 2. WAYBACK CDX EDGE CASES
# ==============================================================================

class TestWaybackCDXEdgeCases:
    def test_empty_or_whitespace_screen_name_does_not_hang(self):
        # Empty screen name or single '@' must return empty set without issuing unbounded wildcard CDX query
        for empty_name in ("", "@", "   ", "@@@"):
            res = fetch_cdx_rows(empty_name)
            assert res == []
            ids = fetch_archived_status_ids(empty_name)
            assert ids == set()

    def test_cdx_json_dict_error_response_does_not_crash(self):
        # When CDX returns a JSON dictionary (e.g. rate limit / outage error)
        def mock_dict_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json={"message": "Your request was rate limited"})

        client = httpx.Client(transport=httpx.MockTransport(mock_dict_handler))
        res = fetch_cdx_rows("validuser", client=client, max_retries=1)
        assert res == []

    def test_cdx_corrupted_rows_handled_gracefully(self):
        # Truncated row with only 2 fields instead of 3
        corrupted_data = [
            ["timestamp", "original", "statuscode"],
            ["20200101000000", "https://twitter.com/test/status/123"],  # missing statuscode
            None,  # non-list row
            ["20200102000000", "https://twitter.com/test/status/456", "200"],  # valid row
        ]

        def mock_corrupt_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(200, json=corrupted_data)

        client = httpx.Client(transport=httpx.MockTransport(mock_corrupt_handler))
        res = fetch_cdx_rows("testuser", client=client, max_retries=1)
        assert len(res) == 1
        assert res[0].original_url == "https://twitter.com/test/status/456"

    def test_wayback_domain_fallback_when_first_domain_fails(self):
        # When twitter.com fails with a WaybackError, it should still try x.com
        def mock_fallback_handler(request: httpx.Request) -> httpx.Response:
            if "twitter.com" in str(request.url):
                return httpx.Response(503, text="Service Unavailable")
            return httpx.Response(
                200,
                json=[
                    ["timestamp", "original", "statuscode"],
                    ["20231010000000", "https://x.com/target/status/1711516171819202122", "200"],
                ],
            )

        client = httpx.Client(transport=httpx.MockTransport(mock_fallback_handler))
        res = fetch_cdx_rows(
            "target",
            client=client,
            max_retries=1,
            retry_wait_seconds=0.01,
            domains=("twitter.com", "x.com"),
        )
        assert len(res) == 1
        assert "1711516171819202122" in res[0].original_url


# ==============================================================================
# 3. PROFILER EDGE CASES
# ==============================================================================

class TestProfilerEdgeCases:
    def test_profiler_24_7_bot_uniform_distribution_not_falsely_cet(self):
        # An automated bot active every hour evenly has 25% activity in any 6h window
        hourly = {h: 20 for h in range(24)}
        start, end, pct = detect_quiescent_trough(hourly, window_hours=6)
        assert pct == 25.0
        offset, label = estimate_timezone_from_trough(start, window_hours=6, quiescent_pct=pct)
        assert "Uniform" in label or "Bot" in label or "Undetermined" in label or "24/7" in label

    def test_profiler_single_tweet(self):
        # Single tweet should produce a valid profile without division by zero
        single_id = [1308986682906152960]
        prof = profile_activity(single_id)
        assert prof.total_statuses == 1
        assert prof.timespan_days == 0
        assert prof.dormancy_periods == []

    def test_profiler_all_tweets_same_hour(self):
        # 10 tweets all in the exact same hour
        # status IDs corresponding to same hour
        base_id = 1308986682906152960
        ids = [base_id + i for i in range(10)]
        prof = profile_activity(ids)
        assert prof.total_statuses == 10
        assert sum(prof.hourly_utc.values()) == 10

    def test_profiler_sparse_hourly_dict(self):
        # detect_quiescent_trough shouldn't crash on sparse dict
        sparse = {0: 5, 12: 10}
        start, end, pct = detect_quiescent_trough(sparse, window_hours=6)
        assert 0 <= start < 24
        assert 0 <= end < 24

    def test_profiler_dormancy_threshold_validation(self):
        # Non-positive dormancy threshold should be handled safely
        ids = [1308986682906152960, 1308986682906152961]
        with pytest.raises(ValueError):
            detect_dormancy_periods(ids, threshold_days=0)
        with pytest.raises(ValueError):
            detect_dormancy_periods(ids, threshold_days=-5)


# ==============================================================================
# 4. MEDIA URL PARSING EDGE CASES
# ==============================================================================

class TestMediaEdgeCases:
    def test_media_rejects_ssrf_domain_spoofing(self):
        # Attacker domains with twimg.com as substring
        attacker_urls = [
            "https://pbs.twimg.com.attacker.com/media/malicious.jpg",
            "https://evil-twimg.com/media/malicious.jpg",
            "https://twimg.com.evil.org/profile_images/123/avatar_normal.jpg",
            "https://evil.com/twimg.com/profile_banners/123/600x200",
        ]
        for url in attacker_urls:
            # Must NOT rewrite attacker domains with :orig or /1500x500
            assert resolve_orig_image_url(url) == url
            assert resolve_avatar_orig(url) == url
            assert resolve_banner_orig(url) == url

    def test_video_variants_none_content_type_and_url(self):
        # Malformed video variants shouldn't crash select_highest_bitrate_video
        variants = [
            {"content_type": None, "url": "https://video.twimg.com/1.mp4"},
            {"content_type": "video/mp4", "url": None},
            None,
            "not a dict",
            {"content_type": "video/mp4", "url": "https://video.twimg.com/valid.mp4", "bitrate": 832000},
        ]
        best = select_highest_bitrate_video(variants)
        assert best is not None
        assert best["url"] == "https://video.twimg.com/valid.mp4"

    def test_video_variants_handles_string_and_negative_bitrates(self):
        variants = [
            {"content_type": "video/mp4", "url": "https://video.twimg.com/neg.mp4", "bitrate": -1},
            {"content_type": "video/mp4", "url": "https://video.twimg.com/str.mp4", "bitrate": "1280000"},
            {"content_type": "video/mp4", "url": "https://video.twimg.com/low.mp4", "bitrate": 500000},
        ]
        best = select_highest_bitrate_video(variants)
        assert best is not None
        assert best["url"] == "https://video.twimg.com/str.mp4"

    def test_extract_media_with_null_video_info(self):
        # GraphQL payload where video_info is explicitly None
        payload = {
            "extended_entities": {
                "media": [
                    {
                        "id_str": "123",
                        "type": "video",
                        "video_info": None,
                        "media_url_https": "https://pbs.twimg.com/media/sample.jpg",
                    }
                ]
            }
        }
        extracted = extract_media_from_status(payload)
        assert len(extracted) == 1
        assert extracted[0]["id"] == "123"

    def test_avatar_orig_with_query_params_and_no_ext(self):
        u1 = "https://pbs.twimg.com/profile_images/123/avatar_normal.jpg?format=jpg"
        assert "_normal" not in resolve_avatar_orig(u1)


# ==============================================================================
# 5. IDENTITY & CLI EDGE CASES
# ==============================================================================

class TestIdentityAndCLIEdgeCases:
    def test_cf_ray_header_on_valid_200_json_is_not_blocked(self):
        # Legitimate 200 JSON through Cloudflare CDN shouldn't trigger bot block false positive
        def mock_cdn_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                headers={"cf-ray": "1234567890abcdef-SIN", "content-type": "application/json"},
                text=json.dumps({"valid": True, "taken": False, "msg": "Available!"}),
            )

        client = httpx.Client(transport=httpx.MockTransport(mock_cdn_handler))
        res = check_username_available("gooduser", client=client)
        assert res["error"] is None
        assert res["taken"] is False
        assert res["valid"] is True

    def test_invalid_username_characters_not_reported_as_taken(self):
        def mock_invalid_handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                200,
                json={"valid": False, "msg": "Username contains invalid characters", "desc": "Username contains invalid characters"},
            )

        client = httpx.Client(transport=httpx.MockTransport(mock_invalid_handler))
        res = check_username_available("用戶", client=client)
        assert res["valid"] is False
        assert res["taken"] is False  # Must NOT report taken=True for invalid handle

    def test_nitter_handles_regex_metacharacters(self):
        # Screen names with brackets or metacharacters must not raise PatternError
        for bad_name in ("user[name", "foo(bar", "test+account", "name.with.dots"):
            found = fetch_nitter_timeline_ids(bad_name, instances=["https://xcancel.com"], max_pages=1)
            assert isinstance(found, set)

    def test_cli_screen_name_validation(self):
        # Passing empty or whitespace or @ should return 1 immediately without hanging
        assert run(["@"]) == 1
        assert run(["   "]) == 1
        assert run([""]) == 1
