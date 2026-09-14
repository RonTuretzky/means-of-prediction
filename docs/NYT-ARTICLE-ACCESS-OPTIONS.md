# NYT article access options (official-source review)

September 13, 2026. This is an access-and-rights note, not a claim that an
article corpus has been collected. It follows the recorded result that the
20-link publisher-request pilot produced no article text.

## Finding

The public NYT developer APIs can build a **metadata index**, but their
published response schemas are not a full-article corpus source. A usable
article corpus needs an access route whose applicable terms permit the planned
research and retention. A written NYT licence/authorization is one route; an
institutional or other legitimate provider route may have different terms that
must be checked before collection.

This distinction matters here: titles, snippets, URLs, publication dates,
tags, and word counts can help select and audit a sample; they must not be
counted as full articles or substituted for article evidence.

## Official public API: useful, but metadata only

| Interface | Authentication and operating constraints | What it returns | Corpus decision |
|---|---|---|---|
| [Article Search API](https://developer.nytimes.com/docs/articlesearch-product/1/overview) | API key supplied as the `api-key` query parameter. The current official specification documents `401` for a missing/invalid key and `429` when its per-minute or per-day limit is reached. It returns 10 results per page; the specification lists `page` with a maximum of 100, while its prose says “up to 100 pages.” Treat the boundary as an implementation detail to verify with a key. | The response schema contains URL, snippet, headline, byline, date, tags, section, type, word count, and limited image data. It does **not** contain a body-text field. `Article.body` appears only as a searchable filter field, which does not make the body available in results. | Use only to make an article *registry* and freeze candidate URLs/metadata after an API key is legitimately obtained. Do not call the registry a text corpus. |
| [Archive API](https://developer.nytimes.com/docs/archive-product/1/overview) | Same query-parameter API-key mechanism and `401`/`429` handling. The official specification warns that a monthly response can be about 20 MB and is not intended for browser calls. | An array of the same Article Search records for a month. Its own description says it is useful for a database of NYT **article metadata**. The declared Article fields likewise omit body text. | Suitable for inexpensive month-by-month metadata inventory after key provisioning; unsuitable as a full-text acquisition plan. |

The linked documentation pages are the human-facing API pages. The exact
publisher-hosted specifications used for the field/response check are
[Article Search specification](https://developer.nytimes.com/portals/api/sites/nyt-apigeex-prd-devportal/liveportal/apis/articlesearch-product/spec)
and [Archive specification](https://developer.nytimes.com/portals/api/sites/nyt-apigeex-prd-devportal/liveportal/apis/archive-product/spec).

The current official specifications identify that rate limiting exists, but do
not publish a numeric quota. Treat `429` as the operative signal; do not rely
on historical third-party quota figures. A key requires a developer-portal
application, which was deliberately not created in this bounded review.

## Full text: access and publisher terms

NYT's current [Terms of Service](https://thenewyorktimeshelpcenter.helpjuice.com/115002797688-Policies/115014893428-Terms-of-Service/version/2?kb_language=en_US)
cover APIs and RSS as Services. They say that NYT content—including text,
metadata, data and compilations—is protected; they prohibit automated
scraping, bypassing access controls, and caching or archiving Content. They
also state that their “non-commercial use” definition excludes AI/ML
development, training, fine-tuning, grounding/RAG, and supplying archived or
cached datasets without NYT’s prior written consent. Those publisher terms are
important for a direct NYT collection route; they do not by themselves resolve
every possible lawful research or licensed-provider arrangement.

If the project seeks permission directly from NYT, request a scoped written
licence/authorization through NYT's
[Rights and Permissions link in the Terms](https://nytimes.wrightsmedia.com/).
The licensing portal identifies Wright's Media as NYT's authorized licensing
partner and offers editorial-republishing/academic permissions. The request
should state the finite article list or date/topic window, research purpose,
whether any model-assisted analysis occurs, named users, storage location and
retention/deletion plan, whether machine-readable delivery or text-and-data
mining is required, and that the dataset will not be redistributed. Obtain
explicit language covering: full text, automated delivery/retrieval, local
storage, the intended analysis (including any AI use), and any publication of
excerpts/derived dataset.

An institutional or personal reading subscription may provide article access;
whether it supports research collection depends on its applicable terms. The
operational blocker in this project is narrower: no usable full-text source has
yet been captured. Likewise, a 403/challenge page is an access-control outcome,
not a reason to seek a mirror, proxy, cache, or another bypass.

## Minimal-cost next actions

1. Keep the already-held newsletters as the only retained NYT full-text
   evidence and label all linked articles as unavailable until rights are
   obtained.
2. If article selection/coverage work is useful before licensing, have an
   authorized project owner create one developer API application/key and make
   a low-rate metadata-only registry. Preserve raw JSON, retrieval time,
   endpoint, query parameters, API documentation version, and response hash.
   Do not send the key to this repository or a manifest.
3. Identify a legitimate full-text route and review the terms that govern that
   route. A direct NYT rights request can define a bounded research corpus and
   permitted delivery channel. Until such a route supplies usable text, redesign
   the study around newsletter text and metadata rather than inflating metadata
   records into article counts.

## Source scope and limits

Only official NYT developer documentation/specifications, NYT's Help Center
terms, and the NYT-linked authorized licensing portal were consulted. No NYT
article URL was retried, and no proxy, cache, mirror, account, API key, paid
service, or licence was created. This note is operational guidance based on
the published terms, not legal advice; the controlling permission is the
written licence/authorization NYT supplies for the actual corpus and use.
