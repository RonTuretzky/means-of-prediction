import { DatabaseSync,backup } from 'node:sqlite';
import { readPrivate } from './config.mjs';
import { Store } from './store.mjs';
import { safeCode } from './errors.mjs';
try{
 const c=JSON.parse(readPrivate(process.env.MOP_WORKER_CONFIG||process.env.MOP_SIGNER_CONFIG));
 const source=new DatabaseSync(c.database,{readOnly:true}),path=c.database.replace(/[^/]+$/, '')+'backups/latest.sqlite';
 await backup(source,path);source.close();
 const verified=new Store(path,Buffer.from(readPrivate(c.storageKeyFile),'hex'));
 if(verified.get('PRAGMA integrity_check').integrity_check!=='ok')throw Error();verified.close();
 console.log(JSON.stringify({event:'backup_verified'}));
}catch(e){console.error(JSON.stringify({event:'backup_failed',code:safeCode(e)}));process.exitCode=1;}
