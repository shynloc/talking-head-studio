'use strict';

function noteButtons(captionId) {
  if (P.settings.caption_only) return '';
  return (P.cue_notes||[]).filter(n=>n.caption_id===captionId).map(n=>{
    const label={skipped:'已跳过',accepted:'已采用',existing:'已安排'}[n.status]||'试看';
    return `<button class="ghost cue-note" data-recording-note="${esc(n.id)}">${label} · ${esc(n.label)}</button>`;
  }).join('');
}

document.addEventListener('click',async event=>{
  const button=event.target.closest('[data-recording-note]');
  if(!button)return;
  try {
    await save();
    const pid=P.id, fresh=await api('/api/project?id='+pid);
    if(P?.id!==pid||homeMode)return;
    P=fresh;
    const note=P.cue_notes.find(n=>n.id===button.dataset.recordingNote);
    if(note)await openRecordingNote(note);
  } catch(error){toast(error.message,true);}
});

async function openRecordingNote(note) {
  const pid=P.id;
  const initial=note.asset_id?(note.kind==='sticker'&&P.assets.find(a=>a.id===note.asset_id)?.type==='png'?'animated':'asset'):['flow','title'].includes(note.kind)?'original':'title';
  openDialog('录制时的画面备注',`<h3>${esc(note.label)}</h3><p class="hint">${esc(note.page)}</p>
    <div id="note-options" class="cue-fields">
    <label>对应哪句话<select id="note-caption"><option value="">请选择实际说出的句子</option>${P.captions.map(c=>`<option value="${esc(c.id)}">${esc(c.text)}</option>`).join('')}</select></label>
    <label>想看什么效果<select id="note-mode">${['flow','title'].includes(note.kind)?'<option value="original">按录前安排</option>':''}
      <option value="title">文字提示</option><option value="flow">步骤动画</option><option value="asset">图片、视频或声音</option><option value="animated">把 PNG 做成动图</option></select></label>
    <div id="note-media"><label>项目素材<select id="note-asset"></select></label><label>或从电脑选择<input type="file" id="note-file"></label></div>
    <label>显示文字或素材名称<input id="note-name" value="${esc(note.label)}"></label></div>
    <div id="note-player"></div><p id="note-feedback" role="status"></p>
    <div class="action-row"><button id="note-try" class="key">看这段效果</button><button id="note-use" class="key" hidden>采用</button><button id="note-change" class="ghost" hidden>换一个</button><button id="note-skip" class="ghost">跳过</button></div>`);
  const form=$('#note-options'),status=$('#note-feedback'),player=$('#note-player');
  const chooser=$('#note-caption'),mode=$('#note-mode'),asset=$('#note-asset'),file=$('#note-file');
  const tryIt=$('#note-try'),use=$('#note-use'),change=$('#note-change'),skip=$('#note-skip');
  let trial;
  const active=()=>status.isConnected && $('#dialog').open && P?.id===pid;
  chooser.value=note.caption_id;mode.value=initial;
  mode.onchange=()=>{
    const animated=mode.value==='animated';
    $('#note-media').hidden=!['asset','animated'].includes(mode.value);
    asset.innerHTML='<option value="">选择素材</option>'+P.assets.filter(a=>!animated||a.type==='png').map(a=>`<option value="${esc(a.id)}">${esc(a.name)}</option>`).join('');
    asset.value=note.asset_id;file.value='';file.accept=animated?'.png':'image/*,video/*,audio/*';
  };
  mode.onchange();
  function busy(value){for(const el of [tryIt,use,change,skip,...form.querySelectorAll('input,select')])el.disabled=value;}
  function showForm() {
    trial=null;player.replaceChildren();form.hidden=false;change.hidden=true;use.hidden=true;tryIt.hidden=false;
    status.textContent=chooser.value?'':'没能确定对应的口播，请选一句再试看。';
  }
  async function trySample(){
    if(!chooser.value){status.textContent='请先选择对应的口播句子。';chooser.focus();return;}
    busy(true);
    try {
      let aid=asset.value;
      if(['asset','animated'].includes(mode.value)&&file.files[0])aid=await importLocalAsset(pid,file.files[0]);
      if(!active())return;
      if(['asset','animated'].includes(mode.value)&&!aid)throw Error('请先选择一份素材。');
      const args={tag_id:note.id,caption_id:chooser.value,mode:mode.value,name:$('#note-name').value,asset_id:aid};
      let job=await api('/api/action',{project_id:pid,action:'note_preview',args});
      status.textContent='正在准备这段画面…';
      while(['queued','running'].includes(job.status)){
        await new Promise(done=>setTimeout(done,400));if(!active())return;
        job=(await api('/api/jobs?id='+pid)).find(j=>j.id===job.id);
      }
      if(!active())return;
      if(job.status!=='done')throw Error(job.error||job.message);
      trial=job.result;
      form.hidden=true;tryIt.hidden=true;use.hidden=false;change.hidden=false;
      player.innerHTML=`<video class="finish-video" controls playsinline src="/file/${encodeURIComponent(pid)}/${encodeURIComponent(trial.id)}" aria-label="画面备注小样"></video>`;
      status.textContent=(mode.value==='title' && !['title','flow'].includes(note.kind))?'这版使用文字提示。点「换一个」可放真实图片或视频。':'这是这句话放入素材后的效果。';
    } catch(error){status.textContent=error.message;}finally{busy(false);}
  }
  async function decide(skipped){
    busy(true);
    try {
      const data=skipped?{tag_id:note.id,skip:true}:{...trial.selection,baseline:trial.baseline};
      await api('/api/v2/note-decision',{...data,id:pid});
      if(!active())return;
      P=await api('/api/project?id='+pid);
      if(!active())return;
      closeDialog();render();toast(skipped?'已跳过这条画面备注':'已加到这句话');
    }catch(error){status.textContent=error.message;}finally{busy(false);}
  }
  change.onclick=showForm;tryIt.onclick=trySample;use.onclick=()=>decide(false);skip.onclick=()=>decide(true);
  showForm();
  if(note.caption_id&&note.status==='pending')await trySample();
}
