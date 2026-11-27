'use strict';
let homeMode=true,projectList=[],v2Status={},manuscript=null,mdEditor=null,mdSavedText='',draftPoll=null,micTester=null,mdGeneration=0;
const icons={recording:'<rect x="3" y="7" width="17" height="16" rx="3"/><path d="m20 12 7-4v14l-7-4z"/>',import:'<path d="M5 4h11l5 5v15H5zM16 4v6h6M13 13v8m-4-4 4 4 4-4"/>',edit:'<path d="M5 6h9M5 11h7M5 16h5M5 23h17M13 17l2-6 7-7 4 4-7 7z"/>',new:'<rect x="4" y="4" width="22" height="22" rx="5"/><path d="M15 9v12M9 15h12"/>'};
function icon(name){return `<svg viewBox="0 0 30 30" aria-hidden="true">${icons[name]}</svg>`;}
const legacyRender=render,legacyMark=mark,legacyLoad=load,legacyClose=closeDialog;
render=function(){
  if(homeMode)return dashboard();
  localStorage.setItem('studio-page-'+P.id,selected);
  legacyRender();
  $('#agent-inbox').textContent='交给 AI';
  localStorage.setItem('studio-stage-'+P.id,String(stage));
  refreshWorkflow();
  $('#agent-inbox').dataset.agent='compose';
  renderTimeline();
};
mark=function(){if(P)syncTimeline();legacyMark();refreshWorkflow();clearTimeout(mark._tl);mark._tl=setTimeout(()=>{if(!document.activeElement?.closest('.timeline-dock')&&!window.tlDragging)renderTimeline()},180);};
load=async function(id,initialStage){
  homeMode=false;
  if(P?.id!==id)timelineExpanded=false;
  const savedStage=Number(localStorage.getItem('studio-stage-'+id));
  stage=initialStage||([1,2,3].includes(savedStage)?savedStage:1);
  tab=stage===3?'captions':'plan';
  previewMode='auto';
  document.body.classList.remove('dashboard-mode');
  location.hash='project='+id;
  await legacyLoad(id);
};
closeDialog=function(){clearInterval(draftPoll);draftPoll=null;mdGeneration++;const closingEditor=mdEditor;mdEditor=null;clearTimeout(closingEditor?._save);if(closingEditor?._ready)closingEditor.destroy();else if(closingEditor)closingEditor._disposed=true;if(micTester){micTester.stop();micTester=null;}$('#dialog').classList.remove('manuscript-dialog');if(P && $('#dialog').open)localStorage.removeItem(openReviewKey(P.id));legacyClose();};
$('#close-dialog').onclick=()=>safeClose();$('#dialog').addEventListener('cancel',e=>{e.preventDefault();safeClose()});
async function safeClose(){if(finishReview?.flushCaptions)try{await finishReview.flushCaptions()}catch(e){toast(e.message,true);return;}if(mdEditor&&manuscript&&manuscript.status!=='running')try{await saveManuscript()}catch(e){toast(e.message,true);return;}closeDialog();}
function refreshAnnotations(){const doc=new DOMParser().parseFromString(stageOne(),'text/html');const next=doc.querySelector('.annotations');if(next&&$('.annotations')){next.open=$('.annotations').open;$('.annotations').replaceWith(next);}syncTimeline();renderTimeline();const metrics=$$('.hero-metrics .metric strong');if(metrics[2])metrics[2].textContent=P.pages.reduce((n,p)=>n+p.tags.length,0);}
async function dashboard(){
  if(!homeMode)$('#main').replaceChildren();
  homeMode=true;
  busy=false;
  $('#jobbar').hidden=true;
  document.body.classList.remove('busy');
  $('#agent-inbox').textContent='AI 待办';
  $('#agent-inbox').dataset.agent='list';
  document.body.classList.add('dashboard-mode');
  if(location.hash)history.replaceState(null,'',location.pathname);
  const bootstrap=await refreshProjects();
  v2Status=await api('/api/v2/status');
  if(!homeMode)return;
  projectList=bootstrap.projects;
  const recentId=localStorage.getItem('studio-current-project');
  const recent=projectList.find(p=>p.id===recentId&&!p.example) || projectList.find(p=>!p.example);
  const stageName=id=>workSteps[Number(localStorage.getItem('studio-stage-'+id)||1)-1]||workSteps[0];
  const projectButton=p=>`<button class="recent-card" data-open-project="${esc(p.id)}"><strong>${esc(p.title)}</strong><small>${stageName(p.id)} · 继续编辑</small></button>`;
  const examples=projectList.filter(p=>p.example);
  const others=projectList.filter(p=>!p.example&&p!==recent);
  $('#main').innerHTML=`<div class="dashboard">
    ${recent?`<section class="resume-project" data-recent-project="${esc(recent.id)}"><div><strong>${esc(recent.title)}</strong><p role="status" class="resume-status">${stageName(recent.id)}</p></div><div class="action-row resume-actions"><button class="key" data-open-project="${esc(recent.id)}">打开项目</button></div></section>`:''}
    <div class="dash-intro"><h1>你手里<em>有什么？</em></h1><div class="dash-sculpture" aria-hidden="true"></div></div>
    <div class="entry-grid">
      <div class="entry-start"><button class="entry-card featured" data-v2="import-new">${icon('import')}<strong>有稿件</strong><small>导入或粘贴，分成提词页。</small></button><button class="text-action" data-v2="polish-new">想先润色稿件？</button></div>
      <button class="entry-card" data-v2="video-new">${icon('recording')}<strong>有录音或视频</strong><small>录音可以变成稿件，视频可以剪停顿、加字幕。</small></button>
      <div class="entry-start"><a class="entry-card motion-entry" href="/motion/index.html?view=desk"><svg viewBox="0 0 30 30" aria-hidden="true"><path d="m3 10 12-6 12 6-12 6zM3 15l12 6 12-6M3 20l12 6 12-6"/></svg><strong>只做口播素材</strong><small>贴整篇稿，挑喜欢的小样，一次导出透明动画。</small></a><a class="text-action" href="/motion/index.html">浏览动效词库</a></div>
      <div class="entry-start"><button class="entry-card" data-v2="blank">${icon('new')}<strong>从空白开始</strong><small>写下第一段口播。</small></button><button class="text-action" data-v2="import-project">导入工程包</button></div>
    </div>
    ${others.length?`<h2>我的项目</h2><div class="recent-grid">${others.map(projectButton).join('')}</div>`:''}
    ${examples.length?`<details class="workflow-tools"><summary>看看示例</summary><div class="recent-grid">${examples.map(projectButton).join('')}</div></details>`:''}
    </div>`;
  $('#footer-meta').textContent='';
  await refreshDashboardResume($('#main [data-recent-project]'));
}

async function refreshDashboardResume(card) {
  if (!card || card.loading) return;
  card.loading = true;
  const id = card.dataset.recentProject;
  const current = () => homeMode && card.isConnected;
  try {
    const jobs = await api('/api/jobs?id='+id);
    if (!current()) return;
    const active = activeProjectJob(jobs);
    const [project,drafts] = active ? [{id},[]] : await Promise.all([
      api('/api/project?id='+id),
      api('/api/v2/drafts?project_id='+id+'&summary=1'),
    ]);
    const next = await projectResume(project,jobs,drafts.find(d=>d.status==='review'));
    if (!current()) return;
    const status = card.querySelector('.resume-status');
    if (status.textContent !== next.status) status.textContent = next.status;
    const actions = card.querySelector('.resume-actions');
    const open = `data-open-project="${esc(id)}"`;
    const html = next.fileId
      ? `<a class="key" href="${finishURL({projectId:id},next.fileId,true)}">${next.label}</a><button class="ghost" ${open} data-resume="editor">打开项目</button>`
      : `<button class="key" ${open} data-resume="${next.action}" data-resume-draft="${esc(next.draftId||'')}">${next.label}</button>`;
    if (actions._view !== html) {
      const focused = actions.contains(document.activeElement);
      actions.innerHTML = html;
      actions._view = html;
      if (focused) actions.querySelector('.key')?.focus({preventScroll:true});
    }
    card.dataset.activeJob = active ? 'true' : 'false';
  } catch (error) {
    if (current()) card.querySelector('.resume-status').textContent = '暂时无法查看进度';
  } finally { card.loading = false; }
}
async function newBlank(title='新的口播项目',initialStage=1){await save();const p=await api('/api/new',{title});await refreshProjects();await load(p.id,initialStage);return p;}
async function openManuscript(intent='polish',fresh=false,draft=null,initialText=null){
 await save();v2Status=await api('/api/v2/status');
 const projectId=draft?(draft.project_id||''):(fresh?'':P?.id||'');
 if(intent==='import'&&!draft)return openQuickImport(projectId,initialText||'');
 manuscript=draft||await api('/api/v2/draft',{title:fresh?'我的口播稿':P?.title||'我的口播稿',text:initialText??(fresh?'':P?.pages.map(p=>p.text).join('\n\n')||''),intent,project_id:projectId});
 openDialog(intent==='import'?'导入稿件 · 分析与排页':'稿件编辑 · AI 润色');$('#dialog').classList.add('manuscript-dialog');
 $('#dialog-body').innerHTML=`<div class="manuscript-head"><input id="manuscript-title" aria-label="稿件名称" value="${esc(manuscript.title)}"><button class="ghost" id="manuscript-file">导入文件</button><button class="ghost" id="format-tools" aria-expanded="false">更多格式</button><button class="ghost" id="draft-save">保存草稿</button></div><div class="manuscript-layout"><div><div id="markdown-editor"></div><div id="draft-review"></div></div><aside class="manuscript-side"><h3>${intent==='import'?'让内容自然成页':'让表达更适合开口'}</h3><p class="hint">${v2Status.ai.ready?'本次请求会把稿件发送给已配置的模型服务。':'当前为 Codex 待办协作。提交后，在聊天中让 AI 处理工作台待办；结果会自动出现在这里。'}</p><label>润稿要求</label><textarea id="draft-instruction">${esc(manuscript.instruction||'保留事实、数字和专名。表达自然易讲，不虚构经历。')}</textarea><button class="key" id="draft-rewrite">AI 润稿</button><button class="key dark" id="draft-paginate">让 AI 分页</button><div id="draft-state" class="ai-state"></div><label class="checkline" ${projectId?'':'hidden'}><input type="checkbox" id="draft-append">追加到现有页面</label><button class="key" id="draft-create">用现稿分页</button><p class="hint">可以等 AI 的分页建议，也可以直接按段落把现稿分成几页。</p></aside></div>`;
 mdSavedText=manuscript.text||'';
 const editorGeneration=++mdGeneration;let editorInstance;mdEditor=editorInstance=new Vditor('markdown-editor',{cdn:'/vendor/vditor',lang:'zh_CN',mode:'ir',height:450,cache:{enable:false},value:mdSavedText,placeholder:'粘贴文章、输入口播稿，或导入 Markdown / 文档…',toolbar:['headings','bold','italic','strike','|','list','ordered-list','check','outdent','indent','quote','line','|','code','inline-code','link','table','upload','|','undo','redo','both','preview','fullscreen'],upload:{accept:'image/*',handler:async files=>{try{for(const f of files){if(!/^image\/(png|jpeg|webp|gif)$/.test(f.type))return '支持 PNG、JPEG、WebP 和 GIF';const r=await fetch('/api/upload?name='+encodeURIComponent(f.name),{method:'POST',headers:{'X-Studio-Token':token},body:f});const j=await r.json();if(!r.ok)throw Error(j.error);mdEditor.insertValue('!['+f.name.replace(/[\[\]]/g,'')+']('+j.url+')\n');}return null;}catch(e){return e.message;}}},preview:{hljs:{enable:false},math:{engine:'KaTeX'},markdown:{sanitize:true}},input:()=>{if(editorGeneration!==mdGeneration)return;$('#draft-state').textContent='稿件已修改 · 点击保存或 AI 处理';clearTimeout(mdEditor._save);mdEditor._save=setTimeout(()=>saveManuscript().catch(e=>toast(e.message,true)),1000);},after:()=>queueMicrotask(()=>{editorInstance._ready=true;if(editorInstance._disposed||editorGeneration!==mdGeneration){editorInstance.destroy();return;}updateDraftState();})});
 $('#format-tools').onclick=e=>{const expanded=$('#markdown-editor').classList.toggle('full-format');e.target.setAttribute('aria-expanded',String(expanded));e.target.textContent=expanded?'收起格式':'更多格式';};
 $('#draft-save').onclick=()=>saveManuscript().then(()=>toast('稿件草稿已保存')).catch(e=>toast(e.message,true));
 $('#draft-rewrite').onclick=()=>requestDraft('rewrite');$('#draft-paginate').onclick=()=>requestDraft('paginate');
 $('#draft-create').onclick=createFromDraft;$('#manuscript-file').onclick=()=>importManuscriptFile();
 clearInterval(draftPoll);draftPoll=setInterval(checkDraft,1800);updateDraftState();
}
async function saveManuscript(){if(!mdEditor||!manuscript)return;if(!mdEditor._ready)return manuscript;clearTimeout(mdEditor._save);if(manuscript.status==='running')return manuscript;const text=mdEditor.getValue();if(text===mdSavedText&&manuscript.title===$('#manuscript-title').value&&manuscript.instruction===$('#draft-instruction').value)return manuscript;manuscript=await api('/api/v2/draft',{id:manuscript.id,text,title:$('#manuscript-title').value,instruction:$('#draft-instruction').value});mdSavedText=text;return manuscript;}
async function requestDraft(kind){try{await saveManuscript();manuscript=await api('/api/v2/ai',{id:manuscript.id,kind});updateDraftState();}catch(e){toast(e.message,true);}}
async function checkDraft(){if(!manuscript||!$('#dialog').open)return;try{const d=await api('/api/v2/draft?id='+manuscript.id);if(d.status!==manuscript.status){manuscript=d;updateDraftState();}}catch(e){}}
function updateDraftState(){if(!manuscript||!$('#draft-state'))return;const state={editing:'草稿已保存，可开始 AI 润稿或分析。',running:'AI 正在处理…',pending_host:`等待你回原 Codex 对话提交任务，处理后可在这里查看建议。\n任务 ${manuscript.id}\n在聊天中说：“处理口播工作台的待办稿件”。`,review:'建议已返回，原稿保留。请检查后采用。',adopted:'已采用，可继续创建项目。',error:'处理失败：'+manuscript.error};$('#draft-state').textContent=state[manuscript.status]||'稿件已保存';const busy=manuscript.status==='running'||!mdEditor?._ready;$('#draft-rewrite').disabled=busy;$('#draft-paginate').disabled=busy;$('#draft-create').disabled=busy;if(mdEditor?._ready){if(busy)mdEditor.disabled();else mdEditor.enable();}
 const review=$('#draft-review');review.replaceChildren();
 $('#draft-create').textContent=manuscript.kind==='paginate'&&manuscript.pages&&['review','adopted'].includes(manuscript.status)?'采用这组分页':'用现稿分页';

 if(manuscript.status==='review'&&manuscript.kind==='rewrite'){review.innerHTML=`<div class="draft-compare"><section><h3>原稿 · 保留不变</h3><div class="proposal">${esc(manuscript.text)}</div></section><section><h3>AI 建议 · 可修改后采用</h3><div class="proposal" id="draft-proposal" contenteditable="true">${esc(manuscript.proposal)}</div></section></div><div class="action-row"><button class="key" id="draft-adopt">确认采用润色稿</button><button class="ghost" id="draft-discard">保留原稿</button></div>`;$('#draft-adopt').onclick=async()=>{try{if(mdEditor.getValue()!==manuscript.text)throw Error('原稿已修改，请重新润稿，避免覆盖新内容');manuscript=await api('/api/v2/adopt',{id:manuscript.id,text:$('#draft-proposal').innerText});mdSavedText=manuscript.text;mdEditor.setValue(mdSavedText);updateDraftState();}catch(e){toast(e.message,true)}};$('#draft-discard').onclick=()=>{review.replaceChildren();$('#draft-state').textContent='保留原稿，AI 建议尚未采用';};}
 if(manuscript.pages&&['review','adopted'].includes(manuscript.status)&&manuscript.kind==='paginate')review.innerHTML=`<h3>分页预览 · ${manuscript.pages.length} 页</h3><div class="pagination-preview">${manuscript.pages.map((pg,i)=>`<article><b>${i+1}. ${esc(pg.title)}</b><p>${esc(pg.text)}</p><small>${pg.text.length} 字 · ${esc(manuscript.reasons?.[i]||'')}</small></article>`).join('')}</div>`;
}
async function createFromDraft(){
  try{
    await saveManuscript();
    if(!manuscript.text.trim())throw Error('先输入稿件或导入文件。');
    const pid=manuscript.project_id;
    const current=pid?await api('/api/project?id='+pid):null;
    const append=$('#draft-append')?.checked||false;
    if(!append&&current?.pages.some(page=>page.text.trim()||page.tags.length||page.media_id||page.notes?.trim()||page.duration)
       &&!confirm('用这份稿件替换现有页面？可以在项目设置里恢复旧版本。'))return;
    const p=await api('/api/v2/create',{id:manuscript.id,project_id:pid,version:current?.version,append});
    closeDialog();
    await refreshProjects();
    await load(p.id,1);
    toast('稿件已分页，可逐页修改。');
  }catch(e){toast(e.message,true);}
}
function pickDocument(onText){
  const input=document.createElement('input');
  input.type='file';
  input.accept='.txt,.md,.docx,.pdf,.pptx';
  input.onchange=async()=>{
    const file=input.files[0];
    if(!file)return;
    try{
      let text;
      if(/\.(md|txt)$/i.test(file.name))text=await file.text();
      else{
        const result=await fetch('/api/upload?name='+encodeURIComponent(file.name),{method:'POST',headers:{'X-Studio-Token':token},body:file});
        const payload=await result.json();
        if(!result.ok)throw Error(payload.error);
        text=(await api('/api/v2/extract',{path:payload.path})).text;
      }
      await onText(text,file.name.replace(/\.[^.]+$/,''));
    }catch(error){toast(error.message,true)}
  };
  input.click();
}
function importManuscriptFile(){
  const owner=mdEditor;
  pickDocument(async text=>{
    if(mdEditor!==owner||!owner?._ready)return;
    mdEditor.setValue(text);await saveManuscript();
  });
}
function openQuickImport(projectId,initialText){
  openDialog('把稿件分成提词页',`
    <div class="action-row"><button class="ghost" id="manuscript-file">选择稿件文件</button></div>
    <label for="import-text">也可以直接粘贴稿件</label>
    <textarea id="import-text" class="import-text" placeholder="粘贴已经写好的口播稿"></textarea>
    <div class="import-actions"><button class="key" id="draft-create" disabled>使用这些提词页</button>
      <button class="ghost" id="import-polish">交给 AI 润色或分页</button>
      ${projectId?'<label><input id="draft-append" type="checkbox">追加到已有页面</label>':''}</div>
    <p id="page-count" role="status"></p><div id="page-preview" class="pagination-preview"></div>`);
  const input=$('#import-text'), use=$('#draft-create'), count=$('#page-count'), preview=$('#page-preview');
  let title='我的口播稿',revision=0,delay;
  async function update(){
    const current=++revision;
    use.disabled=true;
    clearTimeout(delay);
    if(!input.value.trim()){count.textContent='';preview.replaceChildren();return;}
    count.textContent='正在分页…';
    delay=setTimeout(async()=>{
      try{
        const pages=await api('/api/v2/page-preview',{text:input.value});
        if(!input.isConnected||current!==revision)return;
        count.textContent='共 '+pages.length+' 页，可在项目里逐页修改。';
        preview.innerHTML=pages.map((text,i)=>`<article><b>第 ${i+1} 页</b><p>${esc(text)}</p></article>`).join('');
        use.disabled=!pages.length;
      }catch(error){if(current===revision)count.textContent=error.message}
    },150);
  }
  input.oninput=update;
  input.value=initialText;update();
  $('#manuscript-file').onclick=()=>pickDocument((text,name)=>{if(input.isConnected){input.value=text;title=name;update()}});
  $('#import-polish').onclick=async()=>{
    const text=input.value;
    const draft=await api('/api/v2/draft',{text,title,project_id:projectId,intent:'polish'});
    await openManuscript('polish',!projectId,draft);
  };
  use.onclick=async()=>{
    use.disabled=true;
    try{
      const current=projectId?await api('/api/project?id='+projectId):null;
      const append=$('#draft-append')?.checked||false;
      if(current&&!append&&current.pages.some(p=>p.text.trim()||p.tags.length||p.media_id||p.notes?.trim()||p.duration)
          &&!confirm('替换已有提词页？可以在项目设置中恢复。'))return;
      const draft=await api('/api/v2/draft',{text:input.value,title,project_id:projectId,intent:'import'});
      const project=await api('/api/v2/create',{id:draft.id,project_id:projectId,version:current?.version,append});
      closeDialog();await refreshProjects();await load(project.id,1);
    }catch(error){count.textContent=error.message}
    finally{use.disabled=false}
  };
}
const draftStatusLabels={editing:'草稿',pending_host:'等待 AI 处理',running:'处理中',review:'可查看建议',adopted:'已采用',error:'需要重试'};
async function listDrafts(){const drafts=await api('/api/v2/drafts'+(homeMode?'':'?project_id='+encodeURIComponent(P.id)));openDialog('稿件与 AI 待办',`<p class="hint">待办稿件可由当前 Codex 读取处理，AI 返回后仍需你确认采用。</p><div class="pending-list">${drafts.map(d=>`<button class="recent-card" data-draft="${d.id}"><strong>${esc(d.title||'稿件')}</strong><small>${esc(draftStatusLabels[d.status]||'稿件')} · ${d.kind==='rewrite'?'润稿':d.kind==='paginate'?'分页':'编辑'}</small></button>`).join('')||'还没有稿件'}</div>`);$$('[data-draft]').forEach(b=>b.onclick=()=>openManuscript('polish',false,drafts.find(d=>d.id===b.dataset.draft)));}
async function microphoneDialog(){openDialog('麦克风与本地语音测试',`<p class="mic-note">选择设备后开始测试。浏览器会请求麦克风权限；声音由本地识别处理，测试不保存录音。</p><select id="mic-device" class="mic-device" aria-label="麦克风"><option value="">系统默认麦克风</option></select><div class="mic-meter"><i id="mic-level"></i></div><div class="action-row"><button class="key" id="mic-start">开始语音测试</button><button class="ghost" id="mic-level-only">仅测试音量</button><button class="ghost" id="mic-stop">停止</button></div><p class="mic-note" id="mic-state">尚未启动麦克风</p><div class="mic-transcript" id="mic-text">读一句话，识别结果会显示在这里。</div>`);micTester=new StudioMicrophone({onLevel:n=>{if($('#mic-level'))$('#mic-level').style.width=n*100+'%'},onStatus:s=>{if($('#mic-state'))$('#mic-state').textContent=s},onText:s=>{if($('#mic-text'))$('#mic-text').textContent=s}});async function devices(){const d=await micTester.devices();const val=$('#mic-device').value;$('#mic-device').innerHTML='<option value="">系统默认麦克风</option>'+d.map((x,i)=>`<option value="${esc(x.deviceId)}">${esc(x.label||'麦克风 '+(i+1))}</option>`).join('');$('#mic-device').value=val;}async function start(asr){try{const owner=micTester;const ready=await owner.start($('#mic-device').value,asr);if(ready&&micTester===owner)await devices()}catch(e){}}$('#mic-start').onclick=()=>start(true);$('#mic-level-only').onclick=()=>start(false);$('#mic-stop').onclick=async()=>{await micTester.stop();$('#mic-state').textContent='已停止，麦克风已释放'};$('#mic-device').onchange=()=>{if(micTester.active)start(true)};try{await devices()}catch(e){} }
async function aiSettings(){const c=(await api('/api/v2/status')).ai;openDialog('AI 服务 · 默认 Codex 协作',`<p class="hint">不配置时使用 Codex 待办协作。可选配置兼容 Chat Completions 的模型服务，密钥仅保存在本机服务设置，不进入工程包。</p><div class="field"><label>完整 API 地址</label><input id="ai-url" value="${esc(c.url)}" placeholder="https://…/v1/chat/completions"></div><div class="field"><label>模型名称</label><input id="ai-model" value="${esc(c.model)}"></div><div class="field"><label>密钥 ${c.has_key?'（已保存；留空保留）':''}</label><input id="ai-key" type="password" autocomplete="off"></div><button class="key" id="ai-save">保存本机设置</button>`);$('#ai-save').onclick=async()=>{try{await api('/api/v2/settings',{url:$('#ai-url').value,model:$('#ai-model').value,key:$('#ai-key').value});closeDialog();if(homeMode)dashboard();toast('AI 设置已保存')}catch(e){toast(e.message,true)}};}
document.addEventListener('click',async e=>{const b=e.target.closest('[data-v2],[data-open-project]');if(!b)return;try{if(b.dataset.openProject){
  const action = b.dataset.resume;
  const targetStage = {manuscript:1,prompter:1,recording:2,'import-recording':2,relink:2,cuts:2,editor:3,captions:3,finish:3}[action];
  await save();await load(b.dataset.openProject,targetStage);
  if($('#dialog').open)return;
  if(b.dataset.resumeDraft){const draft=await api('/api/v2/draft?id='+b.dataset.resumeDraft);await openManuscript('polish',false,draft);}
  else if(action==='prompter')await launchPrompt();
  else if(action==='manuscript')$('#page-text')?.focus();
  else if(action==='import-recording')mediaDialog();
  else if(action==='relink')relinkDialog();
  else if(action==='cuts'&&!busy)openCutReview();
  else if(action==='finish'||action==='captions')await openFinishReview({captions:action==='captions'});
  return;}switch(b.dataset.v2){case 'home':await save();await dashboard();break;case 'import-project':projectImportDialog();break;case 'blank':await newBlank();break;case 'video-new':mediaDialog(true);break;case 'import-new':await openManuscript('import',true);break;case 'polish-new':await openManuscript('polish',true);break;case 'import':await openManuscript('import');break;case 'polish':await openManuscript('polish');break;case 'mic':await microphoneDialog();break;case 'drafts':await listDrafts();break;case 'ai-settings':await aiSettings();break;}}catch(e){toast(e.message,true)}});
scriptDialog=()=>openManuscript('import');rewriteDialog=()=>openManuscript('polish');
launchPrompt=async function(){await save();promptWindow=window.open(`/prompter?id=${P.id}&page=${selected}`,'studio-prompter','width=1200,height=900');if(!promptWindow)toast('请允许本站弹出提词窗口',true);};
$('#new-project').onclick=()=>newBlank();const oldSettings=$('#settings').onclick;$('#settings').onclick=()=>{
  if(!homeMode)return oldSettings();
  openDialog('工作台设置',`<p>本机工作台 V${esc(v2Status.version)}。写稿、提词可直接开始。</p>
    <div class="action-row"><button class="ghost" data-v2="drafts">稿件和润色建议</button>
    <button class="ghost" data-v2="mic">检查麦克风</button>
    <button class="ghost" data-v2="ai-settings">自定义 AI 服务</button></div>`);
};
const homeBtn=document.createElement('button');homeBtn.className='v2-top-home';homeBtn.textContent='工作台首页';homeBtn.dataset.v2='home';$('.top-actions').prepend(homeBtn);
init=async function(){
  try {
    await refreshProjects();
    const id=new URLSearchParams(location.hash.slice(1)).get('project');
    if(id){await load(id);restoreOpenReview();}
    else await dashboard();
    $('#agent-inbox').disabled=false;
    setInterval(()=>{
      if(homeMode)refreshDashboardResume($('[data-recent-project][data-active-job="true"]'));
      else poll();
    },1600);
  } catch(e) {toast(e.message,true);}
};

const legacyAct=act;act=async function(action,args={}){if(P?.timeline?.mode==='actual')action=({sample:'timeline_sample',final:'timeline_final',approve_final:'approve_timeline'}[action]||action);return legacyAct(action,args);};
