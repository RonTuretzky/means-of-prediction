import { useRef, useState } from "react";
import { Link } from "react-router-dom";
import { ArrowLeft, ArrowRight, ArrowSquareOut, Check, CheckCircle, Clock, Copy, FileText, Info, SealCheck } from "@phosphor-icons/react";
import { PEACE_DEMO as demo } from "../data/peace-demo";

const TABS = ["Overview", "Evidence", "Rules", "Verification"] as const;
type Tab = (typeof TABS)[number];
const date = (value: string) => new Date(value).toLocaleString("en-US", { month: "short", day: "numeric", year: "numeric", hour: "2-digit", minute: "2-digit", second: "2-digit", timeZone: "UTC" }) + " UTC";

function OutLink({ href, children }: { href: string; children: React.ReactNode }) {
  return <a href={href} target="_blank" rel="noopener noreferrer" className="mp-text-link">{children}<ArrowSquareOut size={14} aria-hidden="true" /><span className="sr-only"> (opens a new tab)</span></a>;
}

function Evidence({ compact = false }: { compact?: boolean }) {
  return <div className="mp-evidence-list">{demo.sources.map(source => <article className="mp-source-card" key={source.id}>
    <div className="mp-source-top"><div className="mp-source-name"><span className="mp-source-mark">{source.mark}</span><div><strong>{source.name}</strong><span>{source.domain}</span></div></div><span className="mp-small-label"><CheckCircle size={14} aria-hidden="true" /> Supports YES in replay</span></div>
    <blockquote>“{source.excerpt}”</blockquote>
    {!compact && <>
      <p className="mp-score-note">Integer model scores · not market odds</p>
      <div className="mp-score-row"><span>Support</span><div className="mp-score-track" aria-hidden="true"><i style={{ width: `${source.support}%` }} /></div><strong>{source.support.toFixed(2)}%</strong></div>
      <div className="mp-score-row mp-score-counter"><span>Counter</span><div className="mp-score-track" aria-hidden="true"><i style={{ width: `${source.counter}%` }} /></div><strong>{source.counter.toFixed(2)}%</strong></div>
      <dl className="mp-source-dates"><div><dt>Google signed at</dt><dd><time dateTime={source.signedAt}>{date(source.signedAt)}</time></dd></div><div><dt>DKIM expired</dt><dd><time dateTime={source.expiresAt}>{date(source.expiresAt)}</time></dd></div></dl>
    </>}
    <OutLink href={source.url}>View source</OutLink>
  </article>)}</div>;
}

export function PeaceDemoPage() {
  const [tab, setTab] = useState<Tab>("Overview");
  const [copyStatus, setCopyStatus] = useState("");
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);
  const tabList = useRef<HTMLDivElement | null>(null);
  const showTab = (next: Tab) => {
    setTab(next);
    requestAnimationFrame(() => tabList.current?.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth", block: "start" }));
  };
  const copyHash = async () => {
    try { await navigator.clipboard.writeText(demo.localTransaction); setCopyStatus("Transaction hash copied"); }
    catch { setCopyStatus("Copy unavailable. Select the transaction hash below."); }
  };

  return <div className="mp-product mp-shell mp-replay-page">
    <Link to="/markets" className="mp-back"><ArrowLeft size={16} aria-hidden="true" /> Explore markets</Link>
    <div className="mp-market-heading">
      <div className="mp-award-mark" aria-hidden="true">N<span>2026</span></div>
      <div><div className="mp-kicker"><span>World affairs</span><span className="mp-dot" /><span>Nobel Prize</span></div><h1>{demo.question}</h1><p>Historical local replay · Polymarket reference #{demo.marketId}</p></div>
    </div>
    <div className="mp-replay-notice"><Info size={18} aria-hidden="true" /><p>This is a recorded replay from <strong>October 21, 2026</strong>. It is not a live market or a public-chain settlement.</p></div>

    <div className="mp-market-layout">
      <div className="mp-market-main">
        <div className="mp-tabs" ref={tabList} role="tablist" aria-label="Replay details">
          {TABS.map((name, index) => <button key={name} ref={el => { tabRefs.current[index] = el; }} role="tab" id={`peace-tab-${name}`} aria-controls={`peace-panel-${name}`} aria-selected={tab === name} tabIndex={tab === name ? 0 : -1} className={tab === name ? "active" : ""} onClick={() => setTab(name)} onKeyDown={event => {
            const next = event.key === "ArrowRight" ? (index + 1) % TABS.length : event.key === "ArrowLeft" ? (index + TABS.length - 1) % TABS.length : event.key === "Home" ? 0 : event.key === "End" ? TABS.length - 1 : -1;
            if (next >= 0) { event.preventDefault(); setTab(TABS[next]); tabRefs.current[next]?.focus(); }
          }}>{name}{name === "Evidence" && <span className="mp-tab-count">4</span>}</button>)}
        </div>
        <section className="mp-tab-panel" role="tabpanel" id={`peace-panel-${tab}`} aria-labelledby={`peace-tab-${tab}`} tabIndex={0}>
          {tab === "Overview" && <>
            <div className="mp-result-summary"><span className="mp-check-badge"><Check size={23} weight="bold" aria-hidden="true" /></span><div><p className="mp-eyebrow">Recorded outcome</p><h2>Four reports. One supported outcome.</h2><p>The historical judge run found that the reports supported an individual laureate: <strong>{demo.reportedLaureate}</strong>.</p></div></div>
            <div className="mp-section-heading"><h3>Why the replay resolved YES</h3><button className="mp-text-link" onClick={() => showTab("Rules")}>Read the rules <ArrowRight size={14} aria-hidden="true" /></button></div>
            <div className="mp-predicate-grid">{demo.predicates.map(predicate => <div className="mp-predicate" key={predicate.title}><CheckCircle size={19} aria-hidden="true" /><div><strong>{predicate.title}</strong><p>{predicate.detail}</p></div></div>)}</div>
            <div className="mp-section-heading"><h3>The evidence at a glance</h3><button className="mp-text-link" onClick={() => showTab("Evidence")}>Inspect all evidence <ArrowRight size={14} aria-hidden="true" /></button></div>
            <div className="mp-source-strip">{demo.sources.map(source => <button key={source.id} onClick={() => showTab("Evidence")} aria-label={`Inspect ${source.name} evidence`}><span className="mp-source-mark">{source.mark}</span><span>{source.name}</span><CheckCircle size={16} aria-hidden="true" /></button>)}</div>
            <div className="mp-section-heading"><h3>From report to recorded result</h3></div>
            <ol className="mp-timeline">
              <li><span className="mp-timeline-node"><FileText size={16} aria-hidden="true" /></span><div><strong>Reports delivered</strong><p>Four source snippets arrived in signed Google Alerts, October 14–18.</p></div></li>
              <li><span className="mp-timeline-node"><SealCheck size={16} aria-hidden="true" /></span><div><strong>Evidence and rules checked</strong><p>The replay used imported Polymarket rules and a source policy frozen on October 21, after the emails.</p></div></li>
              <li><span className="mp-timeline-node"><Check size={16} aria-hidden="true" /></span><div><strong>Local replay accepted YES</strong><p>{date(demo.replayedAt)} · four observations accepted.</p></div></li>
              <li className="pending"><span className="mp-timeline-node"><Clock size={16} aria-hidden="true" /></span><div><strong>Public full-market settlement remains unfinished</strong><p>The separate Sepolia computation demo is a smaller component. <Link to="/demos" className="mp-inline-link">View that receipt →</Link></p></div></li>
            </ol>
          </>}
          {tab === "Evidence" && <>
            <div className="mp-section-heading"><div><h2>Four reporting sources</h2><p>Short excerpts from the audited Google Alert result blocks.</p></div></div>
            <div className="mp-info-box"><Info size={18} aria-hidden="true" /><p>Google’s signature authenticates the email bytes, not the publisher’s truth. All four DKIM signatures were valid at the historical replay time and have since expired. A DKIM signing time is not an event, publication or first-receipt date.</p></div>
            <Evidence />
          </>}
          {tab === "Rules" && <>
            <p className="mp-eyebrow">Rule provenance</p><h2>Imported from Polymarket</h2><p className="mp-leading">These historical rules were not generated by AI. The replay evaluated the referenced market’s criteria.</p>
            <div className="mp-rule-block"><span className="mp-outcome-label">YES</span><p>The 2026 Nobel Peace Prize is awarded to a named individual. Shared, declined and posthumous awards count; an individual acting only as an organization’s representative does not.</p></div>
            <div className="mp-rule-block"><span className="mp-outcome-label neutral">NO</span><p>Otherwise, including a withheld award or no announcement by December 31, 2026, at 11:59 PM ET.</p></div>
            <h3 className="mp-subheading">Resolution sources</h3><p className="mp-leading">The first official Norwegian Nobel Committee announcement is the primary source. Credible reporting consensus is a fallback. The original rule does not require an arbitrary four-source threshold.</p>
            <OutLink href={demo.rulesUrl}>Open the original market rules</OutLink>
            <div className="mp-info-box mp-margin-top"><Info size={18} aria-hidden="true" /><p>The source policy was fixed after the signed emails, so this is retrospective. Independent timestamps for the official announcement and original market close were not established; the replay does not prove that evidence arrived before that close.</p></div>
            <details className="mp-details"><summary>Rule commitment</summary><code>{demo.ruleHash}</code></details>
            <div className="mp-inline-cta"><div><strong>Have a different question?</strong><p>Draft new rules with DeepSeek inside the product, then review them.</p></div><Link className="mp-button secondary" to="/create/ai">Draft rules <ArrowRight size={16} aria-hidden="true" /></Link></div>
          </>}
          {tab === "Verification" && <>
            <h2>What was actually verified</h2><p className="mp-leading">A historical local replay. The records below do not describe a public-network market transaction.</p>
            <dl className="mp-verification-grid"><div><dt>Replay time</dt><dd>{date(demo.replayedAt)}</dd></div><div><dt>Execution network</dt><dd>Local chain · {demo.chainId}</dd></div><div><dt>Receipt</dt><dd>Success · block {demo.block}</dd></div><div><dt>Accepted evidence</dt><dd>4 observations · replay identifiers consumed</dd></div><div><dt>Local gas used</dt><dd>{demo.gasUsed.toLocaleString()}</dd></div><div><dt>Execution limits</dt><dd>Relaxed local gas and code limits</dd></div></dl>
            <h3 className="mp-subheading">Local transaction</h3><div className="mp-hash-row"><code>{demo.localTransaction}</code><button onClick={copyHash} className="mp-icon-button" aria-label="Copy local transaction hash"><Copy size={18} /></button></div><p className="mp-caption" role="status">{copyStatus || "Local chain 31337 — there is no public Etherscan receipt for this transaction."}</p>
            <h3 className="mp-subheading">Judge execution</h3><p className="mp-leading">The complete 28-layer encoder and two-layer head ran on CPU. Three local operators supplied certificates. This was not full-model execution in the EVM.</p><details className="mp-details"><summary>Model identifier</summary><code>{demo.model}</code></details>
            <div className="mp-info-box mp-margin-top"><Info size={18} aria-hidden="true" /><p>An operator certificate attests to execution. It is not proof that a news claim is true. DKIM expiry, retrospective policy selection, and missing original-close timestamps limit this replay.</p></div>
            <Link to="/demos" className="mp-component-link"><span><strong>Separate public Sepolia component</strong><small>Inspect the Laya × GasKiller arithmetic receipt.</small></span><ArrowRight size={20} aria-hidden="true" /></Link>
          </>}
        </section>
      </div>

      <aside className="mp-resolution-sidebar" aria-label="Recorded market outcome">
        <div className="mp-resolution-card"><p className="mp-eyebrow">Final result · local replay</p><div className="mp-final-result"><CheckCircle size={34} weight="fill" aria-hidden="true" /><strong>YES</strong></div><h2>An individual laureate</h2><p>Recorded outcome from the October 21 replay.</p><div className="mp-sidebar-facts"><span>Evidence reviewed<strong>4 sources</strong></span><span>Rules origin<strong>Polymarket</strong></span><span>Public market settlement<strong>Not completed</strong></span></div><button className="mp-button full" onClick={() => showTab("Evidence")}>Inspect the evidence <ArrowRight size={16} aria-hidden="true" /></button><p className="mp-caption">This replay has no trading or redemption controls. Model scores are not market prices.</p></div>
        <div className="mp-sidebar-note"><p className="mp-eyebrow">Build your own question</p><h3>Start with rules people can read.</h3><Link to="/create/ai" className="mp-text-link">Draft with DeepSeek <ArrowRight size={15} aria-hidden="true" /></Link></div>
      </aside>
    </div>
  </div>;
}
