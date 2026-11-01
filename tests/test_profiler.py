"""Unit tests for x_arch.profiler (circadian rhythms, timezone estimation, dormancy)."""

from __future__ import annotations

from datetime import datetime, timezone

from x_arch.profiler import (
    compute_hourly_distribution,
    compute_weekday_distribution,
    detect_dormancy_periods,
    detect_quiescent_trough,
    estimate_timezone_from_trough,
    profile_activity,
)
from x_arch.snowflake import TWITTER_EPOCH_MS


def _make_snowflake(dt: datetime) -> int:
    """Helper to generate a valid Snowflake ID matching a specific datetime."""
    ms_since_epoch = int(dt.timestamp() * 1000) - TWITTER_EPOCH_MS
    return ms_since_epoch << 22


def test_hourly_and_weekday_distribution():
    # Construct 3 dates:
    # 1. 2023-01-02 (Monday) 10:30 UTC
    # 2. 2023-01-02 (Monday) 10:45 UTC
    # 3. 2023-01-06 (Friday) 22:15 UTC
    dt1 = datetime(2023, 1, 2, 10, 30, tzinfo=timezone.utc)
    dt2 = datetime(2023, 1, 2, 10, 45, tzinfo=timezone.utc)
    dt3 = datetime(2023, 1, 6, 22, 15, tzinfo=timezone.utc)

    hourly = compute_hourly_distribution([dt1, dt2, dt3])
    assert hourly[10] == 2
    assert hourly[22] == 1
    assert hourly[0] == 0

    daily = compute_weekday_distribution([dt1, dt2, dt3])
    assert daily["Monday"] == 2
    assert daily["Friday"] == 1
    assert daily["Wednesday"] == 0


def test_detect_quiescent_trough_and_timezone():
    # Simulate a user active during European/Indonesian hours
    # Zero activity between 18:00 and 00:00 UTC (hours 18, 19, 20, 21, 22, 23)
    counts = {h: 10 for h in range(24)}
    for h in range(18, 24):
        counts[h] = 0

    start_h, end_h, pct = detect_quiescent_trough(counts, window_hours=6)
    assert start_h == 18
    assert end_h == 0
    assert pct == 0.0

    # 18:00 UTC trough start -> local sleep anchor ~ 01:00 -> 01:00 - 18:00 = UTC+7
    offset, label = estimate_timezone_from_trough(start_h, window_hours=6)
    assert offset == 7
    assert "UTC+7" in label
    assert "WIB" in label


def test_detect_dormancy_periods():
    # Create 3 tweets:
    # 1. 2020-01-01
    # 2. 2020-01-15 (14 days gap -> not dormant)
    # 3. 2021-01-15 (366 days gap -> dormant!)
    t1 = datetime(2020, 1, 1, tzinfo=timezone.utc)
    t2 = datetime(2020, 1, 15, tzinfo=timezone.utc)
    t3 = datetime(2021, 1, 15, tzinfo=timezone.utc)

    id1 = _make_snowflake(t1)
    id2 = _make_snowflake(t2)
    id3 = _make_snowflake(t3)

    gaps = detect_dormancy_periods([id1, id2, id3], threshold_days=90)
    assert len(gaps) == 1
    gap = gaps[0]
    assert gap.gap_days == 366
    assert gap.before_status_id == id2
    assert gap.after_status_id == id3


def test_profile_activity_empty():
    prof = profile_activity([])
    assert prof.total_statuses == 0
    assert prof.first_status_utc is None
    assert prof.dormancy_periods == []


def test_profile_activity_end_to_end():
    t1 = datetime(2020, 9, 24, 6, 41, tzinfo=timezone.utc)
    t2 = datetime(2020, 9, 25, 8, 12, tzinfo=timezone.utc)
    id1 = _make_snowflake(t1)
    id2 = _make_snowflake(t2)

    prof = profile_activity([id2, id1], dormancy_threshold_days=30)
    assert prof.total_statuses == 2
    assert prof.first_status_utc == t1.isoformat()
    assert prof.last_status_utc == t2.isoformat()
    assert prof.timespan_days == 1
    assert prof.to_dict()["total_statuses"] == 2
