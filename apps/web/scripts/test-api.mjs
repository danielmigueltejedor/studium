import assert from 'node:assert/strict';
import worker from '../worker/index.js';
let last=null;const original=globalThis.fetch;
const request=(path,body={},extra={})=>new Request('https://studium.test'+path,{method:'POST',headers:{'Content-Type':'application/json',Authorization:'Bearer test-only-key',Origin:'https://studium.test',...extra},body:JSON.stringify(body)});
const base={provider:'openrouter',model:'openrouter/free',mode:'deck',title:'Biología',text:'Las células son la unidad básica de la vida. Los ribosomas sintetizan proteínas.',num:6,freeOnly:true};
try{
 let r=await worker.fetch(new Request('https://studium.test/api/generate',{method:'POST',headers:{'Content-Type':'application/json'},body:'{}'}));assert.equal(r.status,401);
 r=await worker.fetch(request('/api/generate',base,{Origin:'https://attacker.test'}));assert.equal(r.status,403);
 r=await worker.fetch(request('/api/generate',{...base,provider:'openai',model:'gpt-4.1-mini'}));assert.equal(r.status,400);
 r=await worker.fetch(request('/api/generate',{...base,model:'openai/gpt-4.1-mini'}));assert.equal(r.status,400);
 r=await worker.fetch(request('/api/generate',{...base,provider:'opencode',model:'big-pickle'}));assert.equal(r.status,403);assert.match((await r.json()).error,/solo se pueden usar dentro de OpenCode/);
 globalThis.fetch=async(url,opts)=>{last={url,opts,body:opts.body?JSON.parse(opts.body):null};return Response.json({choices:[{message:{content:'{"cards":[{"q":"¿Qué sintetizan los ribosomas?","a":"Proteínas"}]}'},finish_reason:'stop'}]});};
 r=await worker.fetch(request('/api/generate',base));assert.equal(r.status,200);assert.match((await r.json()).text,/Proteínas/);assert.equal(last.url,'https://openrouter.ai/api/v1/chat/completions');assert.equal(last.body.model,'openrouter/free');assert.equal(last.body.models,undefined);assert.equal(last.opts.headers.Authorization,'Bearer test-only-key');assert.equal(last.opts.redirect,'manual');
 globalThis.fetch=async(url,opts)=>{last={url,opts,body:JSON.parse(opts.body)};return Response.json({candidates:[{content:{parts:[{text:'Guion de prueba'}]}}]});};
 r=await worker.fetch(request('/api/generate',{...base,provider:'gemini',model:'gemini-2.5-flash-lite',mode:'podcast'}));assert.equal(r.status,200);assert.equal((await r.json()).text,'Guion de prueba');assert.equal(last.opts.headers['x-goog-api-key'],'test-only-key');assert.match(last.url,/:generateContent$/);
 const wave=new Uint8Array(100);wave.set([82,73,70,70],0);wave.set([87,65,86,69],8);const audio64=Buffer.from(wave).toString('base64');
 globalThis.fetch=async(url,opts)=>{last={url,body:JSON.parse(opts.body)};return Response.json({candidates:[{content:{parts:[{inlineData:{mimeType:'audio/wav',data:audio64}}]}}]});};
 r=await worker.fetch(request('/api/audio',{provider:'gemini',model:'gemini-3.8-flash-lite-tts',text:'Ana: Hola, repasamos biología.\nLeo: Claro, vamos allá.',voice:'Kore',voice2:'Puck',freeOnly:true}));assert.equal(r.status,200);assert.equal(r.headers.get('Content-Type'),'audio/wav');assert.equal(Buffer.from(await r.arrayBuffer()).toString('ascii',0,4),'RIFF');assert.equal(last.body.generationConfig.speechConfig.multiSpeakerVoiceConfig.speakerVoiceConfigs.length,2);assert.equal(last.body.contents[0].parts[1].speech_metadata.speaker,'Leo');assert.match(last.url,/:generateContent$/);
 globalThis.fetch=async()=>Response.json({candidates:[{content:{parts:[{inlineData:{mimeType:'audio/L16;rate=24000',data:Buffer.from(new Uint8Array(480)).toString('base64')}}]}}]});
 r=await worker.fetch(request('/api/audio',{provider:'gemini',model:'gemini-2.5-flash-preview-tts',text:'Ana: Hola, repasamos biología.\nLeo: Vamos.',voice:'Kore',voice2:'Puck'}));const wav=new DataView(await r.arrayBuffer());assert.equal(wav.getUint32(24,true),24000);assert.equal(wav.getUint32(40,true),480);
 globalThis.fetch=async()=>new Response('fake mp3 data',{headers:{'Content-Type':'audio/mpeg'}});
 r=await worker.fetch(request('/api/audio',{provider:'openai',model:'gpt-4o-mini-tts-2025-12-15',text:'Hola, esto es una prueba de audio.',voice:'coral',freeOnly:false}));assert.equal(r.status,200);assert.equal(r.headers.get('Content-Type'),'audio/mpeg');
 globalThis.fetch=async()=>new Response('Secret provider details',{status:429});r=await worker.fetch(request('/api/generate',base));assert.equal(r.status,429);assert.doesNotMatch(await r.text(),/test-only-key|Secret provider/);
 // Exercise the catalog, the failing path in the hosted app. Reject redirect modes Workers cannot run.
 for(const provider of ['gemini','groq','openrouter','openai']){
  let calls=0;
  globalThis.fetch=async(url,opts)=>{
   calls++;assert.equal(opts.redirect,'manual','Cloudflare Workers does not support redirect:error');
   assert(opts.signal instanceof AbortSignal);
   if(provider==='gemini'){
    assert.equal(url,'https://generativelanguage.googleapis.com/v1beta/models');
    assert.equal(opts.method,'GET');assert.equal(opts.headers['x-goog-api-key'],'test-only-key');assert.equal(opts.headers.Authorization,undefined);
    return Response.json({models:[{name:'models/gemini-text',displayName:'Gemini texto',supportedGenerationMethods:['generateContent']},{name:'models/embedding',supportedGenerationMethods:['embedContent']}]});
   }
   if(url.endsWith('/key'))return Response.json({data:{}});
   return Response.json({data:[{id:provider==='openrouter'?'openrouter/free':'test-model'},{id:'paid-model'}]});
  };
  const response=await worker.fetch(request('/api/models',{provider,freeOnly:true}));assert.equal(response.status,200);
  const {models}=await response.json();assert(models.length);
  if(provider==='gemini')assert.deepEqual(models.map(m=>m.id),['gemini-text']);
  assert.equal(calls,provider==='openrouter'?2:1);
 }
 for(const [upstreamStatus,payload,expected,pattern] of [
  [400,{status:'INVALID_ARGUMENT',message:'API key not valid',details:[{reason:'API_KEY_INVALID'}]},401,/clave API no es válida/],
  [400,{details:[{reason:'API_KEY_EXPIRED'}]},401,/caducado/],
  [401,{status:'UNAUTHENTICATED'},401,/clave API no es válida/],
  [403,{message:'Your API key was reported as leaked.'},401,/Google ha bloqueado/],
  [403,{status:'PERMISSION_DENIED'},403,/acceso a la API de Gemini/],
  [429,{status:'RESOURCE_EXHAUSTED'},429,/cuota/],
  [400,{status:'INVALID_ARGUMENT'},400,/no acepta la solicitud/],
  [503,{status:'UNAVAILABLE'},502,/503/],
 ]){
  globalThis.fetch=async()=>Response.json({error:{...payload,private:'test-only-key'}},{status:upstreamStatus});
  const response=await worker.fetch(request('/api/models',{provider:'gemini'}));assert.equal(response.status,expected);
  const body=await response.json();assert.match(body.error,pattern);assert.doesNotMatch(body.error,/test-only-key|UNAUTHENTICATED|PERMISSION_DENIED/);
 }
 for(const status of [302,307]){
  let calls=0;globalThis.fetch=async(url,opts)=>{calls++;assert.equal(opts.redirect,'manual');return new Response(null,{status,headers:{Location:'https://untrusted.test/?key=test-only-key'}});};
  const response=await worker.fetch(request('/api/models',{provider:'gemini'}));assert.equal(response.status,502);assert.equal(calls,1);
  const body=await response.text();assert.match(body,/redirección no admitida/);assert.doesNotMatch(body,/untrusted|test-only-key/);
 }
 console.log('API checks passed: Workers-compatible requests, Gemini catalog and authentication errors, redirect refusal, free-only rules, text and WAV/MP3 audio. No live credentials used.');
}finally{globalThis.fetch=original;}
