/** Full-input accounting only. Does not issue a generation request. */
import {readFile,writeFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import {createHash} from 'node:crypto';
const require=createRequire(import.meta.url);
const {LMStudioClient}=require('/Users/wk/.lmstudio/extensions/plugins/lmstudio/rag-v1/node_modules/@lmstudio/sdk/dist/index.cjs');
const [inputPath,outputPath]=process.argv.slice(2);
const bytes=await readFile(inputPath);
const packet=JSON.parse(bytes.toString('utf8'));
const model=await new LMStudioClient({baseUrl:'ws://127.0.0.1:1234'}).llm.model(packet.identifier);
const contextLength=await model.getContextLength();
const modelInfo=await model.getModelInfo();
const counts=[];
const seen=new Set();
for(const row of packet.requests){
  if(seen.has(row.caseId))throw new Error('Duplicate preflight case');
  seen.add(row.caseId);
  const rendered=await model.applyPromptTemplate(row.request.messages);
  const inputTokens=await model.countTokens(rendered);
  counts.push({caseId:row.caseId,inputTokens,outputAllowance:row.request.max_tokens,
    fits:inputTokens+row.request.max_tokens<=contextLength,
    renderedPromptSha256:createHash('sha256').update(rendered).digest('hex')});
}
const result={at:new Date().toISOString(),identifier:packet.identifier,modelInfo,contextLength,
  inputSha256:createHash('sha256').update(bytes).digest('hex'),counts,
  allFullInputsFit:counts.every(x=>x.fits),maximumInputTokens:Math.max(0,...counts.map(x=>x.inputTokens)),
  note:'Full rendered prompts counted without inference; no source clipping. Over-limit cases retained explicitly.'};
await writeFile(outputPath,JSON.stringify(result,null,2)+'\n',{flag:'wx',mode:0o600});
console.log(JSON.stringify({cases:counts.length,overflow:counts.filter(x=>!x.fits).length,maxInputTokens:result.maximumInputTokens}));
