"""Dataset v2, step 1: the market pool.

Selects catalog markets whose rules settle on "credible reporting" (a newspaper
report is admissible evidence), that resolved decisively inside a date window,
and that are not sports matches or crypto price ticks, then buckets them by
topic. Latest catalog version per market. Held-out and reserved markets are
excluded through the catalog's training_holdout flag. Payouts are carried as
private observations for consistency checks, never as truth labels.

Output (private, write-once): <out>/market-pool.jsonl and <out>/manifest.json.
"""
import argparse, collections, hashlib, json, os, re, sqlite3, time
from pathlib import Path

CATALOG = Path.home()/'.local/share/means-of-prediction/historical-market-catalog-20260914/catalog.sqlite3'
SPORTS_PROP = (r'\bvs\.?\b|\bwin on\b|\bbeat\b|spread|o/u|over/under|moneyline|\bmap \d|\bgame \d|\bset \d|\bfight night\b|\bhalf\b.*\bpoints\b|\brecord the most\b'
               r'|exact score|any other score|\d+\+ ?(goals?|assists?|shots?|points?|rebounds?|yards?|saves?|tackles?|hits?|runs?|strikeouts?|touchdowns?|3-pointers?|threes?|blocks?|steals?|passing|rushing|receiving|kills?|aces)'
               r'|\bfc\b|\bsc\b|\bcf\b|\bafc\b|\bcd\b|\bsk\b|\bfk\b|united\b|athletic\b|rovers\b|wanderers\b|qualify for|clean sheet|first goal|anytime|both teams|total goals|halftime|winning margin|to score|yellow card|red card|corners?\b|double-double|triple-double'
               r'|\bhome run\b|\bpitcher\b|\bquarterback\b|\brounds?\b.*\b(fight|bout)\b|\bko\b|\bwin by\b|\bwin the (match|game|race|set|round|bout|fight)\b|\bgrand prix\b|\bpole position\b|\bfastest lap\b|\bpodium\b')
TOPICS = [('sports_match', SPORTS_PROP),
          ('crypto_price', r'up or down|\b(btc|eth|sol|xrp|bnb|doge|bitcoin|ethereum|solana|dogecoin|hyperliquid)\b.*(price|above|below|hit|reach|\$)|\$[\d,]+.*\b(btc|eth|sol|bitcoin|ethereum)\b'),
          ('sports_season', r'\b(win the|champion|mvp|playoffs|super bowl|world series|stanley cup|nba finals|premier league|ballon|heisman|grand slam|wimbledon|open\b.*\bwin|masters|draft(ed)?|relegat|promot|world cup|olympic)\b'),
          ('elections_politics', r'\b(elect|election|president|senate|congress|governor|mayor|primary|poll|approval|impeach|nominee|cabinet|prime minister|parliament|vote|endorse|resign|confirm)\b'),
          ('geopolitics_conflict', r'\b(ceasefire|invade|strike|war|troops|nato|sanction|missile|nuclear|hostage|russia|ukraine|israel|gaza|iran|taiwan|houthi|hezbollah)\b'),
          ('courts_legal', r'\b(convict|verdict|indict|sentenc|guilty|pardon|supreme court|ruling|lawsuit|trial|arrest|charged|extradit|deport)\b'),
          ('entertainment', r'\b(oscar|grammy|emmy|box office|album|billboard|netflix|movie|film|song|award|rotten tomatoes|imdb|tour|concert)\b'),
          ('business_econ', r'\b(fed|rate cut|rate hike|cpi|inflation|gdp|earnings|ipo|stock|nasdaq|s&p|tariff|unemployment|jobs report|acquire|merger|ceo|bankrupt|layoff)\b'),
          ('science_tech', r'\b(openai|gpt|gemini|claude|grok|spacex|launch|starship|nasa|ai model|apple|iphone|tesla|token|stablecoin|mainnet|airdrop)\b'),
          ('weather_climate', r'\b(temperature|hurricane|earthquake|rainfall|snow|heat|degrees|°|wildfire|storm)\b')]

def topic(question):
    ql = (question or '').lower()
    for name, pat in TOPICS:
        if re.search(pat, ql): return name
    return 'other_news'

def outcome(state):
    try:
        prices = json.loads(state.get('outcomePrices') or '[]'); labels = json.loads(state.get('outcomes') or '[]')
        if len(prices) == len(labels) and prices.count('1') == 1: return labels[prices.index('1')]
    except (ValueError, TypeError): pass
    return None

def build(out, start, end, include_sports, include_crypto):
    out = Path(out)
    if out.exists(): raise RuntimeError('Output exists; use a new directory')
    os.umask(0o077); out.mkdir(parents=True, mode=0o700)
    db = sqlite3.connect('file:'+str(CATALOG)+'?mode=ro', uri=True)
    held = {r[0] for r in db.execute('select market_id from markets where training_holdout=1')}
    latest, t0 = {}, time.time()
    query = ("select version_id, market_id, question, rules, labels_json, state_json, event_group_ids_json, condition_id from versions "
             "where rules like '%credible reporting%' and json_extract(state_json,'$.umaResolutionStatus')='resolved' "
             "and json_extract(state_json,'$.closedTime') >= ? and json_extract(state_json,'$.closedTime') < ?")
    scanned = 0
    for vid, mid, question, rules, labels, state, groups, condition in db.execute(query, (start, end)):
        scanned += 1
        if mid in held: continue
        if mid not in latest or vid > latest[mid][0]:
            latest[mid] = (vid, question, rules, labels, state, groups, condition)
    counts = collections.Counter(); months = collections.Counter(); kept = 0; excluded = collections.Counter()
    with (out/'market-pool.jsonl').open('w') as handle:
        for mid, (vid, question, rules, labels, state, groups, condition) in sorted(latest.items()):
            st = json.loads(state); t = topic(question); res = outcome(st)
            if res is None: excluded['no_decisive_outcome'] += 1; continue
            if t == 'sports_match' and not include_sports: excluded['sports_match'] += 1; continue
            if t == 'crypto_price' and not include_crypto: excluded['crypto_price'] += 1; continue
            row = {'marketId': mid, 'versionId': vid, 'conditionId': condition, 'eventGroupIds': json.loads(groups or '[]'), 'question': question, 'rules': rules,
                   'outcomeLabels': json.loads(labels or '[]'), 'topic': t, 'closedTime': st.get('closedTime'),
                   'privateObservation': {'outcome': res, 'resolvedBy': st.get('resolvedBy'), 'automaticallyResolved': st.get('automaticallyResolved')}}
            handle.write(json.dumps(row, ensure_ascii=False)+'\n'); kept += 1; counts[t] += 1; months[(st.get('closedTime') or '')[:7]] += 1
    digest = hashlib.sha256((out/'market-pool.jsonl').read_bytes()).hexdigest()
    manifest = {'createdAt': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'catalog': str(CATALOG), 'window': [start, end], 'scannedVersions': scanned,
                'distinctMarkets': len(latest), 'kept': kept, 'excluded': dict(excluded), 'heldOutSkipped': 'catalog training_holdout flag', 'byTopic': dict(counts.most_common()),
                'byMonth': dict(sorted(months.items())), 'ruleFilter': "rules LIKE '%credible reporting%' and umaResolutionStatus = resolved and decisive outcomePrices",
                'poolSha256': digest, 'seconds': round(time.time()-t0, 1), 'payoutPolicy': 'privateObservation.outcome is a consistency check for claims, never a truth label'}
    (out/'manifest.json').write_text(json.dumps(manifest, indent=2)); print(json.dumps({k: v for k, v in manifest.items() if k not in ['byMonth']}, indent=1))

if __name__ == '__main__':
    p = argparse.ArgumentParser(); p.add_argument('--out', required=True); p.add_argument('--start', default='2025-06-01'); p.add_argument('--end', default='2026-09-13')
    p.add_argument('--include-sports', action='store_true'); p.add_argument('--include-crypto', action='store_true'); a = p.parse_args()
    build(a.out, a.start, a.end, a.include_sports, a.include_crypto)
