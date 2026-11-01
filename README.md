# x-archaeologist

**Find the real earliest activity of any X/Twitter account — verified against independent archives, not X's own search index.**

```bash
pip install x-archaeologist
x-archaeologist bevanpramudt
```
```text
@bevanpramudt — verified earliest archived activity
  Date (UTC):     2020-09-23T21:28:39.658000+00:00
  Status ID:      1308986682906152960
  URL:            https://x.com/bevanpramudt/status/1308986682906152960
  Total IDs found: 4624
  Sources used:    wayback_machine
```

## Why this exists

Ask X's own search for "every post from this account before [date]" and it will
confidently answer **"No results"** — even when the account has years of real,
public posts before that date. This happened during a real investigation: X's
`from:user until:2022-01-01` search returned zero results for an account with
hundreds of archived 2020–2021 tweets. The search index has **silent gaps** for
accounts that went dormant for long stretches, and it never tells you it's
incomplete.

Scraper libraries that spoof the official client (`twikit`, `twint`, and
similar GraphQL-replay tools) don't fix this either — in 2026 they get blocked
by Cloudflare's TLS fingerprint check even with valid login cookies, because
they use plain HTTP clients that don't match a real browser's handshake.

**x-archaeologist never talks to X.com at all.** It queries the
[Wayback Machine](https://web.archive.org)'s CDX API — a free, independent,
read-only archive — for every snapshot of `twitter.com/<user>/status/*` it has
ever crawled, then decodes the real creation timestamp out of each tweet's
[Snowflake ID](https://github.com/twitter/snowflake) (the ID itself encodes
the exact millisecond it was created — no need to trust crawl order).

## Install

```bash
pip install x-archaeologist
# or, for local development:
git clone <this-repo>
cd x-archaeologist
pip install -e ".[dev]"
```

## Usage

```bash
# Basic lookup
x-archaeologist some_handle

# Narrow the search window (faster for accounts with 10+ years of history)
x-archaeologist some_handle --from-year 2015 --to-year 2018

# Machine-readable output
x-archaeologist some_handle --json

# Add a live Nitter instance as a supplementary cross-check (optional, best-effort)
x-archaeologist some_handle --with-nitter --nitter-instance https://your-instance.example
```

As a library:

```python
from x_archaeologist import fetch_archived_status_ids, build_report

ids = fetch_archived_status_ids("some_handle")
report = build_report("some_handle", ids, source_labels=["wayback_machine"])

print(report.earliest_datetime)  # datetime.datetime, UTC
print(report.earliest_url)       # "https://x.com/some_handle/status/..."
```

## How it works

1. **Query the Wayback Machine CDX API** for every archived snapshot of
   `twitter.com/<handle>/status/*`. This returns hundreds to thousands of
   `(crawl_timestamp, url, http_status)` rows — the same tweet is often
   crawled multiple times.
2. **Extract and deduplicate status IDs** from the URLs.
3. **Decode each ID's Snowflake timestamp** (`(id >> 22) + 1288834974657` ms
   since Unix epoch). Because IDs are monotonically increasing with creation
   time, sorting IDs numerically *is* sorting them chronologically — no need
   to trust which order the archive discovered them in.
4. **Report the smallest ID** as the verified earliest archived activity,
   with its real URL and decoded timestamp.

## What this tool does **not** claim

- It does not claim the reported tweet is the account's *literal first ever
  post*. It is the earliest one that survives in any archive this tool
  checked. If an account's true first tweets were never crawled by Wayback
  (common for the first days after account creation, before any search
  engine or archive bot has indexed it), this tool cannot recover them —
  nothing can, short of X's own internal database.
- The `--with-nitter` flag is a best-effort supplementary signal only. Public
  Nitter instances rate-limit hard and their pagination reliably **stalls**
  after 30–60 pages when walking deep into history (confirmed empirically —
  it silently starts re-serving the first page instead of erroring). Never
  trust a Nitter-only result as the true earliest tweet.
- The Wayback Machine itself occasionally returns a transient
  "Temporarily Offline" page instead of JSON. This tool retries with backoff,
  but if the outage outlasts the retry budget, it raises `WaybackError` —
  it never silently returns an incomplete answer as if it were final.

## Development

```bash
pip install -e ".[dev]"
pytest
```

All tests run against mocked HTTP transports (`httpx.MockTransport`) — no
live network calls, no flaky CI from Wayback Machine outages.

## License

MIT — see [LICENSE](LICENSE).
