import {copyFile,readFile,writeFile} from 'node:fs/promises';
import {build} from 'esbuild';
const root=new URL('../',import.meta.url);
await build({entryPoints:[new URL('node_modules/ts-fsrs/dist/index.mjs',root).pathname],bundle:true,format:'esm',platform:'browser',target:'es2022',outfile:new URL('public/fsrs.js',root).pathname});
for(const [from,to] of [['ts-fsrs/LICENSE','fsrs-LICENSE.txt'],['ical.js/dist/ical.min.js','ical.js'],['ical.js/LICENSE','ical-LICENSE.txt'],['katex/dist/katex.min.js','katex.min.js'],['katex/LICENSE','katex-LICENSE.txt'],['mathjax-full/es5/tex-svg.js','mathjax-svg.js'],['mathjax-full/LICENSE','mathjax-LICENSE.txt']])await copyFile(new URL('node_modules/'+from,root),new URL('public/'+to,root));
console.log('Pinned browser libraries rebuilt.');

const brand=await readFile(new URL('public/studium-logo-dark.png',root));const width=brand.readUInt32BE(16),height=brand.readUInt32BE(20);await writeFile(new URL('public/favicon.svg',root),`<svg xmlns="http://www.w3.org/2000/svg" viewBox="350 90 700 740"><image width="${width}" height="${height}" href="data:image/png;base64,${brand.toString('base64')}"/></svg>`);

for(const name of ['fsrs-LICENSE.txt','ical-LICENSE.txt','katex-LICENSE.txt','mathjax-LICENSE.txt']){const p=new URL('public/'+name,root);await writeFile(p,(await readFile(p,'utf8')).split('\n').map(l=>l.trimEnd()).join('\n').trimEnd()+'\n');}
