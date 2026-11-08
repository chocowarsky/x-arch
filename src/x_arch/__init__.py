"""x-archaeologist: find the verified earliest activity, behavioral rhythms, and media of an X/Twitter account.

Core insight (learned the hard way): X's own search index (`from:user until:date`)
has gaps for accounts that went dormant for long stretches — it will confidently
report "0 results" for periods where the account was actually posting. The only
reliable way to find true earliest activity is to cross-check independent,
X-unaffiliated archives (Wayback Machine) and decode the real creation timestamp
baked into each Tweet's Snowflake ID, rather than trusting crawl order or search
results.
"""

from .identity import (
    check_email_registered,
    check_username_available,
    decode_base64_user_id,
    snowflake_to_base64_user_id,
)
from .media import (
    clean_tracking_params,
    extract_media_from_status,
    resolve_avatar_orig,
    resolve_banner_orig,
    resolve_orig_image_url,
    select_highest_bitrate_video,
)
from .profiler import (
    ActivityProfile,
    DormancyPeriod,
    compute_hourly_distribution,
    compute_weekday_distribution,
    detect_dormancy_periods,
    detect_quiescent_trough,
    estimate_timezone_from_trough,
    profile_activity,
)
from .report import EarliestActivityReport, build_report
from .snowflake import TWITTER_EPOCH_MS, snowflake_to_datetime, sort_ids_chronologically
from .wayback import WaybackError, fetch_archived_status_ids

__version__ = "0.2.0"

__all__ = [
    # Snowflake
    "snowflake_to_datetime",
    "TWITTER_EPOCH_MS",
    "sort_ids_chronologically",
    # Wayback & Reporting
    "fetch_archived_status_ids",
    "WaybackError",
    "EarliestActivityReport",
    "build_report",
    # Profiler & Circadian
    "ActivityProfile",
    "DormancyPeriod",
    "compute_hourly_distribution",
    "compute_weekday_distribution",
    "detect_quiescent_trough",
    "estimate_timezone_from_trough",
    "detect_dormancy_periods",
    "profile_activity",
    # Media & Privacy
    "resolve_orig_image_url",
    "resolve_avatar_orig",
    "resolve_banner_orig",
    "select_highest_bitrate_video",
    "clean_tracking_params",
    "extract_media_from_status",
    # Identity & Registration
    "check_email_registered",
    "check_username_available",
    "decode_base64_user_id",
    "snowflake_to_base64_user_id",
]
