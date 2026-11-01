"""Decode X/Twitter Snowflake status and user IDs into real creation timestamps.

Every ID X issues (tweets, user IDs created after 2010) is a Snowflake ID: a
64-bit integer with the creation timestamp bit-packed into the high bits.
Decoding it gives the exact moment the object was created, independent of
when any crawler or scraper happened to observe it. This is what lets us sort
tweets into true chronological order even when they were discovered in a
random, deduplicated order from a web archive.

Reference: https://github.com/twitter/snowflake (archived) and the public
epoch value used by X's production Snowflake generator.
"""

from __future__ import annotations

import datetime as _dt

# X (Twitter) Snowflake epoch: 2010-11-04T01:42:54.657Z, in milliseconds since
# the Unix epoch. Every Snowflake ID encodes milliseconds-since-this-epoch in
# its top 42 bits (id >> 22).
TWITTER_EPOCH_MS = 1288834974657


def snowflake_to_datetime(snowflake_id: int | str) -> _dt.datetime:
    """Decode a Snowflake ID (tweet or user) into a UTC datetime.

    Args:
        snowflake_id: A Twitter/X Snowflake ID, as an int or a numeric string.

    Returns:
        An aware ``datetime.datetime`` in UTC representing the moment the
        object was created.

    Raises:
        ValueError: If ``snowflake_id`` is not a valid positive integer, or
            decodes to a timestamp before the Snowflake epoch (meaning it is
            not actually a Snowflake ID — e.g. a pre-Snowflake legacy ID).
    """
    sid = int(snowflake_id)
    if sid < 0:
        raise ValueError(f"Snowflake ID must be non-negative, got {sid}")

    milliseconds = (sid >> 22) + TWITTER_EPOCH_MS
    if milliseconds < TWITTER_EPOCH_MS:
        raise ValueError(
            f"ID {sid} decodes before the Snowflake epoch — it is likely a "
            "legacy pre-2010 ID, not a true Snowflake ID."
        )
    return _dt.datetime.fromtimestamp(milliseconds / 1000, tz=_dt.timezone.utc)


def sort_ids_chronologically(ids: "set[int] | list[int]") -> list[int]:
    """Return IDs sorted ascending — because Snowflake IDs are monotonic with
    creation time, numeric sort IS chronological sort. No decoding needed for
    ordering; decoding is only needed to render a human-readable timestamp.
    """
    return sorted(set(int(i) for i in ids))
