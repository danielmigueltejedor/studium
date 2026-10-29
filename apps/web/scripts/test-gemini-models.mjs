import assert from 'node:assert/strict';
import worker from '../worker/index.js';
const original=globalThis.fetch;
const request=(path,body)=>new Request('https://studium.test/api/'+path,{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer test-only-key'},body:JSON.stringify({provider:'gemini',model:'auto',freeOnly:true,...body})});
const base={mode:'podcast',num:6,title:'Biología',text:'Las células son la unidad básica de la vida. Los ribosomas sintetizan proteínas.'};
const model=id=>({name:'models/'+id,displayName:id,supportedGenerationMethods:['generateContent']});
const catalog=[model('gemini-3.8-flash'),model('gemini-3.8-flash-lite-tts'),model('gemini-2.5-flash-preview-tts'),model('gemini-3.8-pro'),model('gemini-live-audio'),model('gemini-flash-image'),{name:'models/embedding',supportedGenerationMethods:['embedContent']}];
const script='Ana: Hoy repasamos la célula.\nLeo: Los ribosomas sintetizan proteínas.';
const textResponse=()=>Response.json({candidates:[{finishReason:'STOP',content:{parts:[{text:'Razonamiento interno',thought:true},{text:script}]}}]});
const wav=new Uint8Array(128);wav.set([82,73,70,70]);wav.set([87,65,86,69],8);
const audioResponse=()=>Response.json({candidates:[{content:{parts:[{inlineData:{mimeType:'audio/wav',data:Buffer.from(wav).toString('base64')}}]}}]});
let calls=[];
const record=(url,init)=>{assert.equal(init.redirect,'manual');assert.equal(init.headers['x-goog-api-key'],'test-only-key');calls.push({url,body:init.body?JSON.parse(init.body):null});};
try{
 globalThis.fetch=async(url,init)=>{record(url,init);return Response.json({models:catalog});};
 let r=await worker.fetch(request('models',{})),data=await r.json();assert.equal(r.status,200);assert.deepEqual(data.models.map(m=>m.id),['gemini-3.8-flash','gemini-3.8-pro']);assert.equal(data.recommendedModel,'gemini-3.8-flash');assert.equal(data.models[0].free,null);
 r=await worker.fetch(request('models',{purpose:'audio'}));data=await r.json();assert.deepEqual(data.models.map(m=>m.id),['gemini-3.8-flash-lite-tts','gemini-2.5-flash-preview-tts']);
 // All catalog pages are read; models may appear after an initial page of embeddings.
 calls=[];globalThis.fetch=async(url,init)=>{record(url,init);if(url.includes('pageToken='))return Response.json({models:[model('gemini-3.8-flash')]});if(init.method==='GET')return Response.json({models:[],nextPageToken:'page two /+'});return textResponse();};
 r=await worker.fetch(request('generate',base));data=await r.json();assert.equal(r.status,200);assert.equal(data.text,script);assert.equal(data.model,'gemini-3.8-flash');assert(!data.text.includes('interno'));assert(calls.some(c=>c.url.endsWith('pageToken=page%20two%20%2F%2B')));
 // Repair saved old settings after an actual 404; keep the complete source and podcast instructions.
 calls=[];globalThis.fetch=async(url,init)=>{record(url,init);if(url.includes('gemini-2.5-flash-lite:'))return Response.json({error:{status:'NOT_FOUND'}},{status:404});if(init.method==='GET')return Response.json({models:catalog});return textResponse();};
 r=await worker.fetch(request('generate',{...base,model:'gemini-2.5-flash-lite'}));data=await r.json();assert.equal(r.status,200);assert.equal(data.modelChanged,true);assert.equal(data.model,'gemini-3.8-flash');assert.equal(calls.filter(c=>c.body).length,2);assert(calls.at(-1).body.contents[0].parts[0].text.includes(base.text));assert(calls.at(-1).body.systemInstruction.parts[0].text.includes('podcast'));
 // A voice model accidentally saved for text is never asked to write the script.
 calls=[];r=await worker.fetch(request('generate',{...base,model:'gemini-3.8-flash-lite-tts'}));assert.equal(r.status,200);assert(!calls.some(c=>c.body&&c.url.includes('tts:')));
 // Do not retry exhausted quota, rejected keys, or invalid requests with a different model.
 for(const status of [400,401,403,429]){calls=[];globalThis.fetch=async(url,init)=>{record(url,init);return Response.json({error:{}},{status});};r=await worker.fetch(request('generate',{...base,model:'gemini-3.8-flash'}));assert.equal(r.status,status);assert.equal(calls.length,1);}
 // A Pro-only account is not switched automatically to a potentially more expensive model.
 calls=[];globalThis.fetch=async(url,init)=>{record(url,init);return Response.json({models:[model('gemini-3.8-pro')]});};r=await worker.fetch(request('generate',base));assert.equal(r.status,422);assert(calls.every(c=>!c.body));
 // Automatic two-speaker WAV uses an available TTS model and its current request format.
 calls=[];globalThis.fetch=async(url,init)=>{record(url,init);if(init.method==='GET')return Response.json({models:catalog});return audioResponse();};
 r=await worker.fetch(request('audio',{text:script,voice:'Kore',voice2:'Puck'}));assert.equal(r.status,200);assert.equal(r.headers.get('X-Studium-Model'),'gemini-3.8-flash-lite-tts');assert.equal(Buffer.from(await r.arrayBuffer()).toString('ascii',0,4),'RIFF');const audioCall=calls.at(-1);assert.match(audioCall.url,/gemini-3.8-flash-lite-tts:generateContent$/);assert.equal(audioCall.body.contents[0].parts[0].speech_metadata.speaker,'Ana');assert.equal(audioCall.body.contents[0].parts[1].speech_metadata.speaker,'Leo');assert.equal(audioCall.body.generationConfig.speechConfig.multiSpeakerVoiceConfig.speakerVoiceConfigs.length,2);
 // A retired TTS model is repaired independently of the text model.
 calls=[];globalThis.fetch=async(url,init)=>{record(url,init);if(url.includes('gemini-2.5-flash-preview-tts:'))return Response.json({error:{}},{status:404});if(init.method==='GET')return Response.json({models:catalog});return audioResponse();};r=await worker.fetch(request('audio',{model:'gemini-2.5-flash-preview-tts',text:script}));assert.equal(r.status,200);assert.equal(r.headers.get('X-Studium-Model'),'gemini-3.8-flash-lite-tts');assert.equal(calls.filter(c=>c.body).length,2);
 // Pasting the provider's models/ prefix must not turn it into an encoded slash in the endpoint.
 calls=[];globalThis.fetch=async(url,init)=>{record(url,init);return textResponse();};r=await worker.fetch(request('generate',{...base,model:'models/gemini-3.8-flash'}));assert.equal(r.status,200);assert(!calls[0].url.includes('%2F'));
 console.log('Gemini model checks passed: catalog pagination, automatic text/voice selection, stale model repair, quota/auth preservation, source fidelity, current two-speaker WAV format. No live credentials used.');
}finally{globalThis.fetch=original;}
