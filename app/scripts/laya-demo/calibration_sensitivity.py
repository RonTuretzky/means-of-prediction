"""Diagnostic re-scaling of saved logits; never runs a model or selects a profile."""
import argparse
import json
from pathlib import Path
import numpy as np
from artifacts import file_sha, save

p=argparse.ArgumentParser()
p.add_argument('reference',type=Path)
p.add_argument('output',type=Path)
a=p.parse_args()
r=json.loads(a.reference.read_bytes())
t=r['profile']['rawEpochTemperatureNoul2']
probs={}
for key,row in zip(r['profile']['questionOrder'],r['capturedLogitsAndActionLogits'][0]):
    z=np.asarray(row,dtype=np.float32)/t
    v=np.exp(z-z.max());v/=v.sum()
    probs[key]=round(float(v[1]),4)
report={'referenceSHA256':file_sha(a.reference),
    'basis':'Post-run diagnostic only: same captured logits, raw-epoch temperature. No model inference, prompt edit, threshold tuning or profile replacement.',
    'chosenProfileUnchanged':True,'finalTemperature':r['profile']['temperatureNoul2'],
    'finalProbabilities':r['probabilities'],'rawEpochTemperature':t,
    'rawTemperatureCounterfactualProbabilities':probs,
    'rawTemperatureCounterfactualFlags':{k:probs[k]>=.55 for k in ['A','B']},
    'calibrationQualityEquivalenceEstablished':False}
save(a.output,report)
print(json.dumps(report))
