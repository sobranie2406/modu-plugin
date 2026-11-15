import {Worker} from 'node:worker_threads';
import {readFile} from 'node:fs/promises';
const source = await readFile(new URL('../packages/web-clipper/extract.js', import.meta.url), 'utf8');
export async function runArticle(input, {oldApis = true} = {}) {
  const code = `const {parentPort} = require('node:worker_threads');
    globalThis.self = globalThis;
    let calls = 0;
    const deny = () => {calls++; throw new Error('Host access denied');};
    for (const key of ['fetch','XMLHttpRequest','WebSocket','EventSource','importScripts','Worker','SharedWorker','indexedDB','caches']) Object.defineProperty(self,key,{value:deny,writable:false,configurable:false});
    ${oldApis ? 'Object.hasOwn=undefined;Array.prototype.at=undefined;Array.prototype.findLast=undefined;String.prototype.replaceAll=undefined;' : ''}
    const modu = new Proxy({}, {get:deny});
    parentPort.once('message', async input => {
      try {
        const result = await (async(input,modu)=>{${source}\n})(input,modu);
        parentPort.postMessage({result,calls,evilExecuted:globalThis.evilExecuted===true,domAbsent:typeof window==='undefined'&&typeof document==='undefined'&&typeof flutter_inappwebview==='undefined'});
      } catch(error) {parentPort.postMessage({error:String(error),calls});}
    });`;
  const worker = new Worker(code, {eval:true});
  return new Promise((resolve,reject) => {
    const timer=setTimeout(()=>reject(new Error('Article worker timed out')),10000);
    worker.once('message', value=>{clearTimeout(timer);resolve(value);});
    worker.once('error', error=>{clearTimeout(timer);reject(error);});
    worker.postMessage({actionId:'extract',url:'https://example.org/article',...input});
  }).finally(()=>worker.terminate());
}
