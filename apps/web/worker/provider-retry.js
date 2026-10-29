// Return only safe, typed quota metadata; never upstream messages/project IDs.
export function quotaDetails(error,retryAfter){
 const details=Array.isArray(error?.details)?error.details:[],violations=details.filter(d=>String(d['@type']||'').endsWith('QuotaFailure')).flatMap(d=>Array.isArray(d.violations)?d.violations:[]);
 const ids=violations.map(v=>String(v.quotaId||v.quota_id||'')),daily=ids.some(id=>/perday|daily/i.test(id)),longTerm=ids.some(id=>/permonth|peryear/i.test(id)),zero=violations.some(v=>String(v.quotaValue??v.quota_value)==='0');
 const quotaWindow=zero?'unavailable':daily?'day':longTerm?'long_term':ids.some(id=>/perminute|persecond/i.test(id))?'minute':'unknown';
 const duration=details.find(d=>String(d['@type']||'').endsWith('RetryInfo'))?.retryDelay,match=typeof duration==='string'?duration.match(/^(\d+(?:\.\d+)?)s$/):null;
 const seconds=match?Number(match[1]):/^\d+(?:\.\d+)?$/.test(retryAfter||'')?Number(retryAfter):undefined;
 return {quotaWindow,...(Number.isFinite(seconds)&&seconds>0&&seconds<=86400?{retryAfterSeconds:seconds}:{})};
}
function pause(ms,signal){return new Promise((resolve,reject)=>{if(signal?.aborted){reject(new DOMException('Audio pausado.','AbortError'));return;}const done=()=>{signal?.removeEventListener('abort',abort);resolve();},timer=setTimeout(done,ms),abort=()=>{clearTimeout(timer);signal?.removeEventListener('abort',abort);reject(new DOMException('Audio pausado.','AbortError'));};signal?.addEventListener('abort',abort,{once:true});});}
export async function retryAudioRequest(send,{signal,sleep=pause}={}){
 let waited=0;
 for(let attempt=0;;attempt++){
  if(signal?.aborted)throw new DOMException('Audio pausado.','AbortError');
  try{return await send();}catch(error){
   const delay=Number(error.retryAfterSeconds)*1000*2**attempt;
   if(error.upstreamStatus!==429||attempt>=2||!['minute','unknown'].includes(error.quotaWindow)||!Number.isFinite(delay)||delay<=0||delay>60000||waited+delay>90000)throw error;
   await sleep(delay,signal);waited+=delay;
  }
 }
}
