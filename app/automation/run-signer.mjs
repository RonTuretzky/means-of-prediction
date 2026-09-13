import { privateKeyToAccount } from 'viem/accounts';
import { Store } from './store.mjs';
import { readPrivate } from './config.mjs';
import { RestrictedSigner } from './signer.mjs';
import { serveSigner } from './signer-ipc.mjs';
import { safeCode } from './errors.mjs';
process.umask(0o077);
try{
 const c=JSON.parse(readPrivate(process.env.MOP_SIGNER_CONFIG));
 const account=privateKeyToAccount(readPrivate(c.privateKeyFile)),store=new Store(c.database,Buffer.from(readPrivate(c.storageKeyFile),'hex'));
 const signer=new RestrictedSigner({account,store,config:c});
 const server=await serveSigner(c.socketPath,signer);
 console.log(JSON.stringify({event:'signer_started',address:account.address,chainId:c.chainId}));
 for(const signal of ['SIGTERM','SIGINT'])process.once(signal,()=>server.close(()=>{store.close();process.exit(0);}));
}catch(e){console.error(JSON.stringify({event:'signer_failed',code:safeCode(e)}));process.exitCode=1;}
