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
