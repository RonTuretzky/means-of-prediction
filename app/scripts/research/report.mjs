import { existsSync, readFileSync, openSync, writeSync, closeSync, renameSync, rmSync, linkSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { marketSearchTerms, marketFingerprint, evidenceCandidate, privateJson } from "./store.mjs";

// A populated mailbox can produce millions of candidates. Keep one enriched
// market in memory, write its durable row, then release it before the next query.
export function writeResearchReport({ store, dataset, mailStatus, onProgress = () => {}, beforeRow = () => {} }) {
  const indexedCount = store.count();
  const generatedAt = new Date().toISOString();
  const reportPath = join(store.dir, "reports", `${generatedAt.slice(0, 10)}.json`);
  const temporary = `${reportPath}.${process.pid}.tmp`;
  const latestTemporary = join(store.dir, `report-latest.${process.pid}.tmp`);
  const summary = { markets: 0, marketsWithCandidates: 0, reviewed: 0, pending: 0,
    subjectEvidence: 0, bodyEvidenceOnly: 0, confirmedOnchain: 0, semanticReviewComplete: false };
  // Repeated intraday contracts often have identical retrieval terms. The
  // corpus is fixed within this transaction; reuse retrieval, but recompute
  // timing and signature eligibility for each individual market below.
  const searchCache = new Map();
  let fd = openSync(temporary, "w", 0o600), transaction = false;
  try {
    store.db.exec("BEGIN"); transaction = true;
    store.db.exec("DELETE FROM research_markets");
    const insert = store.db.prepare("INSERT INTO research_markets VALUES (?,?)");
    writeSync(fd, '{"markets":[\n');
    for (const market of dataset.markets) {
      beforeRow(market);
      const terms = marketSearchTerms(market.question);
      const searchKey = JSON.stringify(terms);
      let matches = searchCache.get(searchKey);
      if (!matches) {
        matches = store.search(terms, 20, { metadataOnly: true });
        if (searchCache.size >= 512) searchCache.delete(searchCache.keys().next().value);
        searchCache.set(searchKey, matches);
      }
      const reviewPath = join(store.dir, "reports", `review-${market.id}.json`);
      let review = existsSync(reviewPath) ? JSON.parse(readFileSync(reviewPath, "utf8")) : null;
      if (review?.marketFingerprint !== marketFingerprint(market) || review?.indexedMessagesAtReview !== indexedCount) review = null;
      const row = { ...market, terms, retrievedEmails: matches.total, shownEmails: matches.emails.length, review,
        status: mailStatus.status !== "complete" ? "mailbox_incomplete" : review ? review.classification : matches.total ? "needs_semantic_review" : "no_keyword_candidate",
        candidates: matches.emails.map(email => {
          const candidate = evidenceCandidate(email, market);
          // The email ID joins to the full metadata/body via inspect.mjs email.
          // Do not repeat identical subject/header strings and instructions
          // millions of times inside the public-market comparison file.
          return { emailId: email.id, score: email.score, rsaSubjectCandidate: candidate.rsaSubjectCandidate,
            fullBodyDkimVerified: candidate.fullBodyDkimVerified, knownBeforeClosure: candidate.knownBeforeClosure };
        }) };
      const serialized = JSON.stringify(row);
      insert.run(market.id, serialized);
      writeSync(fd, (summary.markets ? ',\n' : '') + serialized);
      summary.markets++;
      if (matches.total) summary.marketsWithCandidates++;
      if (review) summary.reviewed++; else summary.pending++;
      if (review?.classification === "subject_evidence") summary.subjectEvidence++;
      if (review?.classification === "body_evidence_only") summary.bodyEvidenceOnly++;
      if (summary.markets % 1000 === 0) onProgress({ ...summary });
    }
    summary.semanticReviewComplete = mailStatus.status === "complete" && summary.pending === 0;
    const overview = { generatedAt, since: dataset.since, marketsFetchedAt: dataset.fetchedAt,
      marketCoverage: dataset.coverage, mailbox: mailStatus, summary,
      limitations: ["All indexed subject/body text is searchable, but lexical retrieval can miss paraphrases. No keyword candidate does not prove no evidence exists.",
        "Only the top 20 retrieved emails per market are listed. Candidate email IDs join to full metadata/body using inspect.mjs email; use search to inspect remaining matches and expand terms.",
        "Generic years and market-template terms are omitted only from automatic ranking, never from the stored messages or rules.",
        "Gamma closure time is a proxy for settlement time. Source rules and original deadlines must be checked during review.",
        "These are retrospective candidates, not validated new market rules or onchain settlement proofs."] };
    writeSync(fd, '\n],'+JSON.stringify(overview).slice(1)+'\n');
    closeSync(fd); fd = null;
    store.db.exec("COMMIT"); transaction = false;
    renameSync(temporary, reportPath);
    // Two names, one private report inode; replacing latest preserves history.
    linkSync(reportPath, latestTemporary);
    renameSync(latestTemporary, join(store.dir, "report-latest.json"));
    privateJson(join(store.dir, "overview-latest.json"), overview);
    const markdown = `# Email market coverage\n\nGenerated ${generatedAt}. Window begins ${dataset.since}.\n\n`+
      `- Resolved markets: ${summary.markets}\n- Mailbox: ${mailStatus.status}\n- Indexed received emails: ${indexedCount}\n`+
      `- Markets with retrieved candidates: ${summary.marketsWithCandidates}\n- Confirmed settleable: pending semantic review\n\n`+
      overview.limitations.map(s => `- ${s}`).join("\n")+"\n\nPrivate data: keep this report and the email archive outside the public repository.\n";
    writeFileSync(join(store.dir, "report-latest.md"), markdown, { mode: 0o600 });
    return { overview, reportPath };
  } catch (error) {
    if (transaction) store.db.exec("ROLLBACK");
    throw error;
  } finally {
    if (fd !== null) closeSync(fd);
    rmSync(temporary, { force: true });
    rmSync(latestTemporary, { force: true });
  }
}
