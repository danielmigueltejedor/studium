import {podcastEvidenceCatalog} from './podcast-evidence.js';

// Gemini constrained output: IDs are computed from this exact source block.
// Semantic support, source coverage, numbers and word counts still need auditing.
export function podcastResponseSchema(source,section){
 if(section?.evidenceVersion!==2)return undefined;
 const ids=podcastEvidenceCatalog(source,section.evidenceId).map(e=>e.id);
 if(!ids.length)throw Error('El bloque del podcast no contiene fragmentos de referencia.');
 const minTurns=Math.max(2,Math.ceil(section.targetWords/(section.kind==='navigation'?45:120))),perTurn=Math.round(section.targetWords/minTurns);
 return {type:'object',properties:{turns:{type:'array',minItems:minTurns,description:'Intervenciones alternas de Ana y Leo, con un total orientativo de '+section.targetWords+' palabras habladas.'+(section.continuation?' Solo intervenciones nuevas para añadir al borrador conservado.':''),items:{type:'object',properties:{speaker:{type:'string',enum:['Ana','Leo']},text:{type:'string',description:'Explicación hablada de aproximadamente '+perTurn+' palabras, basada en el manual y sin etiquetas ni códigos de evidencia.'},evidence:{type:'array',minItems:1,maxItems:8,description:'Fragmentos que respaldan esta intervención. Usa los identificadores disponibles, sin reescribirlos.',items:{type:'object',properties:{id:{type:'string',enum:ids}},required:['id'],additionalProperties:false}}},required:['speaker','text','evidence'],additionalProperties:false}}},required:['turns'],additionalProperties:false};
}
