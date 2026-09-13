// Deploy a hashed, explicitly scoped runtime snapshot. The shared worktree has
// unrelated uncommitted work; never archive all of it or publish private mail.
import{readFileSync,writeFileSync,mkdirSync,copyFileSync,readdirSync,existsSync,chmodSync}from'node:fs';
import{join,dirname,resolve}from'node:path';import{homedir}from'node:os';import{createHash}from'node:crypto';import{execFileSync}from'node:child_process';
const root=resolve(dirname(new URL(import.meta.url).pathname),'../..'),dir=join(homedir(),'.config/means-of-prediction/worker'),state=JSON.parse(readFileSync(join(dir,'digitalocean.json')));
if(!/^\d{1,3}(\.\d{1,3}){3}$/.test(state.ip))throw Error('Worker host unavailable');
const ssh=['-i',join(dir,'digitalocean_ed25519'),'-o','IdentityAgent=none','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+join(dir,'known_hosts'),'-o','ConnectTimeout=10','-o','ServerAliveInterval=10','-o','ServerAliveCountMax=3'];
const run=(cmd,args)=>execFileSync(cmd,args,{encoding:'utf8',stdio:['ignore','pipe','pipe'],timeout:300000});
try{
 const paths=[...readdirSync(join(root,'app/automation')).filter(n=>n.endsWith('.mjs')&&!['e2e.mjs'].includes(n)).map(n=>'app/automation/'+n),...['body.ts','body-transport.ts','dkim.ts','prover.ts'].map(n=>'app/src/lib/'+n),'app/scripts/mailbox.mjs',...readdirSync(join(root,'ops/settler')).filter(n=>n.endsWith('.service')||n.endsWith('.timer')||n==='install-release.sh').map(n=>'ops/settler/'+n)];
 const files=paths.map(path=>({path,sha256:createHash('sha256').update(readFileSync(join(root,path))).digest('hex')}));
 for(const n of ['package.json','package-lock.json'])files.push({path:'app/'+n,sha256:createHash('sha256').update(readFileSync(join(root,'app/automation',n))).digest('hex')});
 const id=createHash('sha256').update(JSON.stringify(files)).digest('hex'),stage=join(dir,'releases',id);mkdirSync(stage,{recursive:true,mode:0o700});
 for(const path of paths){mkdirSync(dirname(join(stage,path)),{recursive:true});copyFileSync(join(root,path),join(stage,path));}
 for(const n of ['package.json','package-lock.json'])copyFileSync(join(root,'app/automation',n),join(stage,'app',n));
 writeFileSync(join(stage,'release.json'),JSON.stringify({id,createdAt:new Date().toISOString(),files},null,2));
 const archive=join(dir,'release.tgz');run('tar',['-czf',archive,'-C',stage,'.']);chmodSync(archive,0o600);
 run('scp',[...ssh,archive,`root@${state.ip}:/root/mop-release.tgz`]);
 if(process.argv.includes('--configure')){
  const configArchive=join(dir,'service-config.tgz');run('tar',['-czf',configArchive,'-C',join(dir,'service'),'.']);chmodSync(configArchive,0o600);
  run('scp',[...ssh,configArchive,`root@${state.ip}:/root/mop-config.tgz`]);
  run('ssh',[...ssh,`root@${state.ip}`,'tar --no-same-owner -xzf /root/mop-config.tgz -C /etc/mop && chown root:root /etc/mop && chmod 755 /etc/mop && chown -R mop-settler:mop-settler /etc/mop/collector && chown -R mop-signer:mop-signer /etc/mop/signer && chmod 700 /etc/mop/collector /etc/mop/signer && chmod 600 /etc/mop/collector/* /etc/mop/signer/* && rm /root/mop-config.tgz']);
 }
 const release='/opt/mop/releases/'+id;
 const output=run('ssh',[...ssh,`root@${state.ip}`,`mkdir -p ${release} && tar --no-same-owner -xzf /root/mop-release.tgz -C ${release} && rm /root/mop-release.tgz && bash ${release}/ops/settler/install-release.sh ${release}`]);
 Object.assign(state,{release:id,deployedAt:new Date().toISOString()});writeFileSync(join(dir,'digitalocean.json'),JSON.stringify(state,null,2),{mode:0o600});
 console.log(output.slice(-2000));console.log(JSON.stringify({deployed:id,ip:state.ip}));
}catch{console.error('Worker deployment failed; provider output suppressed. Inspect service status with the pinned SSH configuration.');process.exitCode=1;}
