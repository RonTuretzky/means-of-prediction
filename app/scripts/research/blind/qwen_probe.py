"""Declared runtime capability probe, separate from scored benchmark draws."""
import json
import qwen_round1 as q

rule={
    'factualA':'The fictional Silver Owls defeated the fictional Copper Foxes in the final match.',
    'factualB':'The fictional Copper Foxes defeated the fictional Silver Owls in the final match.',
    'settlementA':'This email reports a completed final match won by the Silver Owls. No additional timing or source condition applies in this toy capability test.',
    'settlementB':'This email reports a completed final match won by the Copper Foxes. No additional timing or source condition applies in this toy capability test.',
    'abstainWhen':'The winner is missing, preliminary, forecast, or conflicting.',
    'limitations':'Entirely fictional runtime test; no real market result is being inferred.'}
email={'html':'<html><body><p>In the completed final match, the Silver Owls defeated the Copper Foxes, 3-1.</p></body></html>',
    'subject':'Fictional final match', 'domain':'example.invalid','signedDate':'','receivedAt':''}
request=q.judge_request(rule,email,q.BASE_JUDGE,q.load('runtime-draft.json'))
result=q.local_call(request,q.ROOT/'runtime-probes'/'openai-template-kwargs')
print(json.dumps(result),flush=True)
