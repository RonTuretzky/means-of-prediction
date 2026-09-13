const ENDPOINT = "https://gamma-api.polymarket.com/markets/keyset";

export function parseTimestamp(value) {
  if (!value) return NaN;
  return Date.parse(String(value).replace(" ", "T").replace(/\+00$/, "Z"));
}
function array(value) { try { return typeof value === "string" ? JSON.parse(value) : value; } catch { return null; } }

export function resolvedMarket(m, since, now) {
  if (!/^\d+$/.test(String(m.id))) return null;
  const closedAt = parseTimestamp(m.closedTime);
  if (!m.closed || !Number.isFinite(closedAt) || closedAt < since || closedAt > now) return null;
  // A market being closed is not sufficient: require a final resolution marker and payout vector.
  if (m.umaResolutionStatus !== "resolved" && m.automaticallyResolved !== true) return null;
  const outcomes = array(m.outcomes), prices = array(m.outcomePrices)?.map(Number);
  if (!Array.isArray(outcomes) || !Array.isArray(prices) || outcomes.length !== prices.length) return null;
  const winners = prices.flatMap((p, i) => p === 1 ? [i] : []);
  if (winners.length !== 1 || prices.some(p => p !== 0 && p !== 1)) return null;
  return { id: String(m.id), question: m.question, description: m.description || "", slug: m.slug,
    url: `https://polymarket.com/event/${m.events?.[0]?.slug || m.slug}`,
    resolutionSource: m.resolutionSource || "", outcomes, outcome: outcomes[winners[0]],
    closedAt: new Date(closedAt).toISOString(), endDate: m.endDate || null,
    createdAt: m.createdAt || null, volume: Number(m.volumeNum ?? m.volume ?? 0),
    timeBasis: "Gamma closedTime (closure timestamp, not independently verified onchain resolution time)" };
}

export async function fetchResolvedMarkets({ now = Date.now(), days = 14, fetcher = fetch, onPage = () => {},
  delay = ms => new Promise(r => setTimeout(r, ms)) } = {}) {
  const since = now - days * 86_400_000;
  const markets = new Map(), seen = new Set();
  const excluded = { missingCloseTime: 0, notFinalOrNonBinaryPayout: 0, outsideWindow: 0 };
  let pages = 0, scanned = 0, previousTime = Infinity, cursor = null;
  const cursors = new Set();
  for (;;) {
    const url = `${ENDPOINT}?closed=true&order=closedTime&ascending=false&limit=100` +
      (cursor ? `&after_cursor=${encodeURIComponent(cursor)}` : "");
    let response, payload;
    for (let retry = 0; retry < 4; retry++) {
      try {
        response = await fetcher(url, { signal: AbortSignal.timeout(60_000) });
        if (response.ok) { payload = await response.json(); break; }
        if (response.status !== 429 && response.status < 500) break;
      } catch (error) {
        // A timeout can occur while opening the response or reading its body.
        // Retry the same cursor; never advance or label a partial page complete.
        if (retry === 3 || !["TimeoutError", "AbortError", "TypeError"].includes(error?.name)) throw error;
      }
      if (retry < 3) await delay(1000 * 2 ** retry);
    }
    if (!response.ok) throw new Error(`Polymarket request failed (${response.status}); coverage is incomplete`);
    const page = payload.markets;
    if (!Array.isArray(page)) throw new Error("Unexpected Polymarket response");
    pages++;
    if (!page.length) break;
    let fresh = 0, crossedCutoff = false;
    for (const m of page) {
      if (seen.has(String(m.id))) continue;
      seen.add(String(m.id)); fresh++; scanned++;
      const time = parseTimestamp(m.closedTime);
      if (!Number.isFinite(time)) { excluded.missingCloseTime++; continue; }
      if (time > previousTime) throw new Error("Polymarket ordering changed during scan; retry before claiming full coverage");
      previousTime = time;
      if (time < since) crossedCutoff = true;
      const normalized = resolvedMarket(m, since, now);
      if (normalized) markets.set(normalized.id, normalized);
      else if (time < since || time > now) excluded.outsideWindow++;
      else excluded.notFinalOrNonBinaryPayout++;
    }
    onPage({ pages, scanned, matched: markets.size,
      oldestClosedAt: Number.isFinite(previousTime) ? new Date(previousTime).toISOString() : null });
    if (!fresh) throw new Error("Polymarket repeated a page; refusing a truncated report");
    if (crossedCutoff) break;
    if (!payload.next_cursor) break;
    if (cursors.has(payload.next_cursor)) throw new Error("Polymarket repeated its cursor; coverage incomplete");
    cursor = payload.next_cursor; cursors.add(cursor);
  }
  return { fetchedAt: new Date(now).toISOString(), since: new Date(since).toISOString(),
    coverage: { pages, scanned, excluded, paginationComplete: true,
      limitation: "Uses Gamma closedTime as a resolution-time proxy; missing timestamps, nonfinal and split/void payouts are excluded and counted." },
    markets: [...markets.values()] };
}
