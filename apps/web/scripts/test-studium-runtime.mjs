import assert from 'node:assert/strict';
import {loadPyodide} from 'pyodide';
import {initializeStudiumPython} from '../public/studium-native.js';
const run=await initializeStudiumPython(loadPyodide,new URL('../node_modules/pyodide/',import.meta.url).pathname);
const result=run({profile:'UNDERGRADUATE',chapters:5,concepts:30,derivations:3,worked_examples:5,exercises:0,figures:0,sources:1,preference:'AUTO'});assert.equal(result.framework.runtime,'python-pyodide');assert.equal(result.scope.estimate,37.1);assert.equal(result.framework.revision,'f7bc7310507b83bb23738511843fc7c7f1b6c96e');console.log('Real Pyodide/WASM execution passed with original upstream Python modules: 37.1 planned pages; review remains PENDING.');
