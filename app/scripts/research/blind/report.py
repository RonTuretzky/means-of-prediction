"""Private text-only research report. No images or public publication."""
import collections, datetime, json, os
from pathlib import Path
from experiment import ROOT,load,save,output_from
from improve import recover,evaluate,summarize

def pct(a,b):return f'{100*a/b:.1f}%' if b else 'unavailable'
def table(headers,rows):
    return '\n'.join(['| '+' | '.join(headers)+' |','| '+' | '.join(['---']*len(headers))+' |']+
        ['| '+' | '.join(str(x).replace('|','\\|').replace('\n',' ') for x in row)+' |' for row in rows])

def build():
    final=(ROOT/'final-scores.private.json').exists()
    calibration_released=(ROOT/'calibration-release.json').exists()
    lines=['# NYT-specific Astra rule-generation experiment','',
        '**Status: '+('final text scoring complete; see native checks below' if final else 'in progress — no final holdout claim')+'**','',
        'Updated '+datetime.datetime.now(datetime.timezone.utc).isoformat()+'.','',
        'This improves a reusable rule-writing prompt from real NYT training examples. It is prompt optimization, not model weight fine-tuning. A factual text hit is not a verified market settlement.','',
        'The former Qwen run produced 1/100 clean known-email source hits. That hit failed semantic counterexamples; 33/100 generations hit the old 2,000-token cap. The old result is preserved.','',
        'Astra is identified as `gpt-6-astra` in the service responses. The 2,000-token cap is removed. This connection rejects `max_output_tokens`, so the experiment controls supported reasoning effort and provides token guidance; the tables use actual service-reported token counts.','',
        '## Training and blind test','',
        table(['Split','Markets','Event/email groups','Distinct evidence emails'],[['Initial training',104,5,11],['Calibration (formerly validation)' if calibration_released else 'Validation',19,3,3],['Hidden final test',26,3,3]]),'',
        'All 149 cases were retrospectively selected as known factual matches. These are not a random sample of Polymarket markets. Shared raw emails, factual families and all US Open cases are grouped. Wider political/news-cycle correlations can remain across different contests. This retrospective holdout is not an externally pristine future benchmark. The historical archive contains 131 emails.','',
        ('The initial validation methods all scored 0/19. Those 19 cases were subsequently released for disclosed calibration, bringing the development pool to 123 cases. Their later results are training performance, not unseen validation. The 26 final-test cases remain excluded from every teacher and optimizer request.' if calibration_released else 'Validation/test evidence never enters the optimizer or new-market generator.'),'',
        'The optimizer sees development facts, HTML excerpts and failures. A new-market generation gets public rules, question, labels, ID, the frozen prompt, and its own review candidate where applicable. The public-context arm additionally supplies sorted contender names from archived public market questions created at least 30 days before the scheduled event end; it is distinct from the original four-field comparison. No model tools are exposed. Every request and raw completion is retained privately.','',
        '## Reasoning budget pilot','']
    if final:
        result=load('final-scores.private.json');test=result['test']['summary'];original=result['original']['summary']
        lines[6:6]=[
            f"**Held-out result: {test['cleanHits']}/{test['attempts']} factual text hits ({pct(test['cleanHits'],test['attempts'])}), covering {test['marketsWithHit']}/{test['distinctMarkets']} markets in at least one draw.** All these matching emails arrived after the closure proxy. This percentage is conditional on the selected known-match corpus, not coverage of all Polymarket markets.",'',
            f"The original ten-market replication reached {original['cleanHits']}/100; it includes training/calibration overlap and is not an unbiased comparison with the old 1/100 Qwen result. The blind test still produced {test['negativeFalsePositives']} synthetic negative false positives, and {test['attemptsWithoutControls']} draws lacked controls. The improved prompt is not ready to authorize settlements.",'']
    cases=load('train-cases.private.json');controls=load('controls.json') if (ROOT/'controls.json').exists() else {}
    records=[recover(p) for p in (ROOT/'pilot').glob('*/*/*/generation.json')]
    summaries={e:summarize(evaluate([r for r in records if r['effort']==e],cases,controls)) for e in ['medium','high','xhigh','max']}
    save(ROOT/'pilot-corrected-progress.json',summaries)
    lines += [table(['Effort','Attempts / planned','Model completions','Factual hits','Positive controls passed','Negative false positives / unscorable','Median known output tokens','Calls missing usage'],
        [[e,str(s['attempts'])+' / 8',sum(r['status']=='completed' for r in records if r['effort']==e),str(s['cleanHits'])+'/'+str(s['attempts']),str(s['positiveControlPasses'])+'/'+str(s['positiveControls']),
          str(s['negativeFalsePositives'])+' / '+str(s['negativeControlUnscorable']),s['medianOutputTokens'],s['callsWithoutTokenUsage']] for e,s in summaries.items()]),'',
        'Output tokens include reasoning and visible output; they are not just regex length. The initial pilot log misread empty terminal SSE output arrays as invalid JSON. These corrected scores recover the original completed stream/client outputs without regenerating them.','',
        'All eight max-effort calls and two xhigh calls ended without a completed response after approximately 902 seconds. Their usage is unavailable, not zero. This is a service completion failure, not a measurement of regex quality. Increasing guidance cannot remove that service behavior.','',
        '## Measured prompt revisions','']
    measured=[]
    for p in sorted((ROOT/'methods').glob('*/train-generations.json')):
        name=p.parent.name;rows=evaluate([recover(Path(r['directory'])/'generation.json') for r in json.loads(p.read_text())],cases,controls);s=summarize(rows)
        save(p.parent/'train-scores.private.json',rows);save(p.parent/'train-summary.json',s)
        measured.append([name,s['attempts'],pct(s['cleanHits'],s['attempts']),str(s['positiveControlPasses'])+'/'+str(s['positiveControls']),
                         str(s['negativeControlFailures'])+'/'+str(s['negativeControls']),s['medianOutputTokens'],s['pipelineOutputTokens']])
    lines += [table(['Method','Training attempts','Factual hits','Positive controls','Negative failures','Median final-call output tokens','All generation/review output tokens'],measured),'',
        'A method with no factual hits or no positive-control passes is ineligible as a useful detector. Missing controls never count as passed checks. Training measurements cannot establish out-of-sample performance.','']
    if (ROOT/'control-availability.json').exists():
        availability=load('control-availability.json');available=sum(c['available'] for c in availability.values())
        lines += [f'Independent synthetic controls are available for {available}/{len(availability)} requested markets. Astra declined or omitted fabricated political-election reports in the others; those refusals are retained and marked unavailable, with no bypass attempts. Control coverage is reported separately from factual-email coverage.','']
    if calibration_released:
        release=load('calibration-release.json');lines+=['## Initial validation, before release for calibration','',
            table(['Method','Unseen attempts at that time','Factual hits'],[[name,s['attempts'],s['cleanHits']] for name,s in release['preCalibrationValidationResults'].items()]),'',
            '## Later calibration (training) measurements','']
        calibration=[]
        for p in sorted((ROOT/'methods').glob('*/calibration-generations.json')):
            rows=evaluate([recover(Path(r['directory'])/'generation.json') for r in json.loads(p.read_text())],load('calibration-cases.private.json'),controls);s=summarize(rows)
            save(p.parent/'calibration-scores.private.json',rows);save(p.parent/'calibration-summary.json',s)
            calibration.append([p.parent.name,s['attempts'],s['cleanHits'],s['pipelineModelCalls'],s['pipelineOutputTokens']])
        lines += [table(['Method','Development attempts','Factual hits','Generation/review calls','Known output tokens'],calibration),'']
    for p in sorted((ROOT/'optimization').glob('*/lineage.json')):
         x=json.loads(p.read_text());lines += ['### '+p.parent.name,'']+['- '+c for c in x['changes']]+['',f'Prompt SHA-256: `{x["promptSha256"]}`. Training results seen: {x["trainingSummary"]["attempts"]}.','']
    if (ROOT/'selection-rationale.json').exists():
        selected=load('selection-rationale.json')
        lines+=['## Selected method','',selected['selectionRationale'],'',selected['qualityOrder'],'',
            table(['Method','Development hits / attempts','Hits passing available negatives','False positives','Pipeline calls','Known output tokens'],
                [[name,str(s['cleanHits'])+'/'+str(s['attempts']),s['safeControlHits'],s['negativeFalsePositives'],s['pipelineModelCalls'],s['pipelineOutputTokens']]
                 for name,s in selected['developmentComparison'].items()]),'',
            'The selected reusable prompt is `prompt-nyt-calibrated.txt`, medium effort with 8,000-token guidance and no hard output cap. It is a research candidate generator, not a production settlement policy.','']
    if final:
        data=load('final-scores.private.json');lines += ['## Frozen final results','']
        for split,item in data.items():
            s=item['summary'];lines += ['### '+split,'',table(['Attempts','Factual hit rate','Hits passing available negatives','Timely hits','4 KiB witness hits'],
               [[s['attempts'],pct(s['cleanHits'],s['attempts']),s['safeControlHits'],s['timelyHits'],s['windowCompatibleHits']]]),'',
               'The original ten-market replication overlaps training/calibration/test cases; only the separate 26-market set is held out from prompt optimization. Three test draws reuse the same 26 markets, so 78 attempts are not 78 independent news events.','',
               f"Distinct markets with at least one factual hit: {s['marketsWithHit']}/{s['distinctMarkets']}. Full-archive candidate pairs: {s['archiveCandidatePairs']} (unreviewed). Actual pipeline output tokens: {s['pipelineOutputTokens']}; input tokens: {s['pipelineInputTokens']} ({s['pipelineCachedInputTokens']} cached). Calls with unknown output usage: {s['pipelineCallsWithoutTokenUsage']}; unknown input usage: {s['pipelineCallsWithoutInputUsage']}.",'',
               table(['Event/email group','Attempts','Factual hits'],[[', '.join(sorted({r['factKey'].replace('_',' ') for r in item['rows'] if r['evaluationGroupId']==g})),v['attempts'],v['cleanHits']] for g,v in item.get('byGroup',{}).items()]),'',
               f"Independent controls: {s['positiveControlPasses']}/{s['positiveControls']} positives passed; {s['negativeFalsePositives']}/{s['negativeControls']} negative false positives; {s['negativeControlUnscorable']} unscorable negatives. {s['attemptsWithoutControls']} attempts have no controls, so they have no measured safety pass.",'']
            by_market=collections.defaultdict(list)
            for row in item['rows']:by_market[row['marketId']].append(row)
            for id,rows in sorted(by_market.items()):
                example=next((r for r in rows if r['score']['status']=='hit'),rows[0]);lines += ['#### '+example['question'],'',
                    f'Market `{id}`. Data split: {example["dataSplit"]}. Correct factual matches: {sum(r["score"]["status"]=="hit" for r in rows)}/{len(rows)}.','',
                    f"Known email `{example['knownEmailId']}` received {example['emailReceivedAt']}; market closure proxy {example['marketClosedAt']}. Available by closure: {example['availableByClosure']}.",'',
                    '**Original rules**','',example['rules'],'','**Representative generated pair**','']
                if example['output']:
                    for key in ['outcomeARegex','outcomeBRegex']:lines+=['```text',example['output'][key],'```','']
                    lines += [example['output'].get('limitations',''),'']
                actual=example['score']['actualIndex'];match=example['score']['matches'][actual]
                if match:lines+=['**Exact matched HTML source**','', '```html',match['text'],'```','']
                else:lines+=['No match in the known evidence email for this representative attempt.','']
    if final and (ROOT/'final-semantic-review.private.json').exists():
        review=load('final-semantic-review.private.json')
        lines+=['## Source review and remaining errors','',
            f"All {review['distinctMarketPassages']} distinct market/passage pairs behind the clean factual hits were inspected against the previously reviewed email facts. They are consistent with those outcomes in their source context. Date, national versus regional statistics, party/office and source requirements are not necessarily contained in the regex witness itself. Original-rule acceptance remains unproven.",'',
            'Retained synthetic failures include a state unemployment rate mistaken for a national figure, a payroll forecast mistaken for a release, a false viral victory claim, a different election year and a baseball result from the previous day. A factual hit therefore cannot be treated as a trustworthy automatic decision.','',
            'The held-out South Carolina runoff group scored 0/15. Its email names Darline Graham as nominee; the questions concern Ralph Norman and his victory margin. The generated rules did not connect that named rival victory to Norman’s loss. Those failures were not used to revise the frozen prompt.','']
    if (ROOT/'new-market-cpi/score.private.json').exists():
        example=load('new-market-cpi/score.private.json')
        lines+=['## New-market command check','',
            'The public-input-only `research:nyt-rule` command completed a separate Astra generation for August annual CPI market 3539674. Both output patterns passed the experiment syntax check. No target email or settled result was sent to its generation request.','',
            f"Against the newly received September 11 newsletter, this candidate scored **{example['knownEmailScore']['status']}**. The newsletter’s ‘rising at an annual pace’ phrasing was not covered by its generated routes. This extra example is outside the frozen 26-market score; it did not trigger a prompt revision. The original CPI rules require BLS, independently of textual recall.",'']
    if final and (ROOT/'native-output.private.json').exists():
        native=load('native-output.private.json');checks={c['pattern']:c for c in native['checks']}
        matches={(w['pattern'],w['decodedSource']):w for w in native['witnesses']};rows=[]
        for split,item in data.items():
            both=sum(all(checks.get(r['output'][k],{}).get('validateSucceeded') for k in ['outcomeARegex','outcomeBRegex']) for r in item['rows'] if isinstance(r['output'],dict))
            matcher=0;qualified=0
            for r in item['rows']:
                if r['score']['status']!='hit' or not r['knownWitness']['compatible']:continue
                p=r['output'][['outcomeARegex','outcomeBRegex'][r['score']['actualIndex']]]
                passed=bool(matches.get((p,r['knownWitness']['decodedSource']),{}).get('matchesWithinGasLimit'))
                matcher+=passed
                qualified+=passed and all(checks.get(r['output'][k],{}).get('validateSucceeded') for k in ['outcomeARegex','outcomeBRegex'])
            rows.append([split,both,matcher,qualified,len(item['rows'])])
        lines+=['## Final native library checks','',table(['Split','Both regexes validate','Factual witness matches','Both conditions','All attempts'],rows),'',
            f"Native checks used local chain 31337 with a {native['gasLimit']}-gas call budget. {sum(c['validateSucceeded'] for c in native['checks'])}/{len(native['checks'])} distinct patterns validated and {sum(w['matchesWithinGasLimit'] for w in native['witnesses'])}/{len(native['witnesses'])} distinct factual witnesses matched. Runtime artifact SHA-256: `{native['artifactSha256']}`. State override: {native.get('stateOverride',False)}; no transactions.",'']
    usage=collections.defaultdict(lambda:collections.Counter())
    for p in ROOT.rglob('transport-result.json'):
        relative=p.relative_to(ROOT);category=relative.parts[0]
        if category=='methods':category='Method generation/review'
        _,u,status=output_from(json.loads(p.read_text()),p.parent);v=usage[category]
        v['attempts']+=1;v['completed']+=status=='completed'
        v['inputTokens']+=u.get('input_tokens',0);v['outputTokens']+=u.get('output_tokens',0)
        v['cachedInputTokens']+=u.get('input_tokens_details',{}).get('cached_tokens',0)
        v['unknownUsage']+='output_tokens' not in u or 'input_tokens' not in u
    save(ROOT/'usage-audit.json',{k:dict(v) for k,v in usage.items()})
    lines+=['## Full experiment usage audit','',
        table(['Stage','Attempts','Completed JSON calls','Known input tokens','Cached input tokens','Known output tokens','Calls missing usage'],
            [[k,v['attempts'],v['completed'],v['inputTokens'],v['cachedInputTokens'],v['outputTokens'],v['unknownUsage']] for k,v in sorted(usage.items())]),'',
        'This includes teachers, controls, discarded methods and transport diagnostics once each. Known token totals are lower bounds when failed calls lack usage; cached input is a subset of input tokens. The NYT demonstration prompt itself is approximately 20,600 input tokens, so its cost cannot be represented by the roughly 1,800-token final output alone.','']
    lines += ['## Deployment limits','',
        'The experiment restricts patterns to ASCII and the contract limits each pattern to 10,000 bytes. Broader literal UTF-8 pattern support was not measured. The evidence witness must fit within 4,096 encoded bytes, and the full encoded body must be at most 192 KiB. Source matching occurs on decoded HTML bytes, not rendered text.','',
        'The first native pilot checked two generated patterns and both exhausted the local 16-million-gas validation call. Among three shorter supervised demonstrations, four of six patterns validated within that budget and one of three matched its source within it (10,804,451 matcher-only gas). These are training examples, not final-test results. A gas failure is not proof of invalid syntax. Native checks are read-only; no NYT email is posted onchain. Matcher gas excludes RSA/DKIM, storage, body verification and settlement.','',
        'Quoted or denied versions of a matching passage can contain the same positive substring. A source window may omit the context that disqualifies it. Official-source, deadline, event identity and consensus requirements must still be satisfied. No prompt in this experiment is automatically promoted to live settlement.','',
        'The exact protocol, split manifest, prompt lineage, request bodies, raw responses, token counts, controls and private scores are saved beside this report.','']
    (ROOT/'REPORT.md').write_text('\n'.join(lines))
    print(json.dumps({'report':str(ROOT/'REPORT.md'),'finalTextScoringComplete':final,'pilotFinished':len(records),'measuredMethods':len(measured)}))

if __name__=='__main__':os.umask(0o077);build()
