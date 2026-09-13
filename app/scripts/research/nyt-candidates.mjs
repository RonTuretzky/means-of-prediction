#!/usr/bin/env node
// Exhaustive lexical scan, followed by human/assistant rule review. Its scores
// and candidate counts are NOT settlement-coverage percentages.
import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";
import { DatabaseSync } from "node:sqlite";
import { DEFAULT_DATA_DIR, privateJson } from "./store.mjs";
import { resolvedMarket, parseTimestamp } from "./polymarket.mjs";

const root = process.env.MOP_DATA_DIR || DEFAULT_DATA_DIR;
const dir = process.env.MOP_NYT_DATA_DIR || join(root, "nyt");
const cache = join(root, "polymarket-pages");
const manifest = JSON.parse(readFileSync(join(cache, "manifest.json"), "utf8"));
const paginationComplete = manifest.publicPaginationComplete === true || manifest.complete === true;
const since = manifest.now - manifest.days * 86400000;
const mailCoverage = JSON.parse(readFileSync(join(dir, "mailbox-coverage.json"), "utf8"));
const db = new DatabaseSync(join(dir, "mail.sqlite"));
const emails = db.prepare("SELECT * FROM messages ORDER BY json_extract(metadata,'$.receivedAt')").all().map((e,i) => ({
  ...e, ...JSON.parse(e.metadata), n:i+1,
  text: e.body.replace(/https?:\/\/\S+/g, "").replace(/^\s*\[\s*$/gm, "").split(/\nNeed help\?|\nYou received this email because/)[0].replace(/\n{3,}/g,"\n\n"),
}));
const stop = new Set("will would could should shall the a an is are was were be been being has have had do does did of on in at by for to from and or but this that these those with as it its before after between than more less above below over under yes no market markets resolves resolve resolution price end date time et utc any if not which whether according following during until into win wins winner winning finish finishes week month year another new next reach hit high low close closes opening closing september august july june january february march april may october november december monday tuesday wednesday thursday friday saturday sunday exact score other total team first second third half halftime inning innings quarter overtime round rounds map maps spread points sets games game match matches at least percent margin million billion highest lowest higher lower season 2026 2027".split(" "));
const normalize = text => text.toLowerCase().replace(/sachsen/g,"saxony").replace(/alternative for germany/g,"afd").replace(/\b(?:[a-z]\.){2,}/g, s => s.replaceAll(".",""));
const terms = text => [...new Set((normalize(text).match(/[\p{L}]+/gu)||[]).filter(w => w.length>=3&&!stop.has(w)))];
const inverted = new Map();
for (const e of emails) for (const word of terms(e.subject+" "+e.text)) {
  if(!inverted.has(word)) inverted.set(word,new Set());
  inverted.get(word).add(e.n);
}
const emailByNumber = new Map(emails.map(e=>[e.n,e]));
// Private readable corpus for the assistant's review. Preserve raw .eml files
// separately; this URL/footer-stripped rendering is not cryptographic evidence.
privateJson(join(dir, "emails-clean.json"), emails.map(e => Object.fromEntries(
  ["n", "id", "subject", "text", "from", "receivedAt", "date", "signatures", "proof", "attachmentCount", "attachmentTextIndexed"]
    .filter(k => k in e).map(k => [k, e[k]])
)));
db.exec("CREATE TABLE IF NOT EXISTS coverage_markets(id TEXT PRIMARY KEY,payload TEXT,candidate REAL);");
const insert=db.prepare("INSERT INTO coverage_markets VALUES(?,?,?)");
const seen=new Set(), candidates=[];
const counts={scanned:0,finalBinary:0,finalNonBinaryOrInvalid:0,notFinal:0,outsideWindow:0,missingTime:0,lexicalCandidates:0};
db.exec("BEGIN");
try {
  db.exec("DELETE FROM coverage_markets");
  for(const file of readdirSync(cache).filter(f=>f!=="manifest.json"&&f.endsWith(".json"))) {
    for(const raw of JSON.parse(readFileSync(join(cache,file),"utf8")).markets) {
      if(seen.has(String(raw.id))) continue;seen.add(String(raw.id));counts.scanned++;
      const at=parseTimestamp(raw.closedTime);
      if(!Number.isFinite(at)){counts.missingTime++;continue;}
      if(at<since||at>manifest.now){counts.outsideWindow++;continue;}
      if(raw.umaResolutionStatus!=="resolved"&&raw.automaticallyResolved!==true){counts.notFinal++;continue;}
      const market=resolvedMarket(raw,since,manifest.now);
      if(!market){counts.finalNonBinaryOrInvalid++;continue;}
      counts.finalBinary++;
      const qt=terms(market.question), hits=new Map();let possible=0;
      for(const word of qt){
        const matches=inverted.get(word), weight=1+Math.log((emails.length+1)/((matches?.size||0)+1));possible+=weight;
        if(!matches)continue;
        for(const number of matches){if(!hits.has(number))hits.set(number,{number,score:0,words:[]});const h=hits.get(number);h.score+=weight;h.words.push(word);}
      }
      const ranked=[...hits.values()].map(h=>({...h,coverage:h.score/possible})).filter(h=>h.coverage>=0.45 && h.words.length>=Math.min(2,qt.length)).sort((a,b)=>b.coverage-a.coverage||b.score-a.score).slice(0,8);
      const best=ranked[0]?.coverage||0;
      insert.run(market.id,JSON.stringify(market),best);
      if(ranked.length){counts.lexicalCandidates++;candidates.push({id:market.id,question:market.question,outcome:market.outcome,closedAt:market.closedAt,terms:qt,
        matches:ranked.map(h=>({emailNumber:h.number,emailId:emailByNumber.get(h.number).id,coverage:h.coverage,matchedWords:h.words,subject:emailByNumber.get(h.number).subject}))});}
    }
  }
  db.exec("COMMIT");
}catch(e){db.exec("ROLLBACK");throw e;}finally{db.close();}
candidates.sort((a,b)=>b.matches[0].coverage-a.matches[0].coverage||Number(a.id)-Number(b.id));
privateJson(join(dir,"candidate-audit.json"),{generatedAt:new Date().toISOString(),windowStart:new Date(since).toISOString(),windowEnd:new Date(manifest.now).toISOString(),paginationComplete,mailCoverage,counts,semanticReviewComplete:false,markets:candidates});
console.log(JSON.stringify({paginationComplete,...counts}));
