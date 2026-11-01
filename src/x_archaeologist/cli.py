"""Command-line interface for x-archaeologist.

Usage:
    x-archaeologist bevanpramudt
    x-archaeologist bevanpramudt --from-year 2018 --json
    x-archaeologist bevanpramudt --with-nitter --nitter-instance https://your-instance.example
"""

from __future__ import annotations

import argparse
import json
import sys

from .nitter import fetch_nitter_timeline_ids
from .report import build_report
from .wayback import WaybackError, fetch_archived_status_ids


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="x-archaeologist",
        description=(
            "Find the verified earliest archived activity of an X/Twitter "
            "account, cross-checked against the Wayback Machine instead of "
            "X's own (gappy) search index."
        ),
    )
    parser.add_argument("screen_name", help="X handle to look up, without @.")
    parser.add_argument(
        "--from-year",
        type=int,
        default=None,
        help="Only consider archives from this year onward (speeds up large accounts).",
    )
    parser.add_argument(
        "--to-year",
        type=int,
        default=None,
        help="Only consider archives up to this year.",
    )
    parser.add_argument(
        "--with-nitter",
        action="store_true",
        help=(
            "Also try a live Nitter instance as a supplementary source. "
            "Best-effort only — see the nitter module docstring for why "
            "this cannot be the primary source."
        ),
    )
    parser.add_argument(
        "--nitter-instance",
        default="https://nitter.net",
        help="Nitter instance base URL to use with --with-nitter.",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Emit machine-readable JSON instead of a human-readable summary.",
    )
    return parser


def run(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        wayback_ids = fetch_archived_status_ids(
            args.screen_name, from_year=args.from_year, to_year=args.to_year
        )
    except WaybackError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    id_sets = [wayback_ids]
    labels = ["wayback_machine"]

    if args.with_nitter:
        nitter_ids = fetch_nitter_timeline_ids(
            args.screen_name, instance=args.nitter_instance
        )
        id_sets.append(nitter_ids)
        labels.append(f"nitter:{args.nitter_instance}")

    report = build_report(args.screen_name, *id_sets, source_labels=labels)

    if report.earliest_id is None:
        if args.json:
            print(json.dumps(report.to_dict(), indent=2))
        else:
            print(
                f"No archived activity found for @{args.screen_name} in the "
                "requested range. Try widening --from-year/--to-year, or the "
                "account may simply have no Wayback Machine coverage."
            )
        return 0

    if args.json:
        print(json.dumps(report.to_dict(), indent=2))
    else:
        print(f"@{args.screen_name} — verified earliest archived activity")
        print(f"  Date (UTC):     {report.earliest_datetime.isoformat()}")
        print(f"  Status ID:      {report.earliest_id}")
        print(f"  URL:            {report.earliest_url}")
        print(f"  Total IDs found: {report.total_unique_ids}")
        print(f"  Sources used:    {', '.join(report.sources_used)}")
        print()
        print(
            "  Note: this is the earliest activity any checked archive has "
            "preserved. It may still predate the account's true creation if "
            "no archive captured the earlier period — see README for caveats."
        )

    return 0


def main() -> None:
    raise SystemExit(run())


if __name__ == "__main__":
    main()
