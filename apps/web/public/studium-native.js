import {PYTHON_FILES,FRAMEWORK} from './studium-python.js';
export async function initializeStudiumPython(loadPyodide,indexURL){
 const python=await loadPyodide({indexURL});
 for(const [path,source] of Object.entries(PYTHON_FILES)){python.FS.mkdirTree(path.slice(0,path.lastIndexOf('/')));python.FS.writeFile(path,source);}
 python.runPython(`import sys, json\nsys.path.insert(0, '/')\nfrom dataclasses import asdict\nfrom studium.authoring.depth.profiles import PROFILES, profile_requirements\nfrom studium.authoring.depth.length import estimate_book_scope\ndef studium_scope(payload):\n    spec=json.loads(payload)\n    profile=PROFILES[spec.pop('profile')]\n    scope=estimate_book_scope(profile=profile, **spec)\n    return json.dumps({'scope':asdict(scope), 'profile':profile_requirements(profile)})`);
 return spec=>{python.globals.set('_studium_payload',JSON.stringify(spec));const result=JSON.parse(python.runPython('studium_scope(_studium_payload)'));python.globals.delete('_studium_payload');return {...result,framework:{...FRAMEWORK,runtime:'python-pyodide',checks:['depth_scope'],expertReview:'PENDING'}};};
}
