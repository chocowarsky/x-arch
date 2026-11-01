"""Example: full earliest-activity investigation for an X/Twitter account,
matching the real-world workflow this tool was built from.

Run: python examples/investigate_account.py <screen_name>
"""

from __future__ import annotations

import sys

from x_archaeologist import build_report, fetch_archived_status_ids
from x_archaeologist.wayback import WaybackError


def main() -> None:
    if len(sys.argv) != 2:
        print(f"Usage: python {sys.argv[0]} <screen_name>")
        raise SystemExit(1)

    screen_name = sys.argv[1]

    print(f"Querying the Wayback Machine for @{screen_name}...")
    try:
        ids = fetch_archived_status_ids(screen_name)
    except WaybackError as exc:
        print(f"Failed: {exc}")
        raise SystemExit(1)

    report = build_report(screen_name, ids, source_labels=["wayback_machine"])

    if report.earliest_id is None:
        print(f"No archived activity found for @{screen_name}.")
        return

    print(f"\nFound {report.total_unique_ids} unique archived status IDs.")
    print(f"Earliest verified activity:")
    print(f"  {report.earliest_datetime.isoformat()}")
    print(f"  {report.earliest_url}")
    print(
        "\nRemember: this is the earliest activity any archive preserved, "
        "not necessarily the account's literal first-ever post."
    )


if __name__ == "__main__":
    main()
