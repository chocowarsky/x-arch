"""x-archaeologist: find the verified earliest activity of an X/Twitter account.

Core insight (learned the hard way): X's own search index (`from:user until:date`)
has gaps for accounts that went dormant for long stretches — it will confidently
report "0 results" for periods where the account was actually posting. The only
reliable way to find true earliest activity is to cross-check independent,
X-unaffiliated archives (Wayback Machine) and decode the real creation timestamp
baked into each Tweet's Snowflake ID, rather than trusting crawl order or search
results.
"""

from .snowflake import snowflake_to_datetime, TWITTER_EPOCH_MS
from .wayback import fetch_archived_status_ids, WaybackError
from .report import EarliestActivityReport, build_report

__version__ = "0.1.0"

__all__ = [
    "snowflake_to_datetime",
    "TWITTER_EPOCH_MS",
    "fetch_archived_status_ids",
    "WaybackError",
    "EarliestActivityReport",
    "build_report",
]
