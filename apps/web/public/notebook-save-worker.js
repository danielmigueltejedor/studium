import {setWorkerAccountScope} from './account-session.js';
import {persistNotebookChanges} from './notebook-persistence.js';
let chain=Promise.resolve();self.onmessage=({data:{id,job}})=>{chain=chain.catch(()=>{}).then(async()=>{try{setWorkerAccountScope(job.accountId||null);self.postMessage({id,result:await persistNotebookChanges(job)});}catch(error){self.postMessage({id,error:error.message});}});};
