"""Tests for x_arch.report — pure logic, no network."""

from __future__ import annotations

from x_arch.report import build_report


def test_build_report_merges_and_sorts_multiple_sources():
    source_a = {300, 100}
    source_b = {200, 100}  # 100 overlaps -> should not be double counted

    report = build_report(
        "bevanpramudt", source_a, source_b, source_labels=["wayback", "nitter"]
    )

    assert report.all_ids == [100, 200, 300]
    assert report.earliest_id == 100
    assert report.total_unique_ids == 3
    assert report.sources_used == ["wayback", "nitter"]


def test_build_report_with_no_ids_has_none_earliest():
    report = build_report("nobody_archived_this_handle", set())

    assert report.earliest_id is None
    assert report.earliest_datetime is None
    assert report.earliest_url is None
    assert report.total_unique_ids == 0


def test_earliest_url_is_well_formed():
    report = build_report("bevanpramudt", {1308986682906152960})

    assert report.earliest_url == "https://x.com/bevanpramudt/status/1308986682906152960"


def test_to_dict_is_json_serializable():
    import json

    report = build_report("bevanpramudt", {1308986682906152960})
    # Must not raise.
    json.dumps(report.to_dict())


def test_default_source_labels_when_none_provided():
    report = build_report("x", {1}, {2})
    assert report.sources_used == ["source_0", "source_1"]
