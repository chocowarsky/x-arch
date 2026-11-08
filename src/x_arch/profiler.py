"""Circadian activity analysis and timezone estimation from Snowflake IDs.

This module implements offline behavioral profiling on top of Twitter Snowflake IDs
discovered through archives (like Wayback Machine CDX) or timeline data. Because
Snowflake IDs encode timestamps with millisecond precision, a target's 24-hour
circadian rhythm and multi-year lifecycle can be mapped 100% offline without
making any requests to X servers or needing API keys.

Inspired by algorithmic breakthroughs in x0rz/tweets_analyzer and vaguileradiaz/tinfoleak.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Sequence

from .snowflake import snowflake_to_datetime, sort_ids_chronologically

DAYS_OF_WEEK = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]


@dataclass
class DormancyPeriod:
    """A significant gap in activity between consecutive preserved tweets."""

    start_datetime_utc: str
    end_datetime_utc: str
    gap_days: int
    before_status_id: int
    after_status_id: int


@dataclass
class ActivityProfile:
    """Behavioral and circadian profile derived purely from Snowflake timestamps."""

    total_statuses: int
    first_status_utc: str | None
    last_status_utc: str | None
    timespan_days: int
    hourly_utc: dict[int, int]
    daily_distribution: dict[str, int]
    quiescent_trough_utc: tuple[int, int]
    quiescent_percentage: float
    estimated_utc_offset_hours: int
    estimated_timezone_label: str
    dormancy_periods: list[DormancyPeriod] = field(default_factory=list)

    def to_dict(self) -> dict:
        data = asdict(self)
        return data


def compute_hourly_distribution(datetimes: Sequence[datetime]) -> dict[int, int]:
    """Return count of tweets for each UTC hour (0 to 23)."""
    counts = {h: 0 for h in range(24)}
    for dt in datetimes:
        counts[dt.hour] += 1
    return counts


def compute_weekday_distribution(datetimes: Sequence[datetime]) -> dict[str, int]:
    """Return count of tweets for each day of week (Monday to Sunday)."""
    counts = {day: 0 for day in DAYS_OF_WEEK}
    for dt in datetimes:
        day_name = DAYS_OF_WEEK[dt.weekday()]
        counts[day_name] += 1
    return counts


def detect_quiescent_trough(
    hourly_counts: dict[int, int], window_hours: int = 6
) -> tuple[int, int, float]:
    """Find the sliding window of `window_hours` with the fewest total tweets.

    This represents the target's primary circadian resting/sleep period.

    Returns:
        (start_hour_utc, end_hour_utc, percentage_of_total_tweets)
    """
    counts = {h: hourly_counts.get(h, 0) for h in range(24)}
    total = sum(counts.values())
    if total == 0 or window_hours <= 0:
        return (0, max(0, window_hours), 0.0)

    best_start = 0
    min_count = float("inf")

    # Hourly counts form a 24-hour circular ring
    for start_h in range(24):
        window_sum = sum(counts[(start_h + i) % 24] for i in range(window_hours))
        if window_sum < min_count:
            min_count = window_sum
            best_start = start_h

    end_h = (best_start + window_hours) % 24
    pct = round((min_count / total) * 100.0, 2)
    return (best_start, end_h, pct)


def estimate_timezone_from_trough(
    start_trough_utc: int, window_hours: int = 6, quiescent_pct: float | None = None
) -> tuple[int, str]:
    """Deduce probable UTC offset assuming typical human sleep from ~01:00 to ~07:00 local time.

    If the sleep trough starts at `start_trough_utc`, we estimate:
    local_sleep_start (approx 01:00) = start_trough_utc + offset
    => offset = 1 - start_trough_utc
    Normalized to range [-12, +14].
    """
    # Detect uniform / 24-7 automated bot distributions
    expected_uniform = (window_hours / 24.0) * 100.0
    if quiescent_pct is not None and quiescent_pct >= (expected_uniform - 3.0):
        return (0, "UTC+0 (Uniform / 24-7 Activity / Bot - No Clear Sleep Trough)")

    # Target sleep onset anchor ~ 01:00 local time
    raw_offset = 1 - start_trough_utc

    # Normalize to -12 to +14 range
    while raw_offset < -12:
        raw_offset += 24
    while raw_offset > 14:
        raw_offset -= 24

    sign = "+" if raw_offset >= 0 else ""
    label = f"UTC{sign}{raw_offset}"

    # Annotate common regions for standard offsets
    regions = {
        -8: "PST / Pacific (US/Canada)",
        -5: "EST / Eastern (US/Canada)",
        0: "GMT / Western Europe",
        1: "CET / Central Europe",
        2: "EET / Eastern Europe",
        3: "MSK / Arabia / East Africa",
        5: "PKT / Pakistan",
        7: "WIB / Indochina / Western Indonesia (Jakarta, Bangkok)",
        8: "SGT / HKT / CST / WITA (Singapore, Bali, Taipei, Beijing)",
        9: "JST / KST / WIT (Tokyo, Seoul, Eastern Indonesia)",
    }
    desc = regions.get(raw_offset, "Standard Regional Time")
    return (raw_offset, f"{label} ({desc})")


def detect_dormancy_periods(
    sorted_ids: Sequence[int], threshold_days: int = 90
) -> list[DormancyPeriod]:
    """Find gaps between chronologically consecutive tweets exceeding `threshold_days`."""
    if threshold_days <= 0:
        raise ValueError(f"threshold_days must be positive, got {threshold_days}")
    if len(sorted_ids) < 2:
        return []

    dts = [snowflake_to_datetime(sid) for sid in sorted_ids]
    gaps: list[DormancyPeriod] = []

    for i in range(len(sorted_ids) - 1):
        dt1 = dts[i]
        dt2 = dts[i + 1]
        delta_days = (dt2 - dt1).days
        if delta_days >= threshold_days:
            gaps.append(
                DormancyPeriod(
                    start_datetime_utc=dt1.isoformat(),
                    end_datetime_utc=dt2.isoformat(),
                    gap_days=delta_days,
                    before_status_id=sorted_ids[i],
                    after_status_id=sorted_ids[i + 1],
                )
            )

    return gaps


def profile_activity(
    status_ids: Sequence[int], dormancy_threshold_days: int = 90
) -> ActivityProfile:
    """Generate a full ActivityProfile from an arbitrary collection of Snowflake IDs."""
    sorted_ids = sort_ids_chronologically(status_ids)
    if not sorted_ids:
        return ActivityProfile(
            total_statuses=0,
            first_status_utc=None,
            last_status_utc=None,
            timespan_days=0,
            hourly_utc={h: 0 for h in range(24)},
            daily_distribution={d: 0 for d in DAYS_OF_WEEK},
            quiescent_trough_utc=(0, 6),
            quiescent_percentage=0.0,
            estimated_utc_offset_hours=0,
            estimated_timezone_label="UTC+0 (Undetermined)",
            dormancy_periods=[],
        )

    dts = [snowflake_to_datetime(sid) for sid in sorted_ids]
    first_dt = dts[0]
    last_dt = dts[-1]
    timespan = max(0, (last_dt - first_dt).days)

    hourly = compute_hourly_distribution(dts)
    daily = compute_weekday_distribution(dts)
    trough_start, trough_end, trough_pct = detect_quiescent_trough(hourly, window_hours=6)
    offset, tz_label = estimate_timezone_from_trough(
        trough_start, window_hours=6, quiescent_pct=trough_pct
    )
    dormancies = detect_dormancy_periods(sorted_ids, threshold_days=dormancy_threshold_days)

    return ActivityProfile(
        total_statuses=len(sorted_ids),
        first_status_utc=first_dt.isoformat(),
        last_status_utc=last_dt.isoformat(),
        timespan_days=timespan,
        hourly_utc=hourly,
        daily_distribution=daily,
        quiescent_trough_utc=(trough_start, trough_end),
        quiescent_percentage=trough_pct,
        estimated_utc_offset_hours=offset,
        estimated_timezone_label=tz_label,
        dormancy_periods=dormancies,
    )
