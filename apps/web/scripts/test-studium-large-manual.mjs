import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {loadPyodide} from 'pyodide';
import {initializeStudiumCore} from '../public/studium-core-native.js';
const core=await initializeStudiumCore(loadPyodide,new URL('../node_modules/pyodide/',import.meta.url).pathname,{packageBaseUrl:'https://cdn.jsdelivr.net/pyodide/v0.29.3/full/',bridgeSource:await readFile(new URL('../public/studium-core-bridge.txt',import.meta.url),'utf8')});
for(const count of [40,41,52,201]){
 const snippets=Array.from({length:count},(_,i)=>`Unidad ${i+1}. La inspección documenta el estado superficial del material. El historial conserva las intervenciones autorizadas.\n\n`),text=snippets.join('');let from=0;
 const segments=snippets.map((s,i)=>{const unit={id:'chapter-'+(i+1),title:'Unidad '+(i+1),from,to:from+s.length};from+=s.length;return unit;});
 const prepared=await core.call('prepare',{id:'large-'+count,title:'Manual extenso',subject:'Materiales',text,segments});
 assert.equal(prepared.bridgeVersion,2);assert.equal(prepared.blueprint.status,'recorded');assert.equal(prepared.academicBlueprint.status,'recorded');assert.equal(prepared.plan.status,'planned');assert.equal(prepared.placements.length,count);
 // Native paragraph registration is the authority: every placement must exist,
 // including chapters across the 40 boundary and sections grouped above 200.
 const units=segments.map((s,i)=>({id:'turn-'+i,segmentId:s.id,kind:'podcast',text:'La inspección documenta el estado superficial del material. El historial conserva las intervenciones autorizadas.',quotes:['La inspección documenta el estado superficial del material.','El historial conserva las intervenciones autorizadas.']}));
 const registered=await core.call('record',{id:'large-'+count,files:prepared.files,units});
 assert.equal(registered.results.length,count);assert(registered.results.every(r=>r.status==='recorded'));assert(registered.results.every(r=>r.paragraph.excerpts.length===2));assert.equal(registered.report.released,false);
 console.log('Native hierarchy and both citations registered for',count,'source segments');
 if(count===41){const bad=await core.call('record',{id:'large-'+count,files:registered.files,units:[{...units[0],id:'invalid-secondary',quotes:[units[0].quotes[0],'La densidad mide la temperatura.']}]});assert.equal(bad.results[0].status,'rejected');assert.equal(bad.results[0].excerpt.status,'excerpt.not_in_source');const repeat=await core.call('record',{id:'large-'+count,files:registered.files,units:[units[0]]});assert.equal(repeat.results[0].status,'already_recorded');}
}
await assert.rejects(()=>core.call('prepare',{id:'invalid-structure',title:'Manual',subject:'Materiales',text:'Una fuente que debe conservar sus límites.',segments:[{id:'unit-1',title:'Unidad',from:0,to:40}],depth:'UNKNOWN'}),/rejected the academic structure/);
console.log('Preparation errors stop before content generation; original framework checks remain unchanged.');
