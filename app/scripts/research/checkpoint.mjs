import { existsSync, mkdirSync, readFileSync, rmSync } from "node:fs";
import { join } from "node:path";
import { digest, privateJson } from "./store.mjs";

// Cache each successful page before advancing its opaque cursor. This keeps a
// long backfill recoverable after network, process, or report-writing failures.
export function marketCheckpoint(dataDir, { now = Date.now(), days = 14, fetcher = fetch } = {}) {
  const dir = join(dataDir, "polymarket-pages");
  const manifestPath = join(dir, "manifest.json");
  let manifest = existsSync(manifestPath) ? JSON.parse(readFileSync(manifestPath, "utf8")) : null;
  if (!manifest || manifest.complete || manifest.days !== days || now - manifest.now > 6 * 3600000) {
    rmSync(dir, { recursive: true, force: true });
    mkdirSync(dir, { recursive: true, mode: 0o700 });
    manifest = { now, days, complete: false };
    privateJson(manifestPath, manifest);
  }
  return {
    now: manifest.now,
    fetched() { manifest = { ...manifest, publicPaginationComplete: true }; privateJson(manifestPath, manifest); },
    complete() { privateJson(manifestPath, { ...manifest, complete: true }); },
    async fetcher(url, options) {
      const path = join(dir, `${digest(url)}.json`);
      if (existsSync(path)) return { ok: true, status: 200, json: async () => JSON.parse(readFileSync(path, "utf8")) };
      const response = await fetcher(url, options);
      if (!response.ok) return response;
      return { ok: true, status: response.status, json: async () => {
        const payload = await response.json();
        if (!Array.isArray(payload.markets)) throw new Error("Unexpected Polymarket page; checkpoint not saved");
        // Retain every field used by resolution analysis, not duplicate media,
        // orderbook and embedded event payloads from the API.
        const fields = ["id", "question", "description", "slug", "resolutionSource", "outcomes", "outcomePrices",
          "closed", "closedTime", "umaResolutionStatus", "automaticallyResolved", "endDate", "createdAt", "volumeNum", "volume"];
        const page = { next_cursor: payload.next_cursor, markets: payload.markets.map(m => ({
          ...Object.fromEntries(fields.filter(k => k in m).map(k => [k, m[k]])),
          events: m.events?.slice(0, 1).map(e => ({ slug: e.slug })),
        })) };
        privateJson(path, page);
        return page;
      } };
    },
  };
}
