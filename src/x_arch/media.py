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

# Common tracking and telemetry parameters injected by Twitter web and mobile clients
TRACKING_PARAMS = {
    "s",
    "t",
    "ref_src",
    "ref_url",
    "src",
    "vertical",
    "mx",
    "utm_source",
    "utm_medium",
    "utm_campaign",
    "utm_term",
    "utm_content",
}

VIDEO_DIMENSION_REGEX = re.compile(r"/vid/(?:avc1/)?(\d{2,5})x(\d{2,5})/")
COLON_SIZE_REGEX = re.compile(
    r":(?:large|medium|small|thumb|tiny|mini|900x900|\d+x\d+)$", re.IGNORECASE
)


def _is_twitter_media_domain(netloc: str) -> bool:
    """Validate that netloc strictly belongs to Twitter CDN (*.twimg.com)."""
    hostname = netloc.split(":")[0].lower()
    return hostname == "twimg.com" or hostname.endswith(".twimg.com")


def resolve_orig_image_url(url: str) -> str:
    """Transform any Twitter image URL into its highest possible resolution (:orig / name=orig).

    Examples:
        https://pbs.twimg.com/media/F9abcdef?format=jpg&name=small
        -> https://pbs.twimg.com/media/F9abcdef?format=jpg&name=orig

        https://pbs.twimg.com/media/F9abcdef.jpg:large
        -> https://pbs.twimg.com/media/F9abcdef.jpg:orig

        https://pbs.twimg.com/media/F9abcdef.jpg
        -> https://pbs.twimg.com/media/F9abcdef.jpg:orig
    """
    if not url:
        return ""

    # If already ending with :orig, return as-is
    if url.endswith(":orig"):
        return url

    # Handle legacy colon suffix: e.g. .jpg:large, .jpg:medium, .png:small, :thumb, etc.
    if COLON_SIZE_REGEX.search(url):
        return COLON_SIZE_REGEX.sub(":orig", url)

    parsed = urlparse(url)
    if _is_twitter_media_domain(parsed.netloc) and "/media/" in parsed.path:
        # Check if URL uses query parameters (modern Twitter web format)
        if parsed.query or "format=" in parsed.query:
            query_dict = dict(parse_qsl(parsed.query))
            if query_dict.get("name") == "orig":
                return url
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

        # Direct file path without query, e.g. https://pbs.twimg.com/media/F9abcdef.jpg
        if re.search(r"\.(?:jpe?g|png|webp)$", parsed.path, re.IGNORECASE):
            return f"{url}:orig"

        # Fallback query parameter
        return f"{url}?name=orig"

    return url


def resolve_avatar_orig(url: str) -> str:
    """Strip size suffixes (_normal, _bigger, _mini, _200x200) from profile avatar to get full original.

    Examples:
        https://pbs.twimg.com/profile_images/123/avatar_normal.jpg
        -> https://pbs.twimg.com/profile_images/123/avatar.jpg
    """
    if not url:
        return ""

    parsed = urlparse(url)
    if _is_twitter_media_domain(parsed.netloc) and "/profile_images/" in parsed.path:
        new_path = re.sub(
            r"_(?:normal|bigger|mini|\d+x\d+)(?=(\.[a-zA-Z0-9]+)?$)", "", parsed.path
        )
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
    if _is_twitter_media_domain(parsed.netloc) and "/profile_banners/" in parsed.path:
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
    if not variants or not isinstance(variants, list):
        return None

    mp4_candidates: list[tuple[int, dict[str, Any]]] = []

    for variant in variants:
        if not isinstance(variant, dict):
            continue

        content_type = str(variant.get("content_type") or "")
        url = str(variant.get("url") or "")

        if not url:
            continue

        # Skip HLS manifests
        if "mpegURL" in content_type or url.endswith(".m3u8"):
            continue

        if content_type == "video/mp4" or url.endswith(".mp4") or ".mp4?" in url:
            bitrate_raw = variant.get("bitrate")
            bitrate: int | None = None
            if bitrate_raw is not None:
                try:
                    bitrate = int(bitrate_raw)
                    if bitrate < 0:
                        bitrate = 0
                except (ValueError, TypeError):
                    bitrate = None

            if bitrate is not None:
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


def extract_media_from_status(status_payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract and resolve all media items from an X/Twitter status payload into highest quality.

    Supports:
    - Standard REST API v1.1 / archive payloads (`extended_entities.media` or `entities.media`)
    - GraphQL payloads (`legacy.extended_entities.media`, `tweetResult.result.legacy...`)
    - Twitter player/summary cards

    Returns:
        List of dicts, each containing:
            id: str
            type: "photo" | "video" | "animated_gif"
            url: str (original high-res image URL or highest bitrate MP4 video URL)
            thumbnail_url: str | None
            bitrate: int | None (for videos/gifs)
    """
    if not isinstance(status_payload, dict):
        return []

    raw_media: list[dict[str, Any]] = []

    # 1. Standard REST v1.1 extended_entities
    if "extended_entities" in status_payload and isinstance(
        status_payload["extended_entities"], dict
    ):
        raw_media = status_payload["extended_entities"].get("media", [])

    # 2. GraphQL legacy extended_entities
    if not raw_media:
        legacy = status_payload.get("legacy")
        if isinstance(legacy, dict) and "extended_entities" in legacy:
            raw_media = legacy["extended_entities"].get("media", [])

    # 3. Nested tweetResult -> result -> legacy (Twitter Web GraphQL)
    if not raw_media:
        result = (
            status_payload.get("data", {})
            .get("tweetResult", {})
            .get("result", {})
        )
        if isinstance(result, dict):
            res_legacy = result.get("legacy") or result.get("tweet", {}).get("legacy")
            if isinstance(res_legacy, dict) and "extended_entities" in res_legacy:
                raw_media = res_legacy["extended_entities"].get("media", [])

    # 4. tweet -> legacy
    if not raw_media and "tweet" in status_payload and isinstance(status_payload["tweet"], dict):
        t_legacy = status_payload["tweet"].get("legacy", {})
        if isinstance(t_legacy, dict) and "extended_entities" in t_legacy:
            raw_media = t_legacy["extended_entities"].get("media", [])

    # 5. Standard entities fallback
    if not raw_media and "entities" in status_payload and isinstance(
        status_payload["entities"], dict
    ):
        raw_media = status_payload["entities"].get("media", [])

    # 6. Card fallback
    if not raw_media and "card" in status_payload and isinstance(status_payload["card"], dict):
        binding_values = status_payload["card"].get("binding_values")
        if isinstance(binding_values, dict):
            for k, val in binding_values.items():
                if isinstance(val, dict) and "image_value" in val:
                    img_url = val["image_value"].get("url")
                    if img_url:
                        raw_media.append({
                            "id_str": k,
                            "type": "photo",
                            "media_url_https": img_url,
                        })

    extracted: list[dict[str, Any]] = []
    for item in raw_media:
        if not isinstance(item, dict):
            continue

        media_type = item.get("type", "photo")
        media_id = str(item.get("id_str") or item.get("id", ""))
        raw_url = item.get("media_url_https") or item.get("media_url") or item.get("url", "")
        thumbnail_url = (
            resolve_orig_image_url(clean_tracking_params(raw_url)) if raw_url else None
        )

        resolved_url: str | None = None
        bitrate: int | None = None

        if media_type in ("video", "animated_gif"):
            video_info = item.get("video_info")
            variants = video_info.get("variants", []) if isinstance(video_info, dict) else []
            best_variant = select_highest_bitrate_video(variants)
            if best_variant:
                resolved_url = clean_tracking_params(best_variant.get("url", ""))
                bitrate = best_variant.get("bitrate")
            else:
                resolved_url = thumbnail_url
        elif media_type == "photo":
            resolved_url = thumbnail_url
        else:
            resolved_url = clean_tracking_params(raw_url)

        res_item: dict[str, Any] = {
            "id": media_id,
            "type": media_type,
            "url": resolved_url,
            "thumbnail_url": thumbnail_url,
        }
        if bitrate is not None:
            res_item["bitrate"] = bitrate

        extracted.append(res_item)

    return extracted
