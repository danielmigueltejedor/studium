import {initializeStudiumPython} from './studium-native.js';
let engine;
self.onmessage=async({data:{id,spec}})=>{try{engine||=(async()=>{const indexURL='https://cdn.jsdelivr.net/pyodide/v0.29.3/full/';const {loadPyodide}=await import(indexURL+'pyodide.mjs');return initializeStudiumPython(loadPyodide,indexURL);})();const run=await engine;self.postMessage({id,result:run(spec)});}catch(error){engine=null;self.postMessage({id,error:error.message});}};
