"""Unit tests for x_archaeologist.media (resolution enhancement, tracking cleanup)."""

from __future__ import annotations

from x_archaeologist.media import (
    clean_tracking_params,
    resolve_avatar_orig,
    resolve_banner_orig,
    resolve_orig_image_url,
    select_highest_bitrate_video,
)


def test_resolve_orig_image_url():
    # Query param style
    url1 = "https://pbs.twimg.com/media/F9abcdef?format=jpg&name=small"
    res1 = resolve_orig_image_url(url1)
    assert "name=orig" in res1
    assert "format=jpg" in res1

    # Colon format style
    url2 = "https://pbs.twimg.com/media/F9abcdef.jpg:large"
    res2 = resolve_orig_image_url(url2)
    assert res2 == "https://pbs.twimg.com/media/F9abcdef.jpg:orig"

    # Non-twimg url untouched
    url3 = "https://example.com/photo.jpg"
    assert resolve_orig_image_url(url3) == url3


def test_resolve_avatar_orig():
    url = "https://pbs.twimg.com/profile_images/1306114022886973440/avatar_normal.jpg"
    res = resolve_avatar_orig(url)
    assert res == "https://pbs.twimg.com/profile_images/1306114022886973440/avatar.jpg"

    url_bigger = "https://pbs.twimg.com/profile_images/123/pic_bigger.png"
    assert resolve_avatar_orig(url_bigger) == "https://pbs.twimg.com/profile_images/123/pic.png"


def test_resolve_banner_orig():
    url = "https://pbs.twimg.com/profile_banners/1306114022886973440/600x200"
    res = resolve_banner_orig(url)
    assert res == "https://pbs.twimg.com/profile_banners/1306114022886973440/1500x500"


def test_select_highest_bitrate_video():
    variants = [
        {"content_type": "application/x-mpegURL", "url": "https://video.twimg.com/ext_tw_video/1/pu/pl/master.m3u8"},
        {"content_type": "video/mp4", "bitrate": 256000, "url": "https://video.twimg.com/ext_tw_video/1/pu/vid/320x320/low.mp4"},
        {"content_type": "video/mp4", "bitrate": 2176000, "url": "https://video.twimg.com/ext_tw_video/1/pu/vid/720x720/high.mp4"},
        {"content_type": "video/mp4", "bitrate": 832000, "url": "https://video.twimg.com/ext_tw_video/1/pu/vid/480x480/med.mp4"},
    ]

    selected = select_highest_bitrate_video(variants)
    assert selected is not None
    assert selected["bitrate"] == 2176000
    assert "720x720" in selected["url"]


def test_select_highest_bitrate_video_empty():
    assert select_highest_bitrate_video([]) is None


def test_clean_tracking_params():
    url = "https://x.com/bevanpramudt/status/1308986682906152960?s=20&t=aBcDeF123&ref_src=twsrc"
    cleaned = clean_tracking_params(url)
    assert cleaned == "https://x.com/bevanpramudt/status/1308986682906152960"
    assert "s=" not in cleaned
    assert "t=" not in cleaned
