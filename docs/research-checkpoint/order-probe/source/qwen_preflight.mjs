/** Verify the actual rendered full-input token counts before local inference. */
import {readFile,writeFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
import {createHash} from 'node:crypto';
const require=createRequire(import.meta.url);
const {LMStudioClient}=require('/Users/wk/.lmstudio/extensions/plugins/lmstudio/rag-v1/node_modules/@lmstudio/sdk/dist/index.cjs');
const [inputPath,outputPath]=process.argv.slice(2);
const inputBytes=await readFile(inputPath);const packet=JSON.parse(inputBytes.toString('utf8'));
const client=new LMStudioClient({baseUrl:'ws://127.0.0.1:1234'});
const model=await client.llm.model(packet.identifier);
const contextLength=await model.getContextLength();
const modelInfo=await model.getModelInfo();
const counts=[];
for(const row of packet.requests){
  const rendered=await model.applyPromptTemplate(row.request.messages);
  const inputTokens=await model.countTokens(rendered);
  if(inputTokens+row.request.max_tokens>contextLength)throw new Error(`Full input does not fit; refusing truncation: ${row.caseId}`);
  counts.push({caseId:row.caseId,inputTokens,outputAllowance:row.request.max_tokens});
}
const result={at:new Date().toISOString(),identifier:packet.identifier,modelInfo,contextLength,cases:counts.length,inputSha256:createHash('sha256').update(inputBytes).digest('hex'),
  maximumInputTokens:Math.max(...counts.map(x=>x.inputTokens)),counts,allFullInputsFit:true,
  note:'Token counts use the installed model prompt template. No email was sent to inference in this preflight; no labels are present in input.'};
await writeFile(outputPath,JSON.stringify(result,null,2),{flag:'wx',mode:0o600});
console.log(JSON.stringify({contextLength,cases:counts.length,maxInputTokens:result.maximumInputTokens,allFullInputsFit:true}));
