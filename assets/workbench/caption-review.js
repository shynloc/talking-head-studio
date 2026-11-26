'use strict';

function captionChange(before,after) {
  let left=0, endBefore=before.length, endAfter=after.length;
  while(left<endBefore && left<endAfter && before[left]===after[left])left++;
  while(endBefore>left && endAfter>left && before[endBefore-1]===after[endAfter-1]){endBefore--;endAfter--;}
  return [before.slice(left,endBefore),after.slice(left,endAfter)];
}

function openCaptionDesk(review,state,initialId) {
  const spans=state.caption_spans;
  if(!spans.length)return;
  let audit=state.caption_review;
  const draftKey='studio-caption-text-'+review.projectId;
  let draft=null;
  try{draft=JSON.parse(localStorage.getItem(draftKey));}catch{}
  if(draft?.layout!==audit.layout)draft=null;
  const first=draft?.id || initialId || spans.find(s=>audit.issues[s.id])?.id || audit.pending[0];
  let index=Math.max(0,spans.findIndex(s=>s.id===first));
  let queue=Promise.resolve(), timer, alarm, original, playing=false, manual=false;
  $('#finish-panel video')?.pause();
  if(!finishPanel(review,`<fieldset class="caption-desk">
    <h3>听一句，校一句</h3>
    <label for="caption-jump">选一句口播</label><select id="caption-jump"></select>
    <p id="caption-reason" class="hint"></p>
    <audio id="caption-audio" preload="auto" src="${finishURL(review,P.rough.media_id)}"></audio>
    <div class="action-row"><button class="ghost" id="caption-listen">听这句原声</button>
    <button class="ghost" id="caption-next"></button></div>
    <label for="preview-text">这句字幕</label><textarea id="preview-text" rows="2"></textarea>
    <button class="ghost" id="caption-suggest" hidden></button>
    <small id="caption-save-state" role="status"></small>
    <details class="workflow-tools" id="caption-names"><summary>统一改一个名称</summary>
    <div class="caption-pair"><label>原写法<input id="caption-old"></label><label>改成<input id="caption-new"></label></div>
    <div id="caption-match-list" class="hint"></div><button class="ghost" id="caption-bulk"></button></details>
    <button class="ghost" id="caption-auto-bulk" hidden></button>
    <button class="ghost" id="caption-undo" hidden>撤销上一次批量修改</button>
    <div class="action-row"><button class="key" id="caption-proof"></button></div>
    <p id="caption-warning" role="alert"></p></fieldset>`))return;
  const desk=$('.caption-desk'), field=$('#preview-text'), audio=$('#caption-audio');
  const jump=$('#caption-jump'), status=$('#caption-save-state'), warning=$('#caption-warning');
  const active=()=>desk.isConnected && finishPanelActive(review);
  const cap=()=>spans[index];
  const unique=()=>[...new Map(spans.map(s=>[s.id,s])).values()];
  const clearAudio=()=>{clearTimeout(alarm);playing=false;audio.pause();};
  let transition=Promise.resolve();
  const guard=fn=>()=>{
    if(desk.disabled)return transition;
    desk.disabled=true;
    transition=(async()=>{
      try{warning.textContent='';await fn();}
      catch(e){if(active()){jump.value=String(index);warning.textContent=e.message;}}
      finally{desk.disabled=false;}
    })();
    return transition;
  };

  function names() {
    const pair=manual?[$('#caption-old').value,$('#caption-new').value]:captionChange(original,field.value);
    const [from,to]=pair;
    const rows=unique().filter(c=>manual||c.id!==cap().id);
    const edits=[];
    let count=0;
    if(from && to.trim() && from!==to){
      for(const c of rows){
        const before=c.id===cap().id?field.value:c.text;
        const hits=before.split(from).length-1;
        if(hits){edits.push({id:c.id,before,after:before.replaceAll(from,()=>to)});count+=hits;}
      }
    }
    return {from,to,edits,count};
  }
  function controls() {
    const {from,to,edits,count}=names();
    $('#caption-auto-bulk').hidden=manual||!count;
    $('#caption-auto-bulk').textContent='把其余 '+count+' 处「'+from+'」也改为「'+to+'」';
    $('#caption-bulk').disabled=!count;
    $('#caption-bulk').textContent=count?'修改这 '+count+' 处':'没有匹配的名称';
    $('#caption-match-list').textContent=edits.slice(0,3).map(e=>'「'+e.before+'」').join('、');
    $('#caption-undo').hidden=!audit.can_undo;
    $('#caption-next').textContent=audit.issues[cap().id]?'确认这句，听下一处':'听下一句';
    $('#caption-proof').textContent=audit.pending.length||field.value!==cap().text?'改完了，一起试看':'返回预览';
  }
  function options(){
    jump.replaceChildren(...spans.map((s,i)=>new Option((audit.issues[s.id]?'待听 · ':'')+s.text,i)));
    jump.value=String(index);
  }
  function show(){
    const row=cap();original=row.text;field.dataset.captionId=row.id;field.value=row.text;manual=false;
    status.textContent='';warning.textContent='';$('#caption-names').open=false;
    $('#caption-old').value='';$('#caption-new').value='';
    $('#caption-reason').textContent=audit.issues[row.id]||'可以边听边改，文字会自动保存。';
    const suggested=P.pages.flatMap(p=>p.sentences||[]).find(s=>s.id===row.sentence_id)?.text;
    const button=$('#caption-suggest');
    button.hidden=!(suggested && suggested!==row.text && row.match_score>=.88 && !row.ambiguous_match);
    button.textContent=button.hidden?'':'用稿件写法「'+suggested+'」';
    button.onclick=()=>{field.value=suggested;field.dispatchEvent(new Event('input'));};
    options();controls();
  }
  async function persist(op,edits) {
    const result=await api('/api/v2/caption-review',{id:review.projectId,layout:audit.layout,operation:op,edits});
    if(P?.id===review.projectId && !dirty)P=result.project;
    for(const row of spans)if(Object.hasOwn(result.texts,row.id))row.text=result.texts[row.id];
    audit=result.review;
    const local=JSON.parse(localStorage.getItem(draftKey)||'null');
    if(local?.layout===audit.layout && result.texts[local.id]===local.text)localStorage.removeItem(draftKey);
    if(active()){options();controls();status.textContent='已保存';}
  }
  function flush(){
    clearTimeout(timer);
    const id=field.dataset.captionId, after=field.value;
    const next=queue.catch(()=>{}).then(async()=>{
      const before=spans.find(s=>s.id===id).text;
      if(before!==after)await persist('save',[{id,before,after}]);
    });
    queue=next;return next;
  }
  review.flushCaptions=async()=>{if(active()){await transition;if(active())await flush();clearAudio();}};
  field.oninput=()=>{
    localStorage.setItem(draftKey,JSON.stringify({layout:audit.layout,id:cap().id,before:cap().text,text:field.value}));
    status.textContent='正在保存…';controls();clearTimeout(timer);
    timer=setTimeout(()=>flush().catch(e=>{if(active())warning.textContent=e.message;}),350);
  };
  async function listen(){
    clearAudio();
    if(!source()?.audio)return;
    if(audio.readyState<1)await new Promise((ok,fail)=>{
      const clean=()=>{audio.removeEventListener('loadedmetadata',ready);audio.removeEventListener('error',error);};
      const ready=()=>{clean();ok();}, error=()=>{clean();fail(Error('无法读取剪后原声，请检查视频文件。'));};
      if(audio.error)return error();audio.addEventListener('loadedmetadata',ready);audio.addEventListener('error',error);
    });
    if(!active())return;
    const row=cap();
    audio.currentTime=row.listen_start;playing=true;
    await audio.play();
    if(!active()||row!==cap())return;
    function stopAtEnd(){
      if(!active()||row!==cap()||!playing)return;
      const remaining=row.listen_end-audio.currentTime;
      if(remaining<=.015)clearAudio();
      else alarm=setTimeout(stopAtEnd,Math.max(40,remaining*1000/audio.playbackRate));
    }
    stopAtEnd();
  }
  audio.ontimeupdate=()=>{if(playing && audio.currentTime>=cap().listen_end)clearAudio();};
  $('#caption-listen').onclick=guard(listen);
  async function select(i){
    clearAudio(); await flush();
    if(!active())return;
    index=i;show();await listen();
  }
  jump.onchange=guard(async()=>{const i=Number(jump.value);await select(i);});
  $('#caption-next').onclick=guard(async()=>{
    await flush();const row=cap();
    if(audit.issues[row.id])await persist('keep',[{id:row.id,before:row.text,after:row.text}]);
    const order=spans.map((_,i)=>(index+i+1)%spans.length);
    await select(order.find(i=>audit.issues[spans[i].id])??order[0]);
  });
  const details=$('#caption-names');
  details.querySelector('summary').onclick=()=>{
    if(!details.open && !$('#caption-old').value && !$('#caption-new').value){
      const [from,to]=captionChange(original,field.value);
      $('#caption-old').value=from;$('#caption-new').value=to;
    }
  };
  details.ontoggle=()=>{if(active()){manual=details.open;controls();}};
  $('#caption-old').oninput=$('#caption-new').oninput=()=>{manual=true;controls();};
  const bulk=guard(async()=>{
    await flush();const {edits}=names();
    if(!edits.length)return;
    await persist('bulk',edits);show();status.textContent='相同写法已修改，可以撤销。';
  });
  $('#caption-bulk').onclick=bulk;$('#caption-auto-bulk').onclick=bulk;
  $('#caption-undo').onclick=guard(async()=>{await flush();await persist('undo',[]);show();status.textContent='已撤销批量修改';});
  $('#caption-proof').onclick=guard(async()=>{
    await flush();clearAudio();
    const latest=await api('/api/v2/finish?id='+review.projectId);
    if(!active())return;
    if(latest.state!=='ready'||latest.caption_review.layout!==audit.layout)throw Error('剪辑已变化，请重新打开预览。');
    if(latest.caption_review.pending.length){
      review.playCorrections=true;
      await submitFinishJob(review,'caption_proof',{hash:latest.hash});
    }else await refreshFinishReview(review,false);
  });
  show();
  if(draft && draft.id===cap().id && draft.text!==cap().text){
    if(draft.before===cap().text){field.value=draft.text;field.dispatchEvent(new Event('input'));}
    else warning.textContent='这句在其他窗口改过。上次没保存的文字是「'+draft.text+'」。';
  }
  $('#caption-listen').disabled=!source()?.audio;
  if(source()?.audio)listen().catch(e=>{if(active())warning.textContent=e.message;});
}

function bindCorrectionPlayback(review,state,video) {
  const proof=P.caption_review;
  if(proof?.proof_id!==state.sample.id || !proof.proof_captions?.length)return;
  const ranges=[];
  for(const row of state.caption_spans.filter(s=>proof.proof_captions.includes(s.id))){
    const start=Math.max(0,row.start-.35),end=Math.min(state.duration,row.end+.35);
    if(ranges.length && start<=ranges.at(-1).end+.25)ranges.at(-1).end=Math.max(end,ranges.at(-1).end);
    else ranges.push({start,end});
  }
  if(!ranges.length)return;
  const button=$('#proof-play');
  button.hidden=false;
  let cursor=-1, userSelected=false;
  function setCursor(next,label){
    cursor=next;button.setAttribute('aria-pressed',String(cursor>=0));
    button.textContent=cursor>=0?'切回连续播放':label;
  }
  function begin(){
    setCursor(0);video.currentTime=ranges[0].start;
    video.play().catch(()=>setCursor(-1,'连看改过的几句'));
  }
  setCursor(-1,'连看改过的几句');
  button.onclick=()=>{
    userSelected=true;
    if(cursor>=0)setCursor(-1,'连看改过的几句');else begin();
  };
  video.addEventListener('timeupdate',()=>{
    if(cursor<0 || video.seeking || video.currentTime<ranges[cursor].end-.015)return;
    if(cursor+1<ranges.length){cursor++;video.currentTime=ranges[cursor].start;}
    else {setCursor(-1,'再看改过的几句');video.pause();}
  });
  video.addEventListener('ended',()=>{if(cursor>=0)setCursor(-1,'再看改过的几句');});
  if(review.playCorrections){
    review.playCorrections=false;
    if(video.readyState>=1)begin();
    else video.addEventListener('loadedmetadata',()=>{if(!userSelected)begin();},{once:true});
  }
}
