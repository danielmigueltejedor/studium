// Audio-specific adaptation of the upstream depth/length contract; see vendor/studium/README.md.
import {FRAMEWORK,PROFILES} from './studium-python.js';
export {FRAMEWORK,PROFILES};
let worker,serial=0;const pending=new Map();
export function fallbackScope(spec){const p=PROFILES[spec.profile],level=p.academic_level,c=spec.complexity>0?spec.complexity:1,factor=({CONCISE:.5,STANDARD:.75,COMPREHENSIVE:1,EXHAUSTIVE:1.5,AUTO:1})[spec.preference]||1;const b={concepts:spec.concepts*p.pages_per_concept*c,derivations:spec.derivations*p.derivation_pages_per_item*c,worked_examples:spec.worked_examples*(.35+.1*level)*c,exercises:spec.exercises*(.06+.015*level),figures:(spec.figures||0)*.14,references:(spec.sources||0)*.03,front_and_back_matter:6+spec.chapters*1.2};const total=Object.values(b).reduce((n,x)=>n+x,0)*factor;return {scope:{estimate:total,floor:total*.75,ceiling:total*1.35,preference:spec.preference,breakdown:b},profile:p,framework:{...FRAMEWORK,runtime:'javascript-adapter',checks:['depth_scope'],expertReview:'PENDING'}};}
export async function planStudiumScope(spec,{signal,onProgress=()=>{}}={}){
 if(signal?.aborted)throw new DOMException('Operación cancelada.','AbortError');
 if(typeof Worker==='undefined')return fallbackScope(spec);
 onProgress('Preparando la planificación de Studium en tu dispositivo…');
 try{
  if(!worker){worker=new Worker('./studium-engine-worker.js',{type:'module'});worker.onmessage=({data:m})=>{const p=pending.get(m.id);if(!p)return;pending.delete(m.id);m.error?p.reject(Error(m.error)):p.resolve(m.result);};worker.onerror=()=>{for(const p of pending.values())p.reject(Error('No se pudo cargar la planificación Python.'));pending.clear();worker?.terminate();worker=null;};}
  const id=++serial;return await new Promise((resolve,reject)=>{let timer;const cleanup=()=>{clearTimeout(timer);signal?.removeEventListener('abort',abort);pending.delete(id);};const abort=()=>{cleanup();reject(new DOMException('Operación cancelada.','AbortError'));};pending.set(id,{resolve:r=>{cleanup();resolve(r);},reject:e=>{cleanup();reject(e);}});signal?.addEventListener('abort',abort,{once:true});timer=setTimeout(()=>{cleanup();reject(Error('No se pudo preparar el motor Python a tiempo.'));},45000);worker.postMessage({id,spec});});
 }catch(error){if(signal?.aborted)throw error;onProgress('Usando el adaptador local de planificación de Studium.');return {...fallbackScope(spec),framework:{...FRAMEWORK,runtime:'javascript-adapter',checks:['depth_scope'],expertReview:'PENDING',notice:'El módulo Python no pudo cargarse; se utilizó el adaptador local de planificación.'}};}
}
