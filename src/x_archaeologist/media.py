"""Media URL resolution, quality maximization, and privacy tracking sanitization.

Standardizes Twitter CDN media URLs into their highest-quality, uncompressed, original
lossless representations.

Derived from proven reverse-engineering discoveries in:
- EltonChou/TwitterMediaHarvest
- BandarHL/BHTwitter
- robertodoering/harpy
- nonbili/Nora
"""

from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlparse, urlunparse

# Common tracking parameters injected by Twitter web and mobile clients
TRACKING_PARAMS = {
    "s",
    "t",
    "ref_src",
    "ref_url",
    "src",
    "vertical",
    "mx",
}

VIDEO_DIMENSION_REGEX = re.compile(r"/vid/(?:avc1/)?(\d{2,5})x(\d{2,5})/")


def resolve_orig_image_url(url: str) -> str:
    """Transform any Twitter image URL into its highest possible resolution (:orig / name=orig).

    Examples:
        https://pbs.twimg.com/media/F9abcdef?format=jpg&name=small
        -> https://pbs.twimg.com/media/F9abcdef?format=jpg&name=orig

        https://pbs.twimg.com/media/F9abcdef.jpg:large
        -> https://pbs.twimg.com/media/F9abcdef.jpg:orig
    """
    if not url:
        return ""

    # Handle legacy colon suffix: e.g. .jpg:large, .jpg:medium, .png:small
    if ":large" in url or ":medium" in url or ":small" in url or ":900x900" in url or ":thumb" in url:
        return re.sub(r":(?:large|medium|small|900x900|thumb)$", ":orig", url)

    parsed = urlparse(url)
    if "twimg.com" in parsed.netloc and "/media/" in parsed.path:
        query_dict = dict(parse_qsl(parsed.query))
        query_dict["name"] = "orig"
        new_query = urlencode(query_dict)
        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                parsed.path,
                parsed.params,
                new_query,
                parsed.fragment,
            )
        )

    return url


def resolve_avatar_orig(url: str) -> str:
    """Strip size suffixes (_normal, _bigger, _mini) from profile avatar to get full original.

    Examples:
        https://pbs.twimg.com/profile_images/123/avatar_normal.jpg
        -> https://pbs.twimg.com/profile_images/123/avatar.jpg
    """
    if not url:
        return ""

    parsed = urlparse(url)
    if "twimg.com" in parsed.netloc and "/profile_images/" in parsed.path:
        new_path = re.sub(r"_(?:normal|bigger|mini)(?=\.[a-zA-Z0-9]+$)", "", parsed.path)
        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                new_path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            )
        )

    return url


def resolve_banner_orig(url: str) -> str:
    """Ensure Twitter banner URL targets the maximum 1500x500 dimension.

    Examples:
        https://pbs.twimg.com/profile_banners/123/600x200
        -> https://pbs.twimg.com/profile_banners/123/1500x500
    """
    if not url:
        return ""

    parsed = urlparse(url)
    if "twimg.com" in parsed.netloc and "/profile_banners/" in parsed.path:
        new_path = re.sub(r"/\d+x\d+$", "/1500x500", parsed.path)
        if not re.search(r"/1500x500$", new_path):
            new_path = new_path.rstrip("/") + "/1500x500"
        return urlunparse(
            (
                parsed.scheme,
                parsed.netloc,
                new_path,
                parsed.params,
                parsed.query,
                parsed.fragment,
            )
        )

    return url


def select_highest_bitrate_video(variants: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Given Twitter video variant dicts, select the single MP4 with the highest bitrate.

    Automatically discards HLS streaming manifests (application/x-mpegURL or .m3u8).
    """
    if not variants:
        return None

    mp4_candidates: list[tuple[int, dict[str, Any]]] = []

    for variant in variants:
        content_type = variant.get("content_type", "")
        url = variant.get("url", "")

        # Skip HLS manifests
        if "mpegURL" in content_type or url.endswith(".m3u8"):
            continue

        if content_type == "video/mp4" or url.endswith(".mp4") or ".mp4?" in url:
            bitrate = variant.get("bitrate")
            if bitrate is not None and isinstance(bitrate, int):
                mp4_candidates.append((bitrate, variant))
            else:
                # Try to parse dimensions from URL as secondary bitrate proxy
                match = VIDEO_DIMENSION_REGEX.search(url)
                if match:
                    w, h = int(match.group(1)), int(match.group(2))
                    pixel_proxy = w * h
                    mp4_candidates.append((pixel_proxy, variant))
                else:
                    mp4_candidates.append((0, variant))

    if not mp4_candidates:
        return None

    # Sort descending by bitrate/proxy
    mp4_candidates.sort(key=lambda item: item[0], reverse=True)
    return mp4_candidates[0][1]


def clean_tracking_params(url: str) -> str:
    """Strip tracking and referral query parameters (?s=..., &t=...) from X/Twitter URLs."""
    if not url:
        return ""

    parsed = urlparse(url)
    if not parsed.query:
        return url

    query_pairs = parse_qsl(parsed.query, keep_blank_values=True)
    filtered = [(k, v) for k, v in query_pairs if k.lower() not in TRACKING_PARAMS]

    new_query = urlencode(filtered) if filtered else ""
    return urlunparse(
        (
            parsed.scheme,
            parsed.netloc,
            parsed.path,
            parsed.params,
            new_query,
            parsed.fragment,
        )
    )
