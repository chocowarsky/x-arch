"""Tests for x_archaeologist.snowflake — pure math, no network."""

from __future__ import annotations

import datetime as dt

import pytest

from x_archaeologist.snowflake import (
    TWITTER_EPOCH_MS,
    snowflake_to_datetime,
    sort_ids_chronologically,
)


def test_known_snowflake_decodes_to_known_date():
    # This ID is the earliest tweet x-archaeologist found for @bevanpramudt
    # via the Wayback Machine during real-world validation (2026-11-01).
    # Independently confirmed against the archived tweet's displayed
    # timestamp ("9:28 PM - 23 Sep 2020").
    result = snowflake_to_datetime(1308986682906152960)
    assert result.tzinfo is not None
    assert result.date() == dt.date(2020, 9, 23) or result.date() == dt.date(2020, 9, 24)
    # The displayed time was 21:28 in the archived page's local rendering;
    # decoded UTC should be within the same ~24h window.
    assert result.year == 2020
    assert result.month == 9


def test_accepts_string_input():
    assert snowflake_to_datetime("1308986682906152960") == snowflake_to_datetime(
        1308986682906152960
    )


def test_epoch_boundary_is_exact():
    # An ID of exactly 0 should decode to the Snowflake epoch itself.
    result = snowflake_to_datetime(0)
    expected = dt.datetime.fromtimestamp(TWITTER_EPOCH_MS / 1000, tz=dt.timezone.utc)
    assert result == expected


def test_negative_id_rejected():
    with pytest.raises(ValueError):
        snowflake_to_datetime(-1)


def test_sort_ids_chronologically_dedupes_and_sorts():
    ids = [300, 100, 200, 100, 300]
    assert sort_ids_chronologically(ids) == [100, 200, 300]


def test_sort_ids_chronologically_accepts_set():
    ids = {5, 3, 1, 4, 1, 5}
    assert sort_ids_chronologically(ids) == [1, 3, 4, 5]


def test_higher_id_always_decodes_later_or_equal():
    # Core invariant the whole tool relies on: Snowflake IDs are monotonic
    # with creation time, so numeric sort == chronological sort.
    earlier_id = 1308986682906152960
    later_id = 2091818801520341029  # a much more recent tweet ID
    assert snowflake_to_datetime(later_id) > snowflake_to_datetime(earlier_id)
