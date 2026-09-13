// Private operator diagnostics. Does not log mail, credentials or signed bytes.
import { readFileSync,writeFileSync,mkdirSync,chmodSync } from 'node:fs';
import { homedir } from 'node:os';import { join } from 'node:path';
import { execFileSync } from 'node:child_process';
import { Store } from '../../app/automation/store.mjs';
process.umask(0o077);
const dir=join(homedir(),'.config/means-of-prediction/worker'),state=JSON.parse(readFileSync(join(dir,'digitalocean.json')));
const ssh=['-i',join(dir,'digitalocean_ed25519'),'-o','IdentityAgent=none','-o','IdentitiesOnly=yes','-o','BatchMode=yes','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+join(dir,'known_hosts')];
const run=(program,args)=>execFileSync(program,args,{encoding:'utf8',stdio:['ignore','pipe','pipe'],timeout:120000});
const remote=command=>run('ssh',[...ssh,'root@'+state.ip,command]);
try {
 if(process.argv.includes('--restart')){remote('systemctl restart mop-signer mop-settler');await new Promise(r=>setTimeout(r,5000));}
 const health=JSON.parse(remote('curl --silent --show-error http://127.0.0.1:4321/health'));
 const result={checkedAt:new Date().toISOString(),release:state.release,health};
 if(process.argv.includes('--verify')){
  const denied=command=>{try{remote(command);return false;}catch(e){if(e.status===1)return true;throw e;}};
  result.isolation={
   collectorCannotReadSignerKey:denied('runuser -u mop-settler -- test -r /etc/mop/signer/private.key'),
   signerCannotReadMailbox:denied('runuser -u mop-signer -- test -r /etc/mop/collector/mailbox.json'),
   signerLockExclusive:denied('flock --nonblock /var/lib/mop-signer/process.lock true'),
   collectorLockExclusive:denied('flock --nonblock /var/lib/mop-settler/process.lock true'),
   signerNetworkPrivate:remote('systemctl show mop-signer -p PrivateNetwork --value').trim()==='yes',
   signerUnixOnly:remote('systemctl show mop-signer -p RestrictAddressFamilies --value').trim()==='AF_UNIX',
   healthLoopbackOnly:remote('ss -H -lnt sport = :4321').includes('127.0.0.1:4321'),
   invalidSignRejected:remote("curl --silent --unix-socket /run/mop-ipc/signer.sock -X POST -H 'Content-Type: application/json' --data '{}' -w '%{http_code}' http://localhost/sign").endsWith('422'),
  };
  if(!Object.values(result.isolation).every(Boolean))throw Error('Isolation check failed');
  remote('systemctl start mop-backup@settler.service mop-backup@signer.service');
  const target=join(homedir(),'.local/share/means-of-prediction/worker-backups',new Date().toISOString().replace(/[:.]/g,'-'));mkdirSync(target,{recursive:true,mode:0o700});
  result.backups={};
  for(const [role,folder] of [['collector','settler'],['signer','signer']]){
   const file=join(target,folder+'.sqlite');run('scp',[...ssh,'root@'+state.ip+':/var/lib/mop-'+folder+'/backups/latest.sqlite',file]);chmodSync(file,0o600);
   const db=new Store(file,Buffer.from(readFileSync(join(dir,'service',role,'storage.key'),'utf8').trim(),'hex'));
   result.backups[role]={restored:db.get('PRAGMA integrity_check').integrity_check==='ok',counts:db.counts()};
   if(role==='collector'){
    result.emailDomains=db.all('SELECT domain,count(*) AS count FROM messages GROUP BY domain');
    result.intakeLastRejection=db.getMeta('last-rejected-code');
    result.actions=db.all('SELECT id FROM actions ORDER BY nonce').map(({id})=>{const a=db.action(id);return {id:a.id,jobId:a.job_id,state:a.state,nonce:a.nonce,to:a.payload.request.to,versions:a.payload.versions.map(v=>({hash:v.hash})),receipt:a.payload.receipt};});
   }
   db.close();
  }
  result.backupTimers=remote('systemctl is-active mop-backup@settler.timer mop-backup@signer.timer').trim().split('\n');
  writeFileSync(join(target,'inspection.json'),JSON.stringify(result,null,2));
  writeFileSync(join(homedir(),'.local/share/means-of-prediction/worker-inspection.json'),JSON.stringify(result,null,2));
 }
 console.log(JSON.stringify(result,null,2));
}catch{console.error('Worker inspection failed; sensitive host output suppressed. Check the pinned SSH connection and systemd service health.');process.exitCode=1;}
