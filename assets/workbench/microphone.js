/* Each start owns its resources. Late completions only release their owner. */
class StudioMicrophone {
 constructor({onLevel=()=>{},onText=()=>{},onStatus=()=>{}}={}) {
  Object.assign(this,{onLevel,onText,onStatus});this.generation=0;this.run=null;
 }
 get active(){return !!this.run?.active;}
 get stream(){return this.run?.stream||null;}
 get session(){return this.run?.session||null;}
 get context(){return this.run?.context||null;}
 current(run){return this.run===run&&run.generation===this.generation&&!run.cancelled;}
 async request(path,data,token){
  const r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-Studio-Token':token},body:JSON.stringify(data)});
  const j=await r.json();if(!r.ok)throw Error(j.error);return j;
 }
 async devices(){return (await navigator.mediaDevices.enumerateDevices()).filter(d=>d.kind==='audioinput');}
 async release(run){
  if(!run)return;
  run.cancelled=true;run.active=false;run.queue=[];
  const context=run.context,session=run.session,stream=run.stream;
  run.context=null;run.session=null;run.stream=null;
  run.processor?.disconnect();run.source?.disconnect();run.silence?.disconnect();
  stream?.getTracks().forEach(t=>{t.onended=null;t.stop();});
  await Promise.allSettled([
   context&&context.state!=='closed'?context.close():Promise.resolve(),
   session&&run.token?this.request('/api/v2/speech/stop',{id:session},run.token):Promise.resolve()
  ]);
 }
 async start(device='',recognize=true){
  const previous=this.run,generation=++this.generation;
  this.run=null;this.onLevel(0);await this.release(previous);
  if(generation!==this.generation)return false;
  const run={generation,active:false,queue:[],sequence:0,sending:false};this.run=run;
  const status=s=>{if(this.current(run))this.onStatus(s);};
  const stale=async()=>{if(this.current(run))return false;await this.release(run);return true;};
  try{
   if(!navigator.mediaDevices?.getUserMedia)throw Error('当前页面无法访问麦克风，请从本机工作台地址打开');
   status('正在请求麦克风权限…');
   run.stream=await navigator.mediaDevices.getUserMedia({audio:{deviceId:device?{exact:device}:undefined,channelCount:1,echoCancellation:true,noiseSuppression:true},video:false});
   if(await stale())return false;
   run.active=true;run.lastSound=performance.now();
   const boot=await(await fetch('/api/bootstrap')).json();
   if(await stale())return false;
   run.token=boot.token;status('麦克风已连接，正在加载本地识别…');
   if(recognize){const session=await this.request('/api/v2/speech/start',{},run.token);run.session=session.id;}
   if(await stale())return false;
   const context=new AudioContext();run.context=context;
   await context.resume();if(await stale())return false;
   await context.audioWorklet.addModule('/mic-worklet.js');if(await stale())return false;
   run.source=context.createMediaStreamSource(run.stream);run.processor=new AudioWorkletNode(context,'studio-capture');run.silence=context.createGain();run.silence.gain.value=0;
   run.source.connect(run.processor);run.processor.connect(run.silence);run.silence.connect(context.destination);
   run.processor.port.onmessage=e=>{
    if(!this.current(run)||!run.active)return;
    const a=e.data;let sum=0;for(const n of a)sum+=n*n;const rms=Math.sqrt(sum/a.length);this.onLevel(Math.min(1,rms*8));
    if(rms>.003)run.lastSound=performance.now();
    if(performance.now()-run.lastSound>6000)status('麦克风已连接，但暂未检测到明显声音，请检查所选设备与系统音量');
    if(run.session){run.queue.push(a);if(run.queue.length>12){this.fail(run,Error('识别处理跟不上录音，已停止以防进度延迟，请重启'));return;}this.send(run);}
   };
   run.stream.getAudioTracks()[0].onended=()=>this.fail(run,Error('麦克风已断开，请重新选择设备'));
   status(recognize?'本地语音跟随已就绪 · 请开始读稿':'麦克风音量测试中 · 声音仅在本机处理');return true;
  }catch(e){
   if(!this.current(run)){await this.release(run);return false;}
   const names={NotSupportedError:'当前浏览器不支持音频采集，请用 Chrome 或 Edge 打开本机工作台地址',NotAllowedError:'麦克风权限被拒绝，请在地址栏的网站权限中允许麦克风',NotFoundError:'没有可用麦克风，请连接设备',NotReadableError:'麦克风无法打开，可能被其他应用独占',OverconstrainedError:'所选设备已不存在，请重新选择'};
   const message=names[e.name]||e.message;await this.fail(run,Error(message));throw e;
  }
 }
 async fail(run,error){
  if(this.current(run)){this.run=null;this.generation++;this.onLevel(0);this.onStatus(error.message);}
  await this.release(run);
 }
 async send(run){
  if(run.sending||!this.current(run)||!run.queue.length)return;run.sending=true;
  try{
   while(this.current(run)&&run.queue.length){
    const a=run.queue.shift(),bytes=new Uint8Array(a.buffer,a.byteOffset,a.byteLength);let binary='';
    for(let i=0;i<bytes.length;i+=8192)binary+=String.fromCharCode(...bytes.subarray(i,i+8192));
    const r=await this.request('/api/v2/speech/audio',{id:run.session,sequence:run.sequence++,rate:run.context.sampleRate,pcm:btoa(binary)},run.token);
    if(this.current(run)&&r.text)this.onText(r.text,r.endpoint);
   }
  }catch(e){await this.fail(run,Error('识别已停止：'+e.message));}finally{run.sending=false;}
 }
 async stop(){const previous=this.run;this.run=null;this.generation++;this.onLevel(0);await this.release(previous);}
}
window.StudioMicrophone=StudioMicrophone;

