/** Read-only loaded-model/config/template inspection. Never loads or predicts. */
import {readFile} from 'node:fs/promises';
import {createRequire} from 'node:module';
const require=createRequire(import.meta.url);
const {LMStudioClient}=require('/Users/wk/.lmstudio/extensions/plugins/lmstudio/rag-v1/node_modules/@lmstudio/sdk/dist/index.cjs');
const packet=JSON.parse(await readFile(process.argv[2],'utf8'));
const client=new LMStudioClient({baseUrl:'ws://127.0.0.1:1234'});
const model=await client.llm.model(packet.identifier);
const modelInfo=await model.getModelInfo();
if(modelInfo?.identifier!==packet.identifier)throw Error('Loaded instance differs');
const loadConfig=await model.getLoadConfig('Read-only V3 continuation runtime audit');
const counts=[];
for(const row of packet.requests){
  const rendered=await model.applyPromptTemplate(row.request.messages);
  counts.push({caseId:row.caseId,inputTokens:await model.countTokens(rendered),outputAllowance:row.request.max_tokens});
}
console.log(JSON.stringify({modelInfo,loadConfig,counts}));
