/** Per-call raw-prefix diagnostic through the installed SDK, separate from scoring. */
import {readFile,writeFile,mkdir,stat} from 'node:fs/promises';
import {createRequire} from 'node:module';
import {createHash} from 'node:crypto';
const require=createRequire(import.meta.url);
const {LMStudioClient}=require('/Users/wk/.lmstudio/extensions/plugins/lmstudio/rag-v1/node_modules/@lmstudio/sdk/dist/index.cjs');
const root='/Users/wk/.local/share/means-of-prediction/slides/astra-qwen-nyt-round1-20260912';
const packet=JSON.parse(await readFile(root+'/runtime-mode-sdk-inputs.private.json','utf8'));
const limit=Number(process.argv[2]||1);
const extended=process.argv[3]==='open-free-8192';
const client=new LMStudioClient({baseUrl:'ws://127.0.0.1:1234'});
const model=await client.llm.model(packet.identifier);
const info=await model.getModelInfo();
const exists=async p=>stat(p).then(()=>true,()=>false);
const save=async(p,v)=>writeFile(p,JSON.stringify(v,null,2),{flag:'wx',mode:0o600});
const sha=s=>createHash('sha256').update(s).digest('hex');
for(const row of packet.cases.slice(0,limit)){
  const rendered=await model.applyPromptTemplate(row.messages);
  if(!rendered.endsWith('<think>\n'))throw new Error('Unexpected baseline thinking prefix; refusing guessed rewrite.');
  for(const variant of (extended?['open-free-8192']:['open-grammar','closed-grammar','open-free'])){
    const directory=`${root}/runtime-probes/sdk-mode/${row.caseId}/${variant}`;
    if(await exists(directory+'/result.json'))continue;
    if(await exists(directory+'/started.json'))throw new Error('Uncertain existing probe; no restart.');
    await mkdir(directory,{recursive:true});
    const prompt=variant==='closed-grammar'?rendered.slice(0,-8)+'<think>\n\n</think>\n\n':rendered;
    const config={temperature:0,maxTokens:extended?8192:2048,topKSampling:40,topPSampling:0.95,minPSampling:0.05,repeatPenalty:1.1,contextOverflowPolicy:'stopAtLimit',
      structured:variant.startsWith('open-free')?{type:'none'}:{type:'json',jsonSchema:packet.schema}};
    const tokens=await model.countTokens(prompt);
    if(tokens+config.maxTokens>info.contextLength)throw new Error('Full diagnostic input cannot fit.');
    const request={model:packet.identifier,prompt,config,api:'SDK.complete',baseRenderedSha256:sha(rendered),inputTokens:tokens,modelInfo:info};
    await save(directory+'/request.json',request);
    await save(directory+'/started.json',{at:new Date().toISOString(),pid:process.pid});
    const start=Date.now();
    try{
      const result=await model.complete(prompt,config);
      await save(directory+'/response.json',{content:result.content,reasoningContent:result.reasoningContent,nonReasoningContent:result.nonReasoningContent,
        stats:result.stats,modelInfo:result.modelInfo,loadConfig:result.loadConfig,predictionConfig:result.predictionConfig});
      await save(directory+'/result.json',{status:'response_received',seconds:(Date.now()-start)/1000,variant,inputTokens:tokens,stats:result.stats,
        responseSha256:sha(await readFile(directory+'/response.json')),requestSha256:sha(await readFile(directory+'/request.json'))});
      process.stdout.write(JSON.stringify({caseId:row.caseId,variant,seconds:(Date.now()-start)/1000,stats:result.stats})+'\n');
    }catch(error){
      await save(directory+'/result.json',{status:'failed',exceptionType:error.constructor.name,message:error.message,seconds:(Date.now()-start)/1000,variant});
      process.stdout.write(JSON.stringify({caseId:row.caseId,variant,status:'failed',message:error.message})+'\n');
    }
  }
}
