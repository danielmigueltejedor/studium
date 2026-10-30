import {podcastTurnPlan} from './podcast-story.js';
import {podcastEvidenceCatalog} from './podcast-evidence.js';

// Gemini constrained output: IDs are computed from this exact source block.
// Semantic support, source coverage, numbers and word counts still need auditing.
export function podcastResponseSchema(source,section){
 if(section?.evidenceVersion!==2)return undefined;
 const ids=podcastEvidenceCatalog(source,section.evidenceId).map(e=>e.id);
 if(!ids.length)throw Error('El bloque del podcast no contiene fragmentos de referencia.');
 const {count:minTurns,words:perTurn}=podcastTurnPlan(section);
 const story=section.storyVersion===1?{story:{type:'object',description:'Plan editorial breve antes del diálogo. No se escucha ni sustituye las evidencias.',properties:{question:{type:'string',description:'Pregunta interesante que conecta las ideas esenciales.'},analogy:{type:'string',description:'Comparación cotidiana expresamente hipotética que ayuda a entender, sin añadir hechos o cifras.'},payoff:{type:'string',description:'Qué entenderá el oyente al resolver la pregunta; no una lista de fórmulas.'}},required:['question','analogy','payoff'],additionalProperties:false}}:{};
 return {type:'object',properties:{...story,turns:{type:'array',minItems:minTurns,description:'Intervenciones alternas de Ana y Leo, con un total orientativo de '+section.targetWords+' palabras habladas.'+(section.continuation?' Solo intervenciones nuevas para añadir al borrador conservado.':''),items:{type:'object',properties:{speaker:{type:'string',enum:['Ana','Leo']},text:{type:'string',description:'Réplica natural de podcast, con preguntas, conexiones o explicación original, sin copiar la fuente. Media orientativa de '+perTurn+' palabras; varía su longitud. Basada en el material y sin etiquetas ni códigos de evidencia.'},evidence:{type:'array',minItems:1,maxItems:8,description:'Fragmentos que respaldan esta intervención. Usa los identificadores disponibles, sin reescribirlos.',items:{type:'object',properties:{id:{type:'string',enum:ids}},required:['id'],additionalProperties:false}}},required:['speaker','text','evidence'],additionalProperties:false}}},required:[...Object.keys(story),'turns'],additionalProperties:false};
}
