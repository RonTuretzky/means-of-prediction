# NYT RSS metadata registry collection

The frozen public-RSS collection completed on September 14, 2026 UTC. It is a
metadata registry only, not an article corpus and not an alternate route to
blocked NYT article pages. The collector did not follow an RSS item URL or
request `www.nytimes.com`; full-text records: **0**.

The collection plan was written before network activity at:

`~/.local/share/means-of-prediction/nyt-article-registry-20260913/collection-plan.json`

The prior World feed availability probe is recorded as `unarchived_excluded`.
It was not reused as collection evidence. The collection made one new,
non-redirecting GET per planned feed, serially with a 0.5-second pace and a
2 MiB response cap. All raw feeds, normalized metadata records, plan, and
manifest are private write-once files (`0600`) in a private directory (`0700`).

| Feed | Collection UTC interval | HTTP | RSS items | Raw bytes |
|---|---|---:|---:|---:|
| World | 02:31:37.280–02:31:37.399 | 200 | 54 | 120,403 |
| US | 02:31:37.918–02:31:38.003 | 200 | 20 | 44,835 |
| Politics | 02:31:38.517–02:31:38.614 | 200 | 20 | 44,898 |
| Business | 02:31:39.129–02:31:39.225 | 200 | 49 | 101,995 |
| Technology | 02:31:39.747–02:31:39.851 | 200 | 24 | 49,759 |
| Science | 02:31:40.367–02:31:40.460 | 200 | 27 | 52,204 |
| Sports | 02:31:40.967–02:31:41.041 | 200 | 0 | 945 |
| HomePage | 02:31:41.547–02:31:41.638 | 200 | 21 | 45,524 |

The archived calls produced 215 item records. There are 178 distinct canonical
identities and 33 identities that appear in more than one feed. Dedupe is an
audit count only: every source-feed item/version remains retained with its
original URL(s), feed, item index, raw feed SHA-256, title, GUID, publication
date, and RSS description. Each record explicitly marks `metadata_only`, has
`full_text: null`, and is ineligible as full text.

The private manifest is:

`~/.local/share/means-of-prediction/nyt-article-registry-20260913/manifest.json`

It records status, timestamps, response byte lengths, SHA-256 hashes, parse
counts, and the zero article-link-follow count for each request. No `401`,
`403`, or `429` stop status occurred, so all eight planned feeds were attempted.

## Offline reconstruction audit

An independent offline audit reconstructed every record directly from the eight
archived raw XML feeds. It passed: all raw byte lengths and SHA-256 hashes
matched the manifest, every rebuilt record ID and metadata field matched its
stored normalized record, all 215 records retained the `metadata_only` flag
with null full text, and the captured directory/files retained `0700`/`0600`
permissions. The audit binds the plan, manifest, each raw feed, every
normalized record, and a private snapshot plus SHA-256 of the collector code.

Audit record:

`~/.local/share/means-of-prediction/nyt-article-registry-20260913/audit-20260914T0234Z/audit.json`

The 215 count is **feed-item occurrences**, while 178 is the count of distinct
canonical identities across them; 33 identities occur in more than one feed.
No deduplicated identity replaces or discards any occurrence. The reconstructed
normalized publication-date range is 2026-09-07T09:00:18Z through
2026-09-14T02:14:34Z (215/215 records dated).

The collector is [collect_rss.py](../app/scripts/research/article_collection/collect_rss.py);
the offline auditor is [audit_rss.py](../app/scripts/research/article_collection/audit_rss.py).
It rejects XML `DOCTYPE`/entity declarations before parsing, disables redirects,
and stops remaining planned feeds if a `401`, `403`, or `429` is encountered.

After capture, the collector success counter was tightened to require an
archived, parsed response without a fetch error. This prevents an oversized HTTP
200 response from counting as success in future runs. The frozen collector
snapshot records the exact capture version; all eight actual responses met the
stricter condition, so the recorded counts are unchanged.
