// Reference IDs point to exact spans owned by the app, never model-written quotes.
export function podcastEvidenceCatalog(source,prefix){
 if(typeof source!=='string'||typeof prefix!=='string'||!/^[A-Za-z0-9_-]{1,100}$/.test(prefix))throw Error('La fuente del podcast no tiene un identificador válido.');
 const entries=[];let from=0;
 while(from<source.length){let to=Math.min(source.length,from+240);if(to<source.length){const part=source.slice(from,to),boundary=Math.max(part.lastIndexOf('. ')+1,part.lastIndexOf('\n\n'),part.lastIndexOf(' '));if(boundary>=120)to=from+boundary;if(source.length-to<50&&source.length-from<=290)to=source.length;}const raw=source.slice(from,to),quote=raw.trim();if(quote){const start=from+raw.indexOf(quote);entries.push({id:prefix+'-E'+String(entries.length+1).padStart(4,'0'),from:start,to:start+quote.length,quote});}from=to;}
 return entries;
}
export function podcastSourceText(source,section){return section?.evidenceVersion===2?podcastEvidenceCatalog(source,section.evidenceId).map(e=>`[${e.id}]\n${e.quote}`).join('\n\n'):source;}
function normalizedWithOffsets(text){let normalized='',starts=[],ends=[];for(const match of text.matchAll(/[^\p{M}]\p{M}*|\p{M}+/gu)){const value=match[0].normalize('NFKC').replace(/[\u00ad\u200b\ufeff]/g,'').replace(/[\u2018\u2019]/g,"'").replace(/[\u201c\u201d]/g,'"');for(const char of value){if(/\s/u.test(char)){if(!normalized||normalized.endsWith(' ')){if(normalized)ends[ends.length-1]=match.index+match[0].length;continue;}normalized+=' ';starts.push(match.index);ends.push(match.index+match[0].length);}else{normalized+=char;for(let n=0;n<char.length;n++){starts.push(match.index);ends.push(match.index+match[0].length);}}}}if(normalized.endsWith(' ')){normalized=normalized.slice(0,-1);starts.pop();ends.pop();}return {text:normalized,starts,ends};}
export function resolvePodcastEvidence(evidence,source,section,catalog=podcastEvidenceCatalog(source,section.evidenceId),normalizedSource){
 if(!evidence||typeof evidence.id!=='string')throw Error('Falta una referencia válida del manual. Selecciona un identificador de los fragmentos proporcionados.');
 const entry=catalog.find(e=>e.id===evidence.id);
 if(entry)return {...entry,status:'EVIDENCE_LOCATED',match:'EXCERPT_ID',semanticSupport:'PENDING'};
 // Old drafts/responses remain readable. Only formatting-equivalent literal quotes
 // are accepted, and the stored quote/offset always comes from the original text.
 if(evidence.id!==section.evidenceId||typeof evidence.quote!=='string')throw Error('Una referencia no existe en este bloque del manual. Usa únicamente los identificadores proporcionados.');
 const quoted=normalizedWithOffsets(evidence.quote).text,normalized=normalizedSource||normalizedWithOffsets(source),at=normalized.text.indexOf(quoted);
 if(quoted.length<20||quoted.length>300||at<0)throw Error('Una cita no se encuentra en el fragmento original. Selecciona sus identificadores, sin reescribir ni inventar la cita.');
 const from=normalized.starts[at],to=normalized.ends[at+quoted.length-1];return {id:evidence.id,quote:source.slice(from,to),from,to,status:'EVIDENCE_LOCATED',match:'LITERAL_FORMAT_NORMALIZED',semanticSupport:'PENDING'};
}
export function podcastEvidenceResolver(source,section){const catalog=podcastEvidenceCatalog(source,section.evidenceId),normalized=normalizedWithOffsets(source);return evidence=>resolvePodcastEvidence(evidence,source,section,catalog,normalized);}

// Models sometimes put source IDs in speech as well as in the evidence field.
// Move only validated app references to metadata before checking spoken numbers.
// Bare numbers, unknown IDs and technical codes present in the source stay subject
// to validation; there is no blanket exception for zero-padded numeric values.
export function separatePodcastReferences(text,evidence,source,section){
 if(evidence!==undefined&&!Array.isArray(evidence))throw Error('La evidencia de una intervención no tiene un formato válido.');
 const catalog=podcastEvidenceCatalog(source,section.evidenceId),known=new Map(catalog.map(e=>[e.id.toLowerCase(),e.id])),refs=[...(evidence||[])],detached=[];
 const escaped=section.evidenceId.replace(/[.*+?^${}()|[\]\\]/g,'\\$&');
 const tokens=new RegExp('(?<![\\p{L}\\p{N}_-])(?:'+escaped+'(?:-E[0-9]+)?|SRC-[A-Za-z0-9_-]+)(?![\\p{L}\\p{N}_-])','giu');
 function detach(id){
  if(source.includes(id))return id;
  const canonical=known.get(id.toLowerCase());
  if(canonical){refs.push({id:canonical});detached.push(canonical);return '';}
  if(id.toLowerCase()===section.evidenceId.toLowerCase()){detached.push(section.evidenceId);return '';}
  throw Error('Una referencia incluida en el diálogo no existe en este bloque del manual. Usa únicamente sus identificadores.');
 }
 const speech=text.replace(/\[([^\[\]\r\n]*)\]|\(([^()\r\n]*)\)|【([^【】\r\n]*)】/g,(whole,...groups)=>{
  const content=groups.slice(0,3).find(s=>s!==undefined),ids=content.match(tokens)||[];
  if(!ids.length||ids.some(id=>source.includes(id)))return whole;
  const withoutFull=content.replace(tokens,''),shorts=withoutFull.match(/(?<![\p{L}\p{N}_-])-?E[0-9]+(?![\p{L}\p{N}_-])/giu)||[];
  const residue=withoutFull.replace(/(?<![\p{L}\p{N}_-])-?E[0-9]+(?![\p{L}\p{N}_-])/giu,'').replace(/\b(?:fuentes?|refs?|referencias?|evidencias?|source|sources|references?|ver|véase|véanse|y|e|and)\b\.?/giu,'').replace(/[\s,;:|/\[\]()【】–—-]/g,'');
  if(residue)return whole;
  for(const id of ids)detach(id);
  for(const short of shorts)detach(section.evidenceId+'-'+short.replace(/^-/,'').toUpperCase());
  return '';
 }).replace(tokens,detach).replace(/[ \t]+([,.;:!?])/g,'$1').replace(/[ \t]{2,}/g,' ').trim();
 const unique=[...new Map(refs.map(e=>[JSON.stringify(e),e])).values()];
 return {text:speech,evidence:unique,detachedReferences:[...new Set(detached)]};
}
