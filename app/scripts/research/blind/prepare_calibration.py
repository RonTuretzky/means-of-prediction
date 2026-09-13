"""Release the former validation set for disclosed calibration; test stays sealed."""
import datetime,json
from experiment import ROOT,BASE,load,save
from prepare_dataset import source_window
from improve import corpus

def prepare():
    if (ROOT/'calibration-cases.private.json').exists():raise RuntimeError('Calibration release already recorded')
    prior={}
    for p in (ROOT/'methods').glob('*/validation-summary.json'):prior[p.parent.name]=json.loads(p.read_text())
    if not prior:raise RuntimeError('Preserve the initial validation measurements before calibration')
    cases=[dict(c,split='calibration') for c in load('validation-cases.private.json')]
    audit=json.loads((ROOT.parents[1]/'nyt/reviewed-audit.json').read_text());facts={f['key']:f for f in audit['facts']};emails=corpus()
    examples=[{**c,**source_window(emails[c['emailId']],facts[c['factKey']])} for c in cases]
    save(ROOT/'calibration-cases.private.json',cases);save(ROOT/'calibration-examples.private.json',examples)
    save(ROOT/'calibration-public-inputs.json',[c['publicInput'] for c in cases])
    save(ROOT/'calibration-release.json',{'releasedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),
         'reason':'After five initial methods failed to generalize, use these email failures for NYT prompt calibration as the user requested. The final 26 test markets remain unseen.',
         'formerValidationIsNowDevelopmentData':True,'preCalibrationValidationResults':prior,
         'finalTestCases':26,'testEvidenceProvidedToModels':False,'calibrationCases':len(cases),
         'locatedSourceExcerpts':sum(e['sourceExcerptLocated'] for e in examples)})
    print(json.dumps({'releasedCalibrationCases':len(cases),'factualFamilies':len({c['factKey'] for c in cases}),'sourceExcerptsLocated':sum(e['sourceExcerptLocated'] for e in examples),'finalTestUnchanged':True}))

if __name__=='__main__':prepare()
