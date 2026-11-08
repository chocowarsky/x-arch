"""Command-line interface for x-arch.

Usage:
    x-arch bevanpramudt
    x-arch bevanpramudt --profile
    x-arch bevanpramudt --from-year 2018 --json
    x-arch bevanpramudt --with-nitter --nitter-instance https://your-instance.example
    x-arch --check-email user@example.com
    x-arch --resolve-media "https://pbs.twimg.com/media/F9abcdef?format=jpg&name=small"
"""

from __future__ import annotations

import argparse
import json
import sys

from .identity import check_email_registered, check_username_available
from .media import (
    clean_tracking_params,
    extract_media_from_status,
    resolve_avatar_orig,
    resolve_banner_orig,
    resolve_orig_image_url,
)
from .nitter import fetch_nitter_timeline_ids
from .report import build_report
from .wayback import WaybackError, fetch_archived_status_ids


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="x-arch",
        description=(
            "Find the verified earliest archived activity and behavioral intelligence "
            "of an X/Twitter account, cross-checked against independent archives "
            "instead of X's own (gappy) search index."
        ),
    )
    parser.add_argument(
        "screen_name",
        nargs="?",
        default=None,
        help="X handle to look up, without @.",
    )
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
        "--profile",
        action="store_true",
        help="Perform offline circadian rhythm, timezone, and dormancy profiling on all recovered IDs.",
    )
    parser.add_argument(
        "--dormancy-days",
        type=int,
        default=90,
        help="Minimum inactive gap in days to classify as an account dormancy period (default: 90).",
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
        default=None,
        help="Nitter instance base URL to use with --with-nitter (defaults to healthy community mirrors).",
    )
    parser.add_argument(
        "--check-email",
        type=str,
        default=None,
        help="Verify if an email address is registered on X using zero-auth registration API.",
    )
    parser.add_argument(
        "--check-username",
        type=str,
        default=None,
        help="Check if an X handle is taken or available using zero-auth registration API.",
    )
    parser.add_argument(
        "--resolve-media",
        type=str,
        default=None,
        help="Upgrade a Twitter image/avatar/banner URL to its maximum original resolution.",
    )
    parser.add_argument(
        "--clean-url",
        type=str,
        default=None,
        help="Strip Twitter tracking parameters (?s=..., &t=...) from a URL.",
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

    # 1. Utility: Zero-auth email registration check
    if args.check_email:
        res = check_email_registered(args.check_email)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            status_str = "REGISTERED / TAKEN" if res["registered"] else "NOT REGISTERED / AVAILABLE"
            if res.get("error"):
                status_str = f"ERROR ({res['error']})"
            print(f"Email:        {res['email']}")
            print(f"Status:       {status_str}")
            if res.get("msg"):
                print(f"Message:      {res['msg']}")
        return 0 if not res.get("error") else 1

    # 2. Utility: Zero-auth username availability check
    if args.check_username:
        res = check_username_available(args.check_username)
        if args.json:
            print(json.dumps(res, indent=2))
        else:
            status_str = "TAKEN" if res["taken"] else "AVAILABLE"
            if res.get("error"):
                status_str = f"ERROR ({res['error']})"
            print(f"Username:     @{res['username']}")
            print(f"Status:       {status_str}")
            if res.get("msg"):
                print(f"Message:      {res['msg']}")
        return 0 if not res.get("error") else 1

    # 3. Utility: Media URL resolution & payload extraction
    if args.resolve_media:
        target = args.resolve_media.strip()
        # Check if argument is a JSON payload or JSON file
        payload: dict | None = None
        if target.startswith("{") and target.endswith("}"):
            try:
                payload = json.loads(target)
            except Exception:
                pass
        elif target.endswith(".json"):
            try:
                with open(target, encoding="utf-8") as f:
                    payload = json.load(f)
            except Exception:
                pass

        if payload is not None:
            extracted = extract_media_from_status(payload)
            if args.json:
                print(json.dumps(extracted, indent=2))
            else:
                print(f"Extracted {len(extracted)} media items:")
                for m in extracted:
                    bitrate_info = f" ({m['bitrate']} bps)" if m.get("bitrate") else ""
                    print(f"  • [{m['type'].upper()}{bitrate_info}] {m['url']}")
            return 0

        url = target
        if "/profile_images/" in url:
            orig = resolve_avatar_orig(url)
        elif "/profile_banners/" in url:
            orig = resolve_banner_orig(url)
        else:
            orig = resolve_orig_image_url(url)
        cleaned = clean_tracking_params(orig)
        if args.json:
            print(json.dumps({"input_url": url, "resolved_url": cleaned}, indent=2))
        else:
            print(f"Original: {url}")
            print(f"Resolved: {cleaned}")
        return 0

    # 4. Utility: Clean tracking URL
    if args.clean_url:
        cleaned = clean_tracking_params(args.clean_url)
        if args.json:
            print(json.dumps({"input_url": args.clean_url, "cleaned_url": cleaned}, indent=2))
        else:
            print(cleaned)
        return 0

    # Require screen_name for excavation
    if not args.screen_name:
        parser.print_help(sys.stderr)
        return 1

    clean_screen_name = args.screen_name.lstrip("@").strip()
    if not clean_screen_name:
        print("error: screen_name cannot be empty or solely '@'", file=sys.stderr)
        return 1

    try:
        wayback_ids = fetch_archived_status_ids(
            clean_screen_name, from_year=args.from_year, to_year=args.to_year
        )
    except WaybackError as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    id_sets = [wayback_ids]
    labels = ["wayback_machine"]

    if args.with_nitter:
        nitter_ids = fetch_nitter_timeline_ids(
            clean_screen_name, instance=args.nitter_instance
        )
        id_sets.append(nitter_ids)
        inst_label = args.nitter_instance or "fallback_mirrors"
        labels.append(f"nitter:{inst_label}")

    report = build_report(
        clean_screen_name,
        *id_sets,
        source_labels=labels,
        include_profile=args.profile,
        dormancy_threshold_days=args.dormancy_days,
    )

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
        print(f"  Date (UTC):      {report.earliest_datetime.isoformat()}")
        print(f"  Status ID:       {report.earliest_id}")
        print(f"  URL:             {report.earliest_url}")
        print(f"  Total IDs found: {report.total_unique_ids}")
        print(f"  Sources used:    {', '.join(report.sources_used)}")

        if report.activity_profile is not None:
            prof = report.activity_profile
            print("\n  Offline Behavioral & Circadian Profile:")
            print(f"    Active Timespan:      {prof.timespan_days} days ({prof.first_status_utc} to {prof.last_status_utc})")
            print(f"    Estimated Timezone:   {prof.estimated_timezone_label}")
            print(f"    Sleep Trough (UTC):   {prof.quiescent_trough_utc[0]:02d}:00 – {prof.quiescent_trough_utc[1]:02d}:00 UTC ({prof.quiescent_percentage}% activity)")
            if prof.dormancy_periods:
                print(f"    Dormancy Gaps (>{args.dormancy_days}d): {len(prof.dormancy_periods)} period(s) detected")
                for gap in prof.dormancy_periods:
                    print(f"      • {gap.gap_days} days inactive: {gap.start_datetime_utc[:10]} -> {gap.end_datetime_utc[:10]}")

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
