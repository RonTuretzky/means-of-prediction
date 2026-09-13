#!/usr/bin/env node
import { readFileSync } from "node:fs";
import { join } from "node:path";
import { MailStore, DEFAULT_DATA_DIR, privateJson, searchTerms, marketFingerprint } from "./store.mjs";

// Assistant review interface. Outputs private mail to the current task, never to public CI.
if (process.env.GITHUB_ACTIONS) throw new Error("Private email inspection cannot run in public CI");
const [command, value, ...rest] = process.argv.slice(2);
const dir = process.env.MOP_DATA_DIR || DEFAULT_DATA_DIR;
const store = new MailStore(dir);
try {
  if (command === "email") console.log(JSON.stringify(store.get(value), null, 2));
  else if (command === "search") console.log(JSON.stringify(store.search(searchTerms(value), Number(rest[0] || 100)), null, 2));
  else if (command === "market") {
    console.log(JSON.stringify(store.researchMarket(value), null, 2));
  } else if (command === "review") {
    const review = JSON.parse(readFileSync(value, "utf8"));
    const market = store.researchMarket(review.marketId);
    if (!market) throw new Error("Unknown market ID");
    if (!["subject_evidence", "body_evidence_only", "insufficient_evidence", "different_resolution_rules", "unverifiable"].includes(review.classification)) throw new Error("Unknown review classification");
    if (!review.reason || !review.ruleAnalysis || !review.outcome) throw new Error("Review needs reason, ruleAnalysis and outcome");
    if (review.outcome !== market.outcome) throw new Error("Review outcome must agree with the resolved payout");
    if (["subject_evidence", "body_evidence_only"].includes(review.classification)) {
      if (!review.evidence?.length) throw new Error("Positive findings need exact email evidence");
      for (const e of review.evidence) {
        const email = store.get(e.emailId);
        const content = e.field === "subject" ? email?.proof?.subject : e.field === "body" ? email?.body : null;
        if (!e.quote || !content?.includes(e.quote)) throw new Error("Evidence quote is absent from the selected email field");
        if (!email.receivedAt || Date.parse(email.receivedAt) > Date.parse(market.closedAt)) throw new Error("Email was not known to be received before closure");
        if (review.classification === "subject_evidence" && (e.field !== "subject" || !email.proof?.headerCandidate ||
          !email.proof.signedAt || Date.parse(email.proof.signedAt) > Date.parse(market.closedAt))) throw new Error("Signed subject evidence is unsupported");
        if (e.field === "body" && !email.signatures.some(s => s.result === "pass" && !s.bodyLengthLimited)) throw new Error("Body DKIM is not fully verified");
      }
    }
    review.reviewedAt = new Date().toISOString();
    review.marketFingerprint = marketFingerprint(market);
    review.indexedMessagesAtReview = store.count();
    review.onchainVerified = false;
    review.note = "Semantic retrospective assessment; not an onchain checkProof result. Subject candidates still require trusted key registration and contract validation.";
    privateJson(join(dir, "reports", `review-${market.id}.json`), review);
    console.log(`Saved private assessment for market ${market.id}`);
  } else throw new Error("Usage: inspect.mjs email ID | market ID | search 'terms' [limit] | review /path/to/review.json");
} finally { store.close(); }
