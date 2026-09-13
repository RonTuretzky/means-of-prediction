import { ImapFlow } from 'imapflow';
import { openMailbox, selectMailboxes, requireGmailCoverage } from '../scripts/mailbox.mjs';
import { digest } from './store.mjs';
import { ServiceError, safeCode, fail } from './errors.mjs';
export class MailboxWorker {
 constructor({store,collector,config,connect=options=>openMailbox(options,ImapFlow)}){Object.assign(this,{store,collector,config,connect});}
 async poll(){let client;let caughtUp=true;let fetched=0;
  try{
   client=await this.connect(this.config.mailbox);const list=await client.list();requireGmailCoverage(list,this.config.mailbox);
   const scope=digest(JSON.stringify({host:this.config.mailbox.host,user:this.config.mailbox.user,from:this.config.discoveryFrom,domains:this.config.allowedDkimDomains,fromDomains:this.config.allowedFromDomains}));
   for(const box of selectMailboxes(list,this.config.mailbox.mailboxes)){
    const lock=await client.getMailboxLock(box.path,{readOnly:true});
    try{
     const validity=String(client.mailbox.uidValidity),cursorKey='imap:'+scope+':'+digest(box.path),old=this.store.getMeta(cursorKey);
     const last=old?.validity===validity?old.uid:0,highest=Number(client.mailbox.uidNext)-1;
     if(!Number.isSafeInteger(highest)||highest<0)fail('mailbox_invalid_cursor');
     if(highest<=last)continue;
     const upper=Math.min(highest,last+this.config.uidBatch),found=(await client.search({uid:`${last+1}:${upper}`,or:this.config.discoveryFrom.map(from=>({from}))},{uid:true}))||[];
     const ordered=found.filter(uid=>uid>last&&uid<=upper).sort((a,b)=>a-b),selected=ordered.slice(0,this.config.messagesPerPoll);
     for(const uid of selected){
      const meta=await client.fetchOne(String(uid),{uid:true,size:true,labels:true,flags:true},{uid:true});
      if(!meta) {this.store.setMeta(cursorKey,{validity,uid});continue;}
      if(!meta.flags?.has('\\Draft')&&!meta.labels?.has('\\Sent')&&!meta.labels?.has('\\Drafts')&&meta.size<=this.config.maxMessageBytes){
       const mail=await client.fetchOne(String(uid),{source:{start:0,maxLength:this.config.maxMessageBytes+1},internalDate:true},{uid:true});
       if(!mail?.source)fail('mailbox_source_unavailable');
       try{await this.collector.ingest(mail.source,mail.internalDate?new Date(mail.internalDate).getTime():Date.now());fetched++;}
       catch(e){if(!(e instanceof ServiceError)||e.status>=500)throw e;this.store.setMeta('last-rejected-code',safeCode(e));}
      }else if(meta.size>this.config.maxMessageBytes)this.store.setMeta('last-rejected-code','email_too_large');
      // Commit only after durable ingestion/rejection. Transient errors leave this UID pending.
      this.store.setMeta(cursorKey,{validity,uid});
     }
     const advanced=ordered.length>selected.length?selected.at(-1):upper;
     this.store.setMeta(cursorKey,{validity,uid:advanced});
     if(advanced<highest)caughtUp=false;
    }finally{lock.release();}
   }
   this.store.setMeta('mailbox-caught-up',caughtUp);this.store.health('mailbox',true);return {caughtUp,fetched};
  }catch(e){this.store.setMeta('mailbox-caught-up',false);this.store.health('mailbox',false,safeCode(e));return {caughtUp:false,fetched,error:safeCode(e)};}
  finally{if(client)try{await client.logout();}catch{client.close();}}
 }
}
