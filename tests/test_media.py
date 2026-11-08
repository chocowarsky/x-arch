"""Unit tests for x_arch.media (resolution enhancement, tracking cleanup)."""

from __future__ import annotations

from x_arch.media import (
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

    url_200 = "https://pbs.twimg.com/profile_images/123/pic_200x200.jpg"
    assert resolve_avatar_orig(url_200) == "https://pbs.twimg.com/profile_images/123/pic.jpg"


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


def test_resolve_orig_image_already_orig():
    url = "https://pbs.twimg.com/media/F9abcdef.jpg:orig"
    assert resolve_orig_image_url(url) == url

    url_query = "https://pbs.twimg.com/media/F9abcdef?format=png&name=orig"
    assert resolve_orig_image_url(url_query) == url_query


def test_extract_media_from_status_rest_payload():
    from x_arch.media import extract_media_from_status

    status_payload = {
        "id_str": "1234567890",
        "extended_entities": {
            "media": [
                {
                    "id_str": "101",
                    "type": "photo",
                    "media_url_https": "https://pbs.twimg.com/media/photo1.jpg:large",
                },
                {
                    "id_str": "102",
                    "type": "video",
                    "media_url_https": "https://pbs.twimg.com/media/thumb.jpg",
                    "video_info": {
                        "variants": [
                            {"content_type": "application/x-mpegURL", "url": "https://video.twimg.com/playlist.m3u8"},
                            {"content_type": "video/mp4", "bitrate": 500000, "url": "https://video.twimg.com/low.mp4?s=20"},
                            {"content_type": "video/mp4", "bitrate": 2000000, "url": "https://video.twimg.com/high.mp4?ref_src=twsrc"},
                        ]
                    },
                },
            ]
        },
    }

    media_items = extract_media_from_status(status_payload)
    assert len(media_items) == 2

    # Photo item
    assert media_items[0]["id"] == "101"
    assert media_items[0]["type"] == "photo"
    assert media_items[0]["url"] == "https://pbs.twimg.com/media/photo1.jpg:orig"

    # Video item
    assert media_items[1]["id"] == "102"
    assert media_items[1]["type"] == "video"
    assert media_items[1]["bitrate"] == 2000000
    assert media_items[1]["url"] == "https://video.twimg.com/high.mp4"
    assert "ref_src" not in media_items[1]["url"]  # Tracking cleaned


def test_extract_media_from_status_graphql_payload():
    from x_arch.media import extract_media_from_status

    graphql_payload = {
        "data": {
            "tweetResult": {
                "result": {
                    "legacy": {
                        "extended_entities": {
                            "media": [
                                {
                                    "id_str": "999",
                                    "type": "photo",
                                    "media_url_https": "https://pbs.twimg.com/media/gql_photo?format=jpg&name=medium",
                                }
                            ]
                        }
                    }
                }
            }
        }
    }

    media_items = extract_media_from_status(graphql_payload)
    assert len(media_items) == 1
    assert media_items[0]["id"] == "999"
    assert "name=orig" in media_items[0]["url"]


def test_extract_media_from_status_empty():
    from x_arch.media import extract_media_from_status

    assert extract_media_from_status({}) == []
    assert extract_media_from_status({"entities": {}}) == []
