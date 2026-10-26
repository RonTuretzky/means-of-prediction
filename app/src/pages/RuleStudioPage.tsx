import { useState } from 'react';
import { Link } from 'react-router-dom';
import { ArrowRight, CheckCircle, DownloadSimple, EnvelopeSimple, LockSimple, Sparkle } from '@phosphor-icons/react';
import { generateRules, readSavedDraft, rulesHash, canonicalJson, type RuleDraft, type RuleGeneration, type FrozenDraft } from '../lib/rule-studio';
import { validateDraft } from '../../../services/rule-generator/src/schema';
import './rule-studio.css';

const API_URL = import.meta.env.VITE_RULE_API_URL || '';
const EXAMPLE = {
  question: 'Will the 2027 Nobel Peace Prize be awarded to at least one individual?',
  context: 'Use the first official Norwegian Nobel Committee announcement at nobelprize.org for the 2027 Nobel Peace Prize. A named individual must be a laureate, not an organization representative. Shared, declined and posthumous awards count. YES requires at least one individual. NO requires a complete official announcement showing only organizations, or an explicit official statement that the prize will not be awarded in 2027. Missing or ambiguous evidence requires abstention.',
};

export function RuleStudioPage() {
  const [question, setQuestion] = useState('');
  const [context, setContext] = useState('');
  const [deadline, setDeadline] = useState('2027-12-31T23:59');
  const [accessCode, setAccessCode] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [generation, setGeneration] = useState<RuleGeneration | null>(null);
  const [draft, setDraft] = useState<RuleDraft | null>(null);
  const [saved, setSaved] = useState<FrozenDraft | null>(readSavedDraft);
  const [reviewed, setReviewed] = useState(false);
  const [editorOpen, setEditorOpen] = useState(false);
  const [jsonEditor, setJsonEditor] = useState('');

  async function generate(event: React.FormEvent) {
    event.preventDefault();
    setBusy(true); setError(''); setNotice(''); setReviewed(false);
    try {
      const result = await generateRules(API_URL, accessCode.trim(), { question: question.trim(), context: context.trim(), deadline: new Date(deadline + ':00Z').toISOString() });
      setGeneration(result); setDraft(result.draft); setEditorOpen(false);
    } catch (e) { setError(e instanceof Error ? e.message : 'Generation failed. Please try again.'); }
    finally { setBusy(false); }
  }

  async function freeze() {
    if (!draft || !generation || !reviewed) return;
    setError('');
    try {
      const plan: FrozenDraft = {
        version: 1, scope: 'local-planning-draft', rules: draft, sha256: await rulesHash(draft),
        frozenAt: new Date().toISOString(), generatorReceipt: generation.receipt,
        editedAfterGeneration: canonicalJson(draft) !== canonicalJson(generation.draft), alertsCreated: false, marketDeployed: false,
      };
      localStorage.setItem('mop-rule-plan-v1', JSON.stringify(plan));
      setSaved(plan); setNotice('Plan saved in this browser. You can download it below.');
    } catch { setError('This browser could not save the plan. Please allow local storage and try again.'); }
  }

  function download() {
    if (!saved) return;
    const url = URL.createObjectURL(new Blob([JSON.stringify(saved, null, 2)], { type: 'application/json' }));
    const a = document.createElement('a'); a.href = url; a.download = 'means-of-prediction-rule-plan.json'; a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }

  function applyEdits() {
    try {
      const next: unknown = JSON.parse(jsonEditor);
      if (!validateDraft(next)) throw new Error();
      setDraft(next); setReviewed(false); setEditorOpen(false); setError('');
    } catch { setError('The edited draft is invalid. Keep the field names, valid source hosts and ISO deadline.'); }
  }

  return <div className="rs-page">
    <div className="rs-breadcrumb"><Link to="/">Means of Prediction</Link><span>/</span><span>Rule studio</span></div>
    <header className="rs-heading"><span className="rs-eyebrow"><Sparkle size={15} weight="fill" /> Powered by DeepSeek</span>
      <h1>Start with a clear question.</h1><p>Turn a market idea into resolution rules and a Google Alerts plan. Review every condition before you use it.</p></header>
    <ol className="rs-steps" aria-label="Market creation progress">
      {['Describe the market', 'Review the rules', 'Save the alert plan'].map((step, i) => <li key={step} aria-current={(saved ? 2 : draft ? 1 : 0) === i ? 'step' : undefined}><span>{i + 1}</span>{step}</li>)}
    </ol>
    <div className="rs-layout">
      <div className="rs-main">
        <section className="rs-card">
          <div className="rs-section-title"><h2>What should the market decide?</h2><button className="rs-text-button" type="button" onClick={() => { setQuestion(EXAMPLE.question); setContext(EXAMPLE.context); }}>Use an example</button></div>
          <form onSubmit={generate}>
            <label className="rs-label" htmlFor="market-question">Market question</label>
            <textarea id="market-question" required minLength={10} maxLength={500} rows={2} placeholder="Will a named event happen before a specific deadline?" value={question} onChange={e => setQuestion(e.target.value)} />
            <label className="rs-label" htmlFor="market-context">Sources and conditions</label>
            <textarea id="market-context" required maxLength={12000} rows={5} placeholder="Which source decides? What exactly counts? Include the complete existing rules if this is based on another market." value={context} onChange={e => setContext(e.target.value)} />
            <label className="rs-label" htmlFor="market-deadline">Resolution deadline (UTC)</label>
            <input id="market-deadline" required type="datetime-local" value={deadline} onChange={e => setDeadline(e.target.value)} />
            <div className="rs-connection"><label className="rs-label" htmlFor="rule-access">Demo access code</label>
              <input id="rule-access" type="password" autoComplete="off" required value={accessCode} onChange={e => setAccessCode(e.target.value)} placeholder="Enter your private demo access code" />
              <p><LockSimple size={13} /> Kept in memory for this page. Your DeepSeek API key stays on the server.</p></div>
            {!API_URL && <p className="rs-message">Rule generation is awaiting its server connection. The resolved demo is available now.</p>}
            <button className="rs-primary" type="submit" disabled={busy || !API_URL}>{busy ? 'DeepSeek is drafting the rules…' : <><Sparkle size={17} /> Generate rules</>}</button>
            <p className="rs-fine">The question and conditions are sent to DeepSeek. Include public market information only.</p>
          </form>
        </section>
        {error && <p role="alert" className="rs-message rs-error">{error}</p>}
        {notice && <p role="status" className="rs-message">{notice}</p>}
        {draft && generation && <section className="rs-card" aria-label="Generated rules">
          <div className="rs-section-title"><h2>Review your rules</h2><button type="button" className="rs-text-button" onClick={() => { setJsonEditor(JSON.stringify(draft, null, 2)); setEditorOpen(!editorOpen); }}>Edit draft</button></div>
          <p className="rs-meta">Generated by {generation.receipt.model} · {new Date(generation.receipt.generatedAt).toLocaleString()}</p>
          {editorOpen ? <div><label className="rs-label" htmlFor="rule-json">Editable rule plan (JSON)</label><textarea id="rule-json" className="rs-json" value={jsonEditor} onChange={e => setJsonEditor(e.target.value)} rows={20} /><button type="button" className="rs-secondary" onClick={applyEdits}>Apply edits</button></div> : <>
            <h3>{draft.question}</h3><p>{draft.eventDefinition}</p>
            <div className="rs-predicates"><RuleList title="Resolves YES when" items={draft.yesConditions} /><RuleList title="Resolves NO when" items={draft.noConditions} /><RuleList title="Wait / abstain when" items={draft.abstainConditions} /></div>
            <RuleList title="Required evidence" items={draft.evidenceRequirements} />
            <h3>Allowed sources</h3><ul className="rs-source-list">{draft.allowedSources.map((s, i) => <li key={i}><strong>{s.name}</strong><span>{s.host} · {s.role}</span></li>)}</ul>
            {draft.allowedSources.length === 0 && <p>No sources selected. Specify authoritative sources before using this plan.</p>}
            <h3>Each alert has a job</h3><div className="rs-alerts">{draft.alertQueries.map((q, i) => <div key={i}><span className="rs-query-number">{i + 1}</span><div><p>{q.job}</p><code>{q.query}</code></div></div>)}</div>
            <details><summary>Instructions for the evidence judge</summary><p>{draft.judgeInstructions}</p></details>
            {draft.warnings.length > 0 && <div className="rs-message"><RuleList title="Before using these rules" items={draft.warnings} /></div>}
            <p className="rs-meta">Deadline: {new Date(draft.deadline).toUTCString()}</p>
            <label className="rs-review"><input type="checkbox" checked={reviewed} onChange={e => setReviewed(e.target.checked)} /> I reviewed the event, source requirements, deadline and abstention rules.</label>
            <button className="rs-primary" type="button" disabled={!reviewed} onClick={freeze}><CheckCircle size={17} /> Save reviewed plan</button>
          </>}
        </section>}
        {saved && <section className="rs-card" aria-label="Saved alert plan">
          <span className="rs-eyebrow">Saved locally · Not deployed</span><h2>{saved.rules.question}</h2>
          <p>Your plan is ready to export. Open each query in Google Alerts, choose your delivery settings, then confirm it is saved in your account.</p>
          <div className="rs-alert-links">{saved.rules.alertQueries.map((q, i) => <a key={i} href={'https://www.google.com/alerts?q=' + encodeURIComponent(q.query)} target="_blank" rel="noreferrer"><EnvelopeSimple size={18} /><span>{q.job}<small>{q.query}</small></span><ArrowRight size={18} /></a>)}</div>
          <p className="rs-fine">Opening a query does not create an alert. No email collection or on-chain market is activated by saving this plan.</p>
          <div className="rs-hash"><span>Rules SHA-256</span><code>{saved.sha256}</code></div>
          <button className="rs-secondary" type="button" onClick={download}><DownloadSimple size={17} /> Download rule plan</button>
        </section>}
      </div>
      <aside className="rs-aside"><section className="rs-card"><h2>From question to outcome</h2><ol className="rs-flow"><li><strong>Write the rules</strong><span>DeepSeek drafts what qualifies as YES, NO or insufficient evidence.</span></li><li><strong>Collect the evidence</strong><span>Each Google Alert searches for a specific required fact.</span></li><li><strong>Check the email</strong><span>Authenticate the full email and inspect the actual result text.</span></li><li><strong>Judge against the rules</strong><span>Match source, event and timing. Missing evidence stays unresolved.</span></li></ol><Link className="rs-demo-link" to="/demo/peace-2026">See a resolved replay <ArrowRight size={16} /></Link></section>
        <section className="rs-note"><h3>A query finds evidence.</h3><p>It is not the evidence itself. Even an <code>after:</code> filter cannot prove when the underlying event happened.</p></section>
      </aside>
    </div>
  </div>;
}

function RuleList({ title, items }: { title: string; items: string[] }) { return <div className="rs-rule-list"><h3>{title}</h3><ul>{items.map((item, i) => <li key={i}>{item}</li>)}</ul></div>; }
