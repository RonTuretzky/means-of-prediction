import { readFileSync,writeFileSync,existsSync,mkdirSync } from 'node:fs';
import { homedir } from 'node:os';
import { join } from 'node:path';
import { execFileSync } from 'node:child_process';
const dir=join(homedir(),'.config/means-of-prediction/worker');mkdirSync(dir,{recursive:true,mode:0o700});
const token=JSON.parse(readFileSync(join(dir,'provisioning.json'))).digitalOceanToken;
const statePath=join(dir,'digitalocean.json'),state=existsSync(statePath)?JSON.parse(readFileSync(statePath)):{};
const save=()=>writeFileSync(statePath,JSON.stringify(state,null,2),{mode:0o600});
async function api(path,body){const r=await fetch('https://api.digitalocean.com/v2'+path,{method:body?'POST':'GET',headers:{Authorization:'Bearer '+token,'Content-Type':'application/json'},...(body?{body:JSON.stringify(body)}:{}),signal:AbortSignal.timeout(30000)});const j=await r.json();if(!r.ok)throw Error('DigitalOcean HTTP '+r.status);return j;}
try{
 const name='mop-email-settler';
 const droplets=(await api('/droplets?per_page=200')).droplets,existing=droplets.find(d=>d.name===name);
 if(existing){Object.assign(state,{dropletId:existing.id,ip:existing.networks.v4.find(v=>v.type==='public')?.ip_address});save();console.log(JSON.stringify({existing:true,id:existing.id,status:existing.status,ip:state.ip}));}
 else{
  const size=(await api('/sizes?per_page=200')).sizes.find(s=>s.slug==='s-1vcpu-1gb'&&s.available&&s.regions.includes('nyc3'));if(!size||size.price_monthly>6)throw Error('Expected worker size unavailable');
  const keyPath=join(dir,'digitalocean_ed25519');if(!existsSync(keyPath))execFileSync('ssh-keygen',['-t','ed25519','-f',keyPath,'-N','','-C',name],{stdio:'ignore'});
  const publicKey=readFileSync(keyPath+'.pub','utf8').trim();let key=(await api('/account/keys?per_page=200')).ssh_keys.find(k=>k.public_key.trim()===publicKey);
  if(!key)key=(await api('/account/keys',{name,public_key:publicKey})).ssh_key;
  state.sshKeyId=key.id;save();
  const tags=(await api('/tags?per_page=200')).tags;if(!tags.some(t=>t.name===name))await api('/tags',{name});
  const ip=(await(await fetch('https://api.ipify.org',{signal:AbortSignal.timeout(15000)})).text()).trim();if(!/^\d{1,3}(\.\d{1,3}){3}$/.test(ip))throw Error('Operator IP unavailable');
  let firewall=(await api('/firewalls?per_page=200')).firewalls.find(f=>f.name===name);
  if(!firewall)firewall=(await api('/firewalls',{name,tags:[name],inbound_rules:[{protocol:'tcp',ports:'22',sources:{addresses:[ip+'/32']}}],outbound_rules:[{protocol:'tcp',ports:'all',destinations:{addresses:['0.0.0.0/0','::/0']}},{protocol:'udp',ports:'all',destinations:{addresses:['0.0.0.0/0','::/0']}},{protocol:'icmp',destinations:{addresses:['0.0.0.0/0','::/0']}}]})).firewall;
  Object.assign(state,{firewallId:firewall.id,operatorSshCidr:ip+'/32'});save();
  const d=(await api('/droplets',{name,region:'nyc3',size:size.slug,image:'ubuntu-24-04-x64',ssh_keys:[key.id],backups:true,ipv6:true,monitoring:true,tags:[name],user_data:readFileSync(new URL('./bootstrap.sh',import.meta.url),'utf8')})).droplet;
  Object.assign(state,{dropletId:d.id,createdAt:d.created_at,monthlyBaseUsd:size.price_monthly,backups:true});save();console.log(JSON.stringify({created:true,id:d.id,monthlyBaseUsd:size.price_monthly,backups:true}));
 }
}catch{console.error('Worker provisioning failed; credentials and provider response suppressed.');process.exitCode=1;}
