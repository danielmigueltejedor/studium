import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import {FRAMEWORK,PROFILES,fallbackScope} from '../public/studium-engine.js';
import {nativePodcastPlan} from '../public/podcast-plan.js';
const specs=Object.keys(PROFILES).flatMap(profile=>[1,4,15].map(chapters=>({profile,chapters,concepts:chapters*7,derivations:chapters,worked_examples:chapters*2,exercises:chapters*3,figures:chapters,sources:2,preference:'AUTO'})));
const code=`import json,sys\nfrom dataclasses import asdict\nsys.path.insert(0,'vendor')\nfrom studium.authoring.depth.profiles import PROFILES\nfrom studium.authoring.depth.length import estimate_book_scope\nspecs=json.load(sys.stdin)\nresults=[]\nfor spec in specs:\n profile=PROFILES[spec.pop('profile')]\n results.append(asdict(estimate_book_scope(profile=profile,**spec)))\nprint(json.dumps(results))`;
const r=spawnSync('python3',['-c',code],{input:JSON.stringify(specs),encoding:'utf8',cwd:new URL('../',import.meta.url)});assert.equal(r.status,0,r.stderr);const scopes=JSON.parse(r.stdout);for(let i=0;i<specs.length;i++){const actual=fallbackScope(specs[i]).scope,expected=scopes[i];for(const key of ['estimate','floor','ceiling'])assert(Math.abs(actual[key]-expected[key])<.11);}
assert.equal(FRAMEWORK.repository,'https://github.com/danielmigueltejedor/studium');assert.equal(FRAMEWORK.revision,'f7bc7310507b83bb23738511843fc7c7f1b6c96e');
const text='La inspección conserva los límites del material y documenta sus condiciones de mantenimiento. '.repeat(180);const base={text,title:'Materiales',engine:'gemini'};
const intro=await nativePodcastPlan({...base,depth:'INTRODUCTORY'}),advanced=await nativePodcastPlan({...base,depth:'ADVANCED_UNDERGRADUATE'});assert(advanced.targetWords>intro.targetWords);assert.equal(intro.framework.expertReview,'PENDING');assert.equal(intro.audioAdaptation.basis,'source_words_and_native_concept_depth');
console.log('Studium checks passed: pinned native Python modules, all five depth profiles, parity with JavaScript fallback and depth-dependent spoken scope.');
