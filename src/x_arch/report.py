"""Assemble the final earliest-activity and behavioral report from one or more data sources."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from .profiler import ActivityProfile, profile_activity
from .snowflake import snowflake_to_datetime, sort_ids_chronologically


@dataclass
class EarliestActivityReport:
    """The result of an earliest-activity search and timeline profiling for one X account."""

    screen_name: str
    all_ids: list[int]
    sources_used: list[str] = field(default_factory=list)
    activity_profile: ActivityProfile | None = None

    @property
    def earliest_id(self) -> int | None:
        return self.all_ids[0] if self.all_ids else None

    @property
    def earliest_datetime(self):
        if self.earliest_id is None:
            return None
        return snowflake_to_datetime(self.earliest_id)

    @property
    def earliest_url(self) -> str | None:
        if self.earliest_id is None:
            return None
        return f"https://x.com/{self.screen_name}/status/{self.earliest_id}"

    @property
    def total_unique_ids(self) -> int:
        return len(self.all_ids)

    def generate_profile(self, dormancy_threshold_days: int = 90) -> ActivityProfile:
        """Compute the circadian activity profile from all recovered status IDs."""
        self.activity_profile = profile_activity(
            self.all_ids, dormancy_threshold_days=dormancy_threshold_days
        )
        return self.activity_profile

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "screen_name": self.screen_name,
            "earliest_id": self.earliest_id,
            "earliest_datetime_utc": (
                self.earliest_datetime.isoformat() if self.earliest_datetime else None
            ),
            "earliest_url": self.earliest_url,
            "total_unique_ids_found": self.total_unique_ids,
            "sources_used": self.sources_used,
        }
        if self.activity_profile is not None:
            data["activity_profile"] = self.activity_profile.to_dict()
        return data


def build_report(
    screen_name: str,
    *id_sets: set[int],
    source_labels: list[str] | None = None,
    include_profile: bool = False,
    dormancy_threshold_days: int = 90,
) -> EarliestActivityReport:
    """Merge any number of ID sets (from different sources) into one report.

    Args:
        screen_name: The account's handle, without ``@``.
        *id_sets: One ``set[int]`` of status IDs per data source.
        source_labels: Optional human-readable names for each source, in the
            same order as ``id_sets``, for provenance in the report.
        include_profile: If True, automatically compute the circadian activity
            profile and dormancy intervals.
        dormancy_threshold_days: Days gap required to classify an inactive period.

    Returns:
        An :class:`EarliestActivityReport` with all IDs merged and sorted
        chronologically ascending (oldest first).
    """
    combined: set[int] = set()
    for id_set in id_sets:
        combined |= id_set

    sorted_ids = sort_ids_chronologically(combined)
    report = EarliestActivityReport(
        screen_name=screen_name,
        all_ids=sorted_ids,
        sources_used=source_labels or [f"source_{i}" for i in range(len(id_sets))],
    )

    if include_profile and sorted_ids:
        report.generate_profile(dormancy_threshold_days=dormancy_threshold_days)

    return report
