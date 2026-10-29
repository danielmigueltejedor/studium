import {assetsDatabase} from './account-session.js';
let dbPromise;
function db(){if(!dbPromise)dbPromise=new Promise((resolve,reject)=>{const r=indexedDB.open(assetsDatabase(),1);r.onupgradeneeded=()=>r.result.createObjectStore('assets',{keyPath:'id'});r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(Error('No se pudo abrir el almacenamiento de documentos, cuadernos y audio.'));});return dbPromise;}
export async function putAsset(id,kind,data,revision=crypto.randomUUID()){const d=await db();return new Promise((resolve,reject)=>{const t=d.transaction('assets','readwrite');t.objectStore('assets').put({id,kind,data,revision});t.oncomplete=()=>resolve();t.onerror=()=>reject(Error('No queda espacio para guardar. Exporta tus archivos y libera almacenamiento.'));t.onabort=()=>reject(Error('No se pudo guardar el archivo.'));});}
export async function getAsset(id){const d=await db();return new Promise((resolve,reject)=>{const r=d.transaction('assets').objectStore('assets').get(id);r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(Error('No se pudo leer el archivo guardado.'));});}
export async function allAssets(){const d=await db();return new Promise((resolve,reject)=>{const r=d.transaction('assets').objectStore('assets').getAll();r.onsuccess=()=>resolve(r.result);r.onerror=()=>reject(Error('No se pudieron leer los archivos guardados.'));});}
export async function deleteAssets(ids){const d=await db();return new Promise((resolve,reject)=>{const t=d.transaction('assets','readwrite');for(const id of ids)t.objectStore('assets').delete(id);t.oncomplete=resolve;t.onerror=reject;});}
export const blobBase64=blob=>new Promise((resolve,reject)=>{const r=new FileReader();r.onload=()=>resolve(r.result);r.onerror=reject;r.readAsDataURL(blob);});
export function base64Blob(url){const match=url.match(/^data:(audio\/[\w.+-]+);base64,([A-Za-z0-9+/=]+)$/);if(!match)throw Error('Archivo de audio de la copia no válido.');return new Blob([Uint8Array.from(atob(match[2]),c=>c.charCodeAt(0))],{type:match[1]});}

export function assetOwnerId(asset){return ['audio-segment','notebook-media','notebook-pdf'].includes(asset.kind)?asset.data?.itemId:asset.id.slice(asset.id.indexOf(':')+1);}
export async function deleteItemAssets(id){const assets=await allAssets();await deleteAssets(assets.filter(asset=>assetOwnerId(asset)===id).map(asset=>asset.id));}
