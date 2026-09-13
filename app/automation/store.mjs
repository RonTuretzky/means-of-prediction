// Adapted from issue.fund's encrypted SQLite journal; independent databases/keys.
import { DatabaseSync } from 'node:sqlite';
import { mkdirSync, chmodSync } from 'node:fs';
import { dirname } from 'node:path';
import { createHash, randomBytes, createCipheriv, createDecipheriv } from 'node:crypto';
import { fail } from './errors.mjs';
export const json = value => JSON.stringify(value, (_,v) => typeof v === 'bigint' ? v.toString() : v);
export const digest = value => createHash('sha256').update(value).digest('hex');
export class Store {
 constructor(path, key, maxBytes=256*1024*1024) {
  if (key.length!==32) fail('storage_key_invalid');
  this.key=Buffer.from(key); this.maxBytes=maxBytes;
  if(path!==':memory:') mkdirSync(dirname(path),{recursive:true,mode:0o700});
  this.db=new DatabaseSync(path);
  if(path!==':memory:') chmodSync(path,0o600);
  this.db.exec(`PRAGMA journal_mode=WAL; PRAGMA synchronous=FULL; PRAGMA foreign_keys=ON; PRAGMA busy_timeout=5000;
   CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY,value TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS health(name TEXT PRIMARY KEY,ok INTEGER,code TEXT,checked_at INTEGER);
   CREATE TABLE IF NOT EXISTS messages(id TEXT PRIMARY KEY,domain TEXT,issued_at INTEGER,received_at INTEGER,cipher BLOB NOT NULL);
   CREATE TABLE IF NOT EXISTS markets(id INTEGER PRIMARY KEY,address TEXT NOT NULL,config TEXT NOT NULL);
   CREATE TABLE IF NOT EXISTS jobs(id TEXT PRIMARY KEY,market TEXT,source INTEGER,email_id TEXT,state TEXT,code TEXT,updated_at INTEGER);
   CREATE TABLE IF NOT EXISTS actions(id TEXT PRIMARY KEY,job_id TEXT,state TEXT,nonce INTEGER,cipher BLOB NOT NULL,updated_at INTEGER);
   CREATE UNIQUE INDEX IF NOT EXISTS nonce_owner ON actions(nonce);
  `);
  const marker=this.getMeta('encryption-check');
  if(marker) { if(this.open(Buffer.from(marker,'base64'),'key-check').value!=='mop-settler')fail('storage_key_invalid'); }
  else this.setMeta('encryption-check',this.seal({value:'mop-settler'},'key-check').toString('base64'));
 }
 get(sql,...args){return this.db.prepare(sql).get(...args);}
 all(sql,...args){return this.db.prepare(sql).all(...args);}
 run(sql,...args){return this.db.prepare(sql).run(...args);}
 transaction(fn){this.db.exec('BEGIN IMMEDIATE');try{const v=fn();this.db.exec('COMMIT');return v;}catch(e){this.db.exec('ROLLBACK');throw e;}}
 getMeta(key){const r=this.get('SELECT value FROM meta WHERE key=?',key);return r?JSON.parse(r.value):null;}
 setMeta(key,value){this.run('INSERT INTO meta VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',key,json(value));}
 health(name,ok,code=null){this.run('INSERT INTO health VALUES (?,?,?,?) ON CONFLICT(name) DO UPDATE SET ok=excluded.ok,code=excluded.code,checked_at=excluded.checked_at',name,ok?1:0,code,Date.now());}
 seal(value,context){const nonce=randomBytes(12),c=createCipheriv('aes-256-gcm',this.key,nonce);c.setAAD(Buffer.from(context));const bytes=Buffer.concat([c.update(json(value)),c.final()]);return Buffer.concat([nonce,c.getAuthTag(),bytes]);}
 open(value,context){const b=Buffer.from(value),d=createDecipheriv('aes-256-gcm',this.key,b.subarray(0,12));d.setAAD(Buffer.from(context));d.setAuthTag(b.subarray(12,28));return JSON.parse(Buffer.concat([d.update(b.subarray(28)),d.final()]).toString());}
 ensureCapacity(extra){const r=this.get('SELECT (SELECT coalesce(sum(length(cipher)),0) FROM messages)+(SELECT coalesce(sum(length(cipher)),0) FROM actions) AS bytes');if(r.bytes+extra>this.maxBytes)fail('storage_full');}
 putMessage(raw,metadata){const id=digest(raw);if(this.get('SELECT id FROM messages WHERE id=?',id))return id;const cipher=this.seal({raw:Buffer.from(raw).toString('base64'),...metadata},'message:'+id);this.ensureCapacity(cipher.length);this.run('INSERT INTO messages VALUES (?,?,?,?,?)',id,metadata.domain,metadata.timestamp,metadata.receivedAt,cipher);return id;}
 message(id){const r=this.get('SELECT cipher FROM messages WHERE id=?',id);return r?this.open(r.cipher,'message:'+id):null;}
 job(id,fields){this.run('INSERT INTO jobs VALUES (?,?,?,?,?,?,?) ON CONFLICT(id) DO NOTHING',id,fields.market,fields.source,fields.emailId,'queued',null,Date.now());}
 jobState(id,state,code=null){this.run('UPDATE jobs SET state=?,code=?,updated_at=? WHERE id=?',state,code,Date.now(),id);}
 action(id){const r=this.get('SELECT * FROM actions WHERE id=?',id);return r?{...r,payload:this.open(r.cipher,'action:'+id)}:null;}
 saveAction(id,jobId,state,nonce,payload){const cipher=this.seal(payload,'action:'+id);this.ensureCapacity(cipher.length);this.run('INSERT INTO actions VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET state=excluded.state,cipher=excluded.cipher,updated_at=excluded.updated_at',id,jobId,state,nonce,cipher,Date.now());}
 counts(){return {messages:this.get('SELECT count(*) AS n FROM messages').n,markets:this.get('SELECT count(*) AS n FROM markets').n,jobs:this.all('SELECT state,count(*) AS count FROM jobs GROUP BY state'),transactions:this.all('SELECT state,count(*) AS count FROM actions GROUP BY state')};}
 close(){this.db.close();this.key.fill(0);}
}
