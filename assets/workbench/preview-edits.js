'use strict';

const pictureTypes = ['png','jpeg','jpg','webp','gif','svg','mp4','mov','webm'];

function bindPreviewEdits(review,state) {
  const video = $('#finish-panel video');
  const toolbar = $('#preview-edit-tools');
  const form = $('#preview-edit-form');
  const captionButton = $('#preview-caption');
  const visualButton = $('#preview-visual');
  const at = () => (state.sample.start || 0) + Math.min(video.currentTime,Math.max(0,state.sample.duration-.001));
  const currentCaption = time => state.caption_spans.find(c=>c.start<=time && time<c.end);
  function update() {
    if (!video.isConnected || !form.hidden) return;
    const cap=currentCaption(at());
    captionButton.disabled=!cap;
    $('#preview-line').textContent=cap?.text || '此处没有字幕';
    toolbar.hidden=!video.paused;
  }
  for(const name of ['pause','playing','seeked','timeupdate','loadedmetadata']) video.addEventListener(name,update);
  video.addEventListener('play',()=>{if(!form.hidden) video.pause();});
  update();
  if(review.replay) {
    review.replay=false;
    video.play().catch(()=>{video.focus();update();});
  }
  captionButton.onclick=()=>openCaptionDesk(review,state,currentCaption(at())?.id);
  if(visualButton)visualButton.onclick=()=>openEditor();

  function openEditor() {
    video.pause();
    const time=at(), cap=currentCaption(time);
    const clips=P.timeline.clips.filter(c=>['title','sticker','pip'].includes(c.track) && c.enabled!==false &&
      !P.timeline.tracks[c.track]?.muted && c.start<=time && time<c.start+c.duration);
    form.hidden=false;toolbar.hidden=true;
    const alternatives=$('#finish-panel .finish-choices');
    const exports=$('#finish-panel details');
    alternatives.hidden=true;exports.hidden=true;
    const payload={id:P.id,sample_id:state.sample.id,hash:state.hash,time,caption_id:cap?.id};
    form.innerHTML=`<label>要改的画面<select id="preview-clip">${clips.map(c=>`<option value="${esc(c.id)}">${esc(c.name)}</option>`).join('')}<option value="">在这里加画面</option></select></label>
      <label>画面内容<select id="preview-asset"><option value="">显示文字</option>${P.assets.filter(a=>pictureTypes.includes(a.type)).map(a=>`<option value="${esc(a.id)}">${esc(a.name)}</option>`).join('')}</select></label>
      <label>或从电脑选图片、视频<input type="file" id="preview-file" accept="image/*,video/*"></label>
      <label>文字或素材名称<input id="preview-text"></label>`;
    form.insertAdjacentHTML('beforeend',`<div class="action-row"><button id="preview-save" class="key">保存并从这里试看</button>
      <button id="preview-hide" class="ghost">移除这个画面</button>
      <button id="preview-cancel" class="ghost">取消</button></div><p id="preview-message" role="status"></p>`);
    {
      const choose=$('#preview-clip');
      choose.onchange=()=>{
        const clip=clips.find(c=>c.id===choose.value);
        $('#preview-asset').value=clip?.asset_id||'';
        $('#preview-text').value=clip?.name||cap?.text||'';
        $('#preview-file').value='';
        $('#preview-hide').hidden=!clip;
      };
      choose.onchange();
      $('#preview-hide').onclick=()=>submit('hide');
    }
    $('#preview-text').focus();
    $('#preview-cancel').onclick=()=>{
      form.hidden=true;form.replaceChildren();alternatives.hidden=false;exports.hidden=false;update();
      visualButton.focus();
    };
    $('#preview-save').onclick=()=>submit('visual');
    async function submit(operation) {
      const message=$('#preview-message');
      for(const control of form.querySelectorAll('button'))control.disabled=true;
      try {
        const text=$('#preview-text').value;
        const clip_id=$('#preview-clip')?.value||'';
        let asset_id=$('#preview-asset')?.value||'';
        const file=$('#preview-file')?.files[0];
        if(operation==='visual'&&file)asset_id=await importLocalAsset(payload.id,file);
        if(!finishPanelActive(review)||!message.isConnected)return;
        const result=await api('/api/v2/preview-edit',{...payload,operation,text,name:text,clip_id,asset_id});
        if(!finishPanelActive(review))return;
        P=await api('/api/project?id='+payload.id);
        if(!finishPanelActive(review))return;
        render();review.replay=true;
        await submitFinishJob(review,'timeline_sample',{start:result.start,duration:Math.max(3,state.sample.duration)});
      } catch(error) {
        message.textContent=error.message;
        for(const control of form.querySelectorAll('button'))control.disabled=false;
      }
    }
  }
}
