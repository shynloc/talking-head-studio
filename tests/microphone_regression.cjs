const fs=require('fs'),vm=require('vm'),path=require('path'),assert=require('assert');
const defer=()=>{let resolve,reject;const promise=new Promise((a,b)=>{resolve=a;reject=b;});return{promise,resolve,reject};};
const flush=()=>new Promise(r=>setImmediate(r));
async function until(fn){for(let i=0;i<100;i++){if(fn())return;await flush();}throw Error('async operation did not reach expected state');}
const streams=[],contexts=[],requests=[],live=new Set();let permission=null,resume=null,audio=null;
global.window={};
Object.defineProperty(global,'navigator',{value:{mediaDevices:{getUserMedia:async()=>{
 if(permission)await permission.promise;
 const track={stopped:false,stop(){this.stopped=true;}};const stream={getTracks:()=>[track],getAudioTracks:()=>[track],track};streams.push(stream);return stream;
}}}});
global.fetch=async()=>({json:async()=>({token:'test-only'})});
const node=()=>({connect(){},disconnect(){},port:{},gain:{value:0}});
global.AudioContext=class{constructor(){this.state='running';this.sampleRate=48000;this.audioWorklet={addModule:async()=>{}};this.destination={};contexts.push(this);}async resume(){if(resume)await resume.promise;}async close(){this.state='closed';}createMediaStreamSource(){return node();}createGain(){return node();}};
global.AudioWorkletNode=class{constructor(){return node();}};
vm.runInThisContext(fs.readFileSync(path.join(__dirname,'../assets/workbench/microphone.js'),'utf8'));
function mic(){const m=new window.StudioMicrophone();m.request=async(url,data)=>{
 if(url.endsWith('/start')){const d=defer();requests.push(d);const id=await d.promise;live.add(id);return{id};}
 if(url.endsWith('/stop')){live.delete(data.id);return{};}
 if(url.endsWith('/audio'))return audio.promise;
 throw Error(url);
};return m;}
async function begin(m,id){const n=requests.length,p=m.start();await until(()=>requests.length>n);requests[n].resolve(id);await p;return m;}
(async()=>{
 const checks=[];
 // A6: startup response A arrives after B has successfully started.
 let m=mic(),i=requests.length,a=m.start();await until(()=>requests.length>i);
 await begin(m,'B');const stream=m.stream;requests[i].resolve('A');assert.equal(await a,false);
 assert(m.active&&m.session==='B'&&!stream.track.stopped);assert.deepEqual([...live],['B']);await m.stop();assert.equal(live.size,0);checks.push('late startup releases only its own session');
 // Stop while permission UI is pending; its returned stream must be released.
 m=mic();permission=defer();a=m.start();await flush();await m.stop();permission.resolve();await a;permission=null;
 assert(!m.active&&streams.at(-1).track.stopped);checks.push('stop during permission releases late stream');
 // A failing old HTTP audio request must not close the newer run.
 m=mic();await begin(m,'audio-A');audio=defer();m.run.queue.push(new Float32Array(128));a=m.send(m.run);
 await begin(m,'audio-B');audio.reject(Error('old request failed'));await a;assert(m.active&&m.session==='audio-B');await m.stop();assert.equal(live.size,0);checks.push('stale audio failure cannot stop new capture');
 // Old AudioContext.resume resolves after a newer start; newer resources survive.
 m=mic();resume=defer();const pending=resume;a=m.start('',false);await until(()=>!!m.context);const oldContext=m.context;
 resume=null;await m.start('',false);const newContext=m.context;pending.resolve();await a;
 assert(m.active&&m.context===newContext&&oldContext.state==='closed'&&newContext.state!=='closed');await m.stop();checks.push('late context resume leaves newer context intact');
 // A stopped startup response must close the session even without a replacement.
 m=mic();i=requests.length;a=m.start();await until(()=>requests.length>i);await m.stop();requests[i].resolve('stopped');await a;
 assert(!m.active&&live.size===0&&streams.every(s=>s.track.stopped));checks.push('stop during ASR startup releases late server session');
 console.log(JSON.stringify({status:'PASS',checks},null,2));
})().catch(e=>{console.error(e);process.exitCode=1;});
