# x-arch

**Find the real earliest activity, behavioral rhythms, and uncompressed media of any X/Twitter account — verified against independent archives, not X's own gappy search index.**

```bash
pip install x-arch
x-arch bevanpramudt --profile
```
```text
@bevanpramudt — verified earliest archived activity
  Date (UTC):      2020-09-23T21:28:39.658000+00:00
  Status ID:       1308986682906152960
  URL:             https://x.com/bevanpramudt/status/1308986682906152960
  Total IDs found: 4624
  Sources used:    wayback_machine

  Offline Behavioral & Circadian Profile:
    Active Timespan:      2218 days (2020-09-23T21:28:39.658000+00:00 to 2026-10-20T08:14:12.112000+00:00)
    Estimated Timezone:   UTC+7 (WIB / Indochina / Western Indonesia (Jakarta, Bangkok))
    Sleep Trough (UTC):   18:00 – 00:00 UTC (4.8% activity)
    Dormancy Gaps (>90d): 1 period(s) detected
      • 633 days inactive: 2022-08-14 -> 2024-05-09
```

---

## Why this exists

Ask X's own search for "every post from this account before [date]" and it will
confidently answer **"No results"** — even when the account has years of real,
public posts before that date. This happened during a real investigation: X's
`from:user until:2024-02-01` search returned zero results for an account with
thousands of archived 2020–2022 tweets. The search index has **silent gaps** for
accounts that went dormant for long stretches, and it never tells you it is
incomplete.

Scraper libraries that spoof the official client (`twikit`, `twint`, and
similar GraphQL-replay tools) don't fix this either:
1. In 2026, guest/unauthenticated search endpoints on X have been deprecated or locked down.
2. Even with valid session cookies, automated HTTP requests get blocked by Cloudflare's TLS fingerprint check because standard HTTP clients (`httpx`, `requests`) do not match a real browser's BoringSSL handshake.
3. Official Developer API v2 read access requires expensive enterprise tiers ($100/mo Basic is write-only or capped at 100 req/day).

**x-arch bypasses X's servers entirely for its core archive work.** It queries the
[Wayback Machine](https://web.archive.org)'s CDX API — a free, independent,
read-only archive — for every snapshot of `twitter.com/<user>/status/*` it has
ever crawled, then decodes the real creation timestamp out of each tweet's
[Snowflake ID](https://github.com/twitter/snowflake) (the ID itself encodes
the exact millisecond it was created — no need to trust crawl order).

---

## Features

### 1. Earliest Activity Recovery
Recovers the true earliest preserved tweet across millions of archive records, immune to X search index gaps.

### 2. Offline Circadian & Timezone Profiler (`--profile`)
Uses the millisecond timestamps encoded in recovered Snowflake IDs to calculate:
- **24-Hour Circadian Distribution**: Identifies the 5–6 hour sleep trough (*quiescent period*) where target activity drops to near zero.
- **Physical Timezone Estimation**: Calculates the probable physical UTC offset (e.g. UTC+7 WIB, UTC-5 EST) from natural sleep hours without IP tracking or GPS metadata.
- **Account Dormancy Gaps**: Pinpoints long multi-month or multi-year gaps where the user stopped posting (explaining why X search suffers index amnesia).

### 3. Lossless Media Resolution (`--resolve-media`)
Upgrades compressed Twitter CDN images, avatars, and banners into their original master quality:
- Resolves `pbs.twimg.com/media/...` to `:orig` / `name=orig`.
- Strips `_normal`, `_bigger`, `_mini` from avatar URLs to obtain original full-resolution profile photos.
- Upgrades profile banner URLs to max `/1500x500` resolution.
- Selects the highest-bitrate MP4 stream from video variants, discarding HLS `.m3u8` manifests.

### 4. Zero-Auth Identity Verification (`--check-email`, `--check-username`)
Uses public registration edge endpoints to check whether an email address or username is registered on X without needing API tokens or login cookies.

### 5. Privacy URL Sanitization (`--clean-url`)
Strips surveillance and tracking parameters (`?s=...`, `&t=...`, `ref_src=...`) from shared X/Twitter links.

---

## Install

```bash
pip install x-arch
# or, for local development:
git clone https://github.com/chocowarsky/x-arch.git
cd x-arch
pip install -e ".[dev]"
```

---

## Usage Examples

### CLI

```bash
# 1. Basic earliest tweet excavation
x-arch bevanpramudt

# 2. Complete earliest discovery + offline behavioral profiling
x-arch bevanpramudt --profile

# 3. Custom dormancy threshold (e.g. flag gaps >= 180 days)
x-arch bevanpramudt --profile --dormancy-days 180

# 4. Narrow the search window (speeds up large accounts)
x-arch bevanpramudt --from-year 2019 --to-year 2021

# 5. Machine-readable JSON output
x-arch bevanpramudt --profile --json

# 6. Resolve media to original lossless resolution
x-arch --resolve-media "https://pbs.twimg.com/media/F9abcdef?format=jpg&name=small"

# 7. Clean tracking parameters from URL
x-arch --clean-url "https://x.com/bevanpramudt/status/1308986682906152960?s=20&t=aBcDeF"

# 8. Zero-auth email registration check
x-arch --check-email user@example.com
```

### Python Library

```python
from x_arch import (
    fetch_archived_status_ids,
    build_report,
    profile_activity,
    resolve_orig_image_url,
    check_email_registered,
)

# Excavate & Profile
ids = fetch_archived_status_ids("bevanpramudt")
report = build_report("bevanpramudt", ids, include_profile=True)

print("Earliest Date:", report.earliest_datetime)
print("Earliest URL:", report.earliest_url)
print("Estimated Timezone:", report.activity_profile.estimated_timezone_label)
print("Sleep Trough:", report.activity_profile.quiescent_trough_utc)

# Resolve Media
orig_image = resolve_orig_image_url("https://pbs.twimg.com/media/F9abcdef?format=jpg&name=small")
print("Original Image:", orig_image)
```

---

## Provenance & Research

Architectural patterns and algorithmic techniques incorporated in `x-arch` were evaluated, empirically tested, and adapted from across 52 open-source X/Twitter research projects:
- **Offline Circadian Rhythm & Sleep Analysis**: Inspired by `x0rz/tweets_analyzer` and `vaguileradiaz/tinfoleak`.
- **Lossless Media Extraction**: Inspired by `EltonChou/TwitterMediaHarvest`, `BandarHL/BHTwitter`, and `robertodoering/harpy`.
- **Zero-Auth Edge Validation**: Inspired by `megadose/holehe` and `fa0311/TwitterInternalAPIDocument`.
- **Timeline & SQLite Caching Patterns**: Inspired by `klinker24/talon-for-twitter-android` and `TwidereProject/Twidere-Android`.

---

## License

MIT License. See [LICENSE](LICENSE) for details.
