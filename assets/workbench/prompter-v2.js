// Loaded after the standalone prompter; its page and highlighting state remain authoritative.
const promptMic=new StudioMicrophone({onLevel:n=>{document.getElementById('prompt-meter').style.width=n*100+'%'},onStatus:s=>{document.getElementById('mic-status').textContent=s;document.getElementById('status').textContent=s;if(!promptMic.active){following=false;document.getElementById('voice').classList.remove('on');}},onText:text=>{following=true;follow(text);updatePromptTimeline();}});
document.getElementById('voice').onclick=async()=>{if(promptMic.active){await promptMic.stop();following=false;document.getElementById('voice').classList.remove('on');document.getElementById('status').textContent='语音跟随已停止';return;}if(location.protocol==='file:'){document.getElementById('status').textContent='离线提词文件可手动使用；语音跟随请从本地工作台打开。';return;}try{if(!await promptMic.start(document.getElementById('prompt-device').value,true))return;following=true;document.getElementById('voice').classList.add('on');await promptDevices();}catch(e){document.getElementById('prompt-device-panel').classList.add('open');document.getElementById('status').textContent+='。可以先手动翻页。';}};
async function promptDevices(){try{const devices=await promptMic.devices(),select=document.getElementById('prompt-device'),value=select.value;select.innerHTML='<option value="">系统默认麦克风</option>';for(const d of devices){const o=document.createElement('option');o.value=d.deviceId;o.textContent=d.label||'麦克风';select.append(o);}select.value=value;}catch(e){}}
document.getElementById('device-toggle').onclick=()=>{document.getElementById('prompt-device-panel').classList.toggle('open');promptDevices()};document.getElementById('prompt-device').onchange=async()=>{if(promptMic.active){following=false;try{if(!await promptMic.start(document.getElementById('prompt-device').value,true))return;following=true;}catch(e){}}};
document.getElementById('prompt-mic-test').onclick=async()=>{try{if(!await promptMic.start(document.getElementById('prompt-device').value,false))return;following=false;await promptDevices();}catch(e){}};
document.getElementById('prompt-mic-stop').onclick=async()=>{await promptMic.stop();following=false;document.getElementById('voice').classList.remove('on');document.getElementById('mic-status').textContent='已停止并释放麦克风'};
window.addEventListener('pagehide',()=>promptMic.stop());
let promptTimeline=P.timeline; if(!promptTimeline){let start=0;promptTimeline={clips:P.pages.map(pg=>{const c={id:pg.id,track:'main',page_id:pg.id,name:pg.title,start,duration:pg.duration||Math.max(3,pg.text.length/(P.settings.speech_rate||240)*60)};start+=c.duration;return c}),duration:start};}
function buildPromptTimeline(){const surface=document.getElementById('prompt-tracks');surface.replaceChildren();const total=Math.max(1,promptTimeline.duration||0);for(const [track,name] of [['sticker','制作提示'],['pip','额外素材'],['main','口播 / 展示'],['music','背景音乐']]){const row=document.createElement('div');row.className='prompt-track';const label=document.createElement('small');label.textContent=name;row.append(label);const lane=document.createElement('div');lane.className='prompt-lane';for(const c of promptTimeline.clips.filter(c=>track==='sticker'?['title','sticker','sfx'].includes(c.track):c.track===track)){const clip=document.createElement('button');clip.textContent=c.name;clip.style.left=c.start/total*100+'%';clip.style.width=c.duration/total*100+'%';clip.title=c.name;clip.onclick=()=>{const idx=P.pages.findIndex(pg=>pg.id===c.page_id);if(idx>=0){index=idx;draw();updatePromptTimeline();}};lane.append(clip);}row.append(lane);surface.append(row);}}
function updatePromptTimeline(){const pg=P.pages[index],c=promptTimeline.clips.find(c=>c.track==='main'&&c.page_id===pg.id);const fraction=pg.type==='speech'?position/Math.max(1,[...pg.text].length):Math.min(1,elapsed/Math.max(.1,pg.duration||3));const time=c?c.start+fraction*c.duration:0;document.getElementById('prompt-needle').style.left=`calc(95px + (100% - 95px) * ${time/Math.max(1,promptTimeline.duration)})`;document.getElementById('prompt-time').textContent='稿件进度 '+Math.floor(time)+'s / '+Math.ceil(promptTimeline.duration)+'s · 预计编排';}
const originalHighlight=highlight;highlight=function(){originalHighlight();updatePromptTimeline();};const originalDraw=draw;draw=function(){originalDraw();updatePromptTimeline();};
setInterval(()=>{if(running&&P.pages[index].type!=='speech')updatePromptTimeline();},200);
document.getElementById('prompt-timeline-toggle').onclick=event=>{
  const compact=document.getElementById('prompt-timeline').classList.toggle('compact');
  event.currentTarget.textContent=compact?'展开轨道':'收起轨道';
  event.currentTarget.setAttribute('aria-expanded',String(!compact));
  queuePromptFit();
};
buildPromptTimeline();updatePromptTimeline();

document.getElementById('manual-reading').onclick=async()=>{
  await promptMic.stop();following=false;
  document.getElementById('voice').classList.remove('on');
  document.getElementById('prompt-device-panel').classList.remove('open');
  document.getElementById('status').textContent='手动翻页 · 用右方向键向前读';
  document.getElementById('next-btn').focus();
};

const prepareFollow=document.getElementById('prepare-follow');
if(prepareFollow){
  prepareFollow.hidden=location.protocol==='file:';
  prepareFollow.onclick=async()=>{
    prepareFollow.disabled=true;
    const status=document.getElementById('mic-status');
    try{
      const boot=await (await fetch('/api/bootstrap')).json();
      const job=await promptMic.request('/api/action',{project_id:P.id,action:'prepare_follow',args:{}},boot.token);
      while(true){
        const tasks=await (await fetch('/api/jobs?id='+encodeURIComponent(P.id))).json();
        const task=tasks.find(item=>item.id===job.id);
        if(!task)throw Error('请回工作台查看任务进度。');
        status.textContent=task.error||task.message;
        if(task.status==='done'){status.textContent='已准备好。点「跟我读」即可开始。';break;}
        if(['error','interrupted'].includes(task.status))break;
        await new Promise(resolve=>setTimeout(resolve,1200));
      }
    }catch(error){status.textContent=error.message;}finally{prepareFollow.disabled=false;}
  };
}
