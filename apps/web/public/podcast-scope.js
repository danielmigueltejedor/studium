// Audio planning heuristics, separate from Studium's academic release gates.
export function narrationSourceProfile(text){
 const tokens=String(text).match(/\S+/gu)||[],lines=String(text).split('\n').map(s=>s.trim()).filter(Boolean),leaders=lines.filter(s=>/(?:\.\s*){5,}/.test(s)).length;
 const sourceWords=tokens.filter(t=>/[\p{L}\p{N}]/u.test(t)).length;
 const orientation=lines.filter(s=>/^(?:presentación(?: y modo de estudio)?|edición y fecha de referencia|estado de revisión|ruta de estudio y diferenciación de fuentes|símbolos y convenciones|relación con el material de la asignatura)$/iu.test(s)).length;
 const developsContent=lines.some(s=>/^(?:orientación del capítulo|objetivos de aprendizaje|objetivos del capítulo|situación trabajada|ejemplo resuelto)\b/iu.test(s));
 const kind=leaders>=4&&leaders/Math.max(1,lines.length)>=.25&&!developsContent?'navigation':orientation>=2?'orientation':'content';
 return {kind,sourceWords,rawSourceWords:tokens.length};
}
export function narrationTarget(text,{engine,perConcept}){const profile=narrationSourceProfile(text),procedures=(text.match(/procedimiento|inspecci[oó]n|mantenimiento|criterio|precauci[oó]n|paso\s+\d/gi)||[]).length;
 const targetWords=profile.kind==='navigation'?Math.max(20,Math.min(70,Math.round(profile.sourceWords*.08))):profile.kind==='orientation'?Math.max(50,Math.min(140,Math.round(profile.sourceWords*.14))):Math.max(20,Math.min(engine==='ai'?430:1250,Math.round(profile.sourceWords*(.38+.35*perConcept)+Math.min(procedures,5)*8)));
 return {...profile,concepts:Math.max(1,Math.ceil(profile.sourceWords/160)),targetWords};
}
export function narrationWindow(targetWords){const minimum=Math.ceil(targetWords*.75),tolerance=Math.min(24,Math.floor(minimum*.025));return {minimum,tolerance};}
export function validPodcastContinuation(c){return c===undefined||!!c&&typeof c.text==='string'&&c.text.length>0&&c.text.length<=20000&&Number.isSafeInteger(c.words)&&c.words>0&&c.words<=10000&&Number.isSafeInteger(c.minimumWords)&&c.minimumWords>0&&c.minimumWords<=1600&&typeof c.needsBeginning==='boolean'&&typeof c.needsEnding==='boolean';}
export function continuationSection(segment,draft,total,depth){const {minimum}=narrationWindow(segment.targetWords),deficit=Math.max(0,minimum-draft.words),targetWords=deficit?Math.min(1200,Math.max(100,Math.ceil(deficit*1.2))):segment.kind==='navigation'?40:80;
 return {...segment,total,depth,evidenceVersion:2,targetWords,continuation:{text:draft.text,words:draft.words,minimumWords:minimum,needsBeginning:!draft.checks?.beginningCovered,needsEnding:!draft.checks?.endingCovered}};
}
