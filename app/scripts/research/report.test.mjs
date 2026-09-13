import test from "node:test";
import assert from "node:assert/strict";
import { mkdtempSync, readFileSync, rmSync, statSync } from "node:fs";
import { join } from "node:path";
import { tmpdir } from "node:os";
import { DatabaseSync } from "node:sqlite";
import { MailStore, marketSearchTerms } from "./store.mjs";
import { writeResearchReport } from "./report.mjs";

test("populated reports stream rows, preserve evidence flags, and roll back interrupted runs", () => {
  const dir = mkdtempSync(join(tmpdir(), "mop-streamed-review-"));
  const store = new MailStore(dir);
  try {
    const reader = new DatabaseSync(join(dir, "mail.sqlite"));
    try {
      reader.exec("BEGIN");
      assert.equal(reader.prepare("SELECT count(*) n FROM settings").get().n, 0);
      store.setSetting("concurrent-import", "written");
      assert.equal(reader.prepare("SELECT count(*) n FROM settings").get().n, 0);
      reader.exec("COMMIT");
      assert.equal(reader.prepare("SELECT count(*) n FROM settings").get().n, 1);
    } finally { reader.close(); }
    const meta = { receivedAt: "2026-09-08T10:00:00Z", signatures: [{ result: "pass", bodyLengthLimited: false }],
      proof: { headerCandidate: true, signedAt: "2026-09-08T09:59:00Z", subject: "Fed rate decision", domain: "example.org" } };
    store.db.prepare("INSERT INTO messages VALUES (?,?,?,?)").run("email-1", "Fed rate decision", "Fed ".repeat(25000), JSON.stringify(meta));
    store.db.prepare("INSERT INTO search VALUES (?,?,?)").run("email-1", "Fed rate decision", "Fed ".repeat(25000));
    assert.equal(store.search(["fed"]).emails[0].body.length, 100000);
    assert.equal("body" in store.search(["fed"], 20, { metadataOnly: true }).emails[0], false);
    const m = id => ({ id, question: "Fed rate decision in September 2026?", description: "Original rules", outcome: "Yes", closedAt: "2026-09-08T12:00:00Z" });
    let searches = 0;
    const search = store.search.bind(store);
    store.search = (...args) => { searches++; return search(...args); };
    const dataset = { since: "2026-08-26T00:00:00Z", fetchedAt: "2026-09-09T00:00:00Z", coverage: { paginationComplete: true },
      markets: (function*() { for (let i = 0; i < 3; i++) yield { ...m(String(i)),
        ...(i === 2 ? { closedAt: "2026-09-08T09:00:00Z" } : {}) }; })() };
    const { overview, reportPath } = writeResearchReport({ store, dataset, mailStatus: { status: "complete" } });
    const content = readFileSync(reportPath, "utf8"), report = JSON.parse(content);
    assert.equal(overview.summary.markets, 3);
    assert.equal(overview.summary.pending, 3);
    assert.equal(overview.summary.semanticReviewComplete, false);
    assert.equal(searches, 1); // same terms reuse retrieval within this corpus snapshot
    assert.equal(report.markets[2].candidates[0].knownBeforeClosure, false);
    assert.equal(report.markets[2].candidates[0].rsaSubjectCandidate, false);
    assert.deepEqual(report.markets[0].candidates[0], { emailId: "email-1", score: report.markets[0].candidates[0].score,
      rsaSubjectCandidate: true, fullBodyDkimVerified: true, knownBeforeClosure: true });
    assert.equal(content.includes("Fed ".repeat(10)), false);
    assert.equal(statSync(reportPath).mode & 0o077, 0);
    assert.equal(statSync(reportPath).ino, statSync(join(dir, "report-latest.json")).ino);
    const previousRow = store.researchMarket("0");
    assert.throws(() => writeResearchReport({ store, dataset: { ...dataset, markets: [m("replacement"), m("failure")] },
      mailStatus: { status: "complete" }, beforeRow: row => { if (row.id === "failure") throw new Error("Interrupted"); } }), /Interrupted/);
    assert.deepEqual(store.researchMarket("0"), previousRow);
    assert.equal(store.researchMarket("replacement"), null);
    assert.equal(readFileSync(join(dir, "report-latest.json"), "utf8"), content);
    assert.equal(searches, 2); // a new report must not reuse the previous snapshot's cache
    assert.deepEqual(marketSearchTerms("Will Ed Markey win the Massachusetts primary in September 2026?"), ["markey", "massachusetts", "primary"]);
  } finally { store.close(); rmSync(dir, { recursive: true }); }
});
