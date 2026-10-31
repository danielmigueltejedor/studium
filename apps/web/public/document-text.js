import {getAsset,putAsset,deleteAssets} from './storage.js';

// The library index holds a preview. Full document bodies live in IndexedDB.
export const TEXT_PREVIEW=1200;
export const EDITOR_PREVIEW=30000;
export function wordCount(text){let count=0;const words=/\S+/g;while(words.exec(text))count++;return count;}
export function compactText(item,textKey){return {...item,...(item.type==='book'?{chapters:(item.chapters||[]).map(({text,...chapter})=>chapter)}:{}),text:item.text.slice(0,TEXT_PREVIEW),textKey,chars:item.text.length,words:wordCount(item.text)};}
export async function readDocumentText(item){if(!item)throw Error('El documento ya no está en tu biblioteca.');if(!item.textKey)return item.text||'';const asset=await getAsset(item.textKey);if(typeof asset?.data?.text!=='string')throw Error('No se encuentra el texto completo. Restaura una copia de seguridad o vuelve a adjuntar el archivo.');return asset.data.text;}
export async function hydrateDocument(item){const text=await readDocumentText(item),asset=item.type==='book'&&item.textKey?await getAsset(item.textKey):null;return {...item,text,...(asset?.data?.chapters?{chapters:asset.data.chapters}:{})};}
export async function saveDocument(item,commit){
 if(!['note','podcast','book'].includes(item.type))return commit(item);
 const key='text:'+item.id,large=item.type==='book'||item.text.length>TEXT_PREVIEW;
 const previous=large?await getAsset(key):null;
 const metadata=large?compactText(item,key):{...item,textKey:undefined,chars:item.text.length,words:wordCount(item.text)};
 if(large)await putAsset(key,'text',{text:item.text,...(item.type==='book'?{chapters:item.chapters||[]}: {})});
 try{if(!await commit(metadata))throw Error('No se pudo guardar el documento en la biblioteca.');}
 catch(error){if(large){if(previous)await putAsset(key,previous.kind,previous.data);else await deleteAssets([key]);}throw error;}
 if(!large)await deleteAssets([key]).catch(()=>{});
 return metadata;
}
