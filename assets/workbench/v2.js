'use strict';
let homeMode=true,projectList=[],v2Status={},manuscript=null,mdEditor=null,mdSavedText='',draftPoll=null,micTester=null,mdGeneration=0;
const icons={import:'<path d="M5 4h11l5 5v15H5zM16 4v6h6M13 13v8m-4-4 4 4 4-4"/>',edit:'<path d="M5 6h9M5 11h7M5 16h5M5 23h17M13 17l2-6 7-7 4 4-7 7z"/>',new:'<rect x="4" y="4" width="22" height="22" rx="5"/><path d="M15 9v12M9 15h12"/>'};
function icon(name){return `<svg viewBox="0 0 30 30" aria-hidden="true">${icons[name]}</svg>`;}
const legacyRender=render,legacyMark=mark,legacyLoad=load,legacyClose=closeDialog;
render=function(){
  if(homeMode)return dashboard();
  legacyRender();
  localStorage.setItem('studio-stage-'+P.id,String(stage));
  refreshWorkflow();
  if(stage===1){
    const toolbar=document.createElement('div');
    toolbar.className='project-cta';
    toolbar.innerHTML='<button class="ghost" data-v2="import">导入稿件</button><button class="ghost" data-v2="polish">AI 润稿</button><button class="ghost" data-v2="mic">测试麦克风</button>';
    $('#main .workflow-metrics').after(toolbar);
  }
  renderTimeline();
};
mark=function(){if(P)syncTimeline();legacyMark();refreshWorkflow();clearTimeout(mark._tl);mark._tl=setTimeout(()=>{if(!document.activeElement?.closest('.timeline-dock')&&!window.tlDragging)renderTimeline()},180);};
load=async function(id,initialStage){
  homeMode=false;
  if(P?.id!==id)timelineExpanded=false;
  const savedStage=Number(localStorage.getItem('studio-stage-'+id));
  stage=initialStage||([1,2,3].includes(savedStage)?savedStage:1);
  tab='plan';
  previewMode='auto';
  document.body.classList.remove('dashboard-mode');
  location.hash='project='+id;
  await legacyLoad(id);
};
closeDialog=function(){clearInterval(draftPoll);draftPoll=null;mdGeneration++;const closingEditor=mdEditor;mdEditor=null;clearTimeout(closingEditor?._save);if(closingEditor?._ready)closingEditor.destroy();else if(closingEditor)closingEditor._disposed=true;if(micTester){micTester.stop();micTester=null;}$('#dialog').classList.remove('manuscript-dialog');legacyClose();};
$('#close-dialog').onclick=()=>safeClose();$('#dialog').addEventListener('cancel',e=>{e.preventDefault();safeClose()});
async function safeClose(){if(mdEditor&&manuscript&&manuscript.status!=='running')try{await saveManuscript()}catch(e){toast(e.message,true);return;}closeDialog();}
function refreshAnnotations(){const doc=new DOMParser().parseFromString(stageOne(),'text/html');const next=doc.querySelector('.annotations');if(next&&$('.annotations'))$('.annotations').replaceWith(next);syncTimeline();renderTimeline();const metrics=$$('.hero-metrics .metric strong');if(metrics[2])metrics[2].textContent=P.pages.reduce((n,p)=>n+p.tags.length,0);}
async function dashboard(){homeMode=true;document.body.classList.add('dashboard-mode');if(location.hash)history.replaceState(null,'',location.pathname);const b=await refreshProjects();projectList=b.projects;v2Status=await api('/api/v2/status');if(!homeMode)return;$('#main').innerHTML=`<div class="dashboard"><div class="dash-intro"><div><h1>做一条<em>口播视频</em></h1><p>准备稿件、录制视频、加字幕并导出。可以从手里的素材直接开始。</p></div><div class="dash-sculpture" aria-hidden="true"></div></div><div class="entry-grid"><button class="entry-card featured" data-v2="import-new">${icon('import')}<strong>导入已有稿件</strong><small>带上你的定稿。分析主题、安排页面，<br>让每一段都说得自然。</small><span class="entry-footer"><b>↗</b></span></button><button class="entry-card" data-v2="polish-new">${icon('edit')}<strong>AI 稿件润色</strong><small>在完整编辑器里整理想法，<br>对比 AI 建议，采用你满意的表达。</small><span class="entry-footer"><b>↗</b></span></button><button class="entry-card" data-v2="blank">${icon('new')}<strong>新建项目</strong><small>从一张空白页开始，<br>自由编排口播、演示与素材。</small><span class="entry-footer"><b>＋</b></span></button></div><div class="recorded-entry"><div><strong>已经录好视频？</strong><p>直接整理视频，或加好字幕再导出。</p></div><button class="key" data-v2="video-new">从视频开始</button></div><div class="dash-recent"><div class="status-pills"><button data-v2="mic" class="${v2Status.speech.ready?'ready':''}">● 麦克风与语音测试</button><button data-v2="ai-settings">${v2Status.ai.ready?'● 模型服务已配置':'◌ Codex 待办协作'}</button><button data-v2="drafts">稿件与 AI 待办</button></div><h2>继续你的创作 </h2><div class="recent-grid">${projectList.map(p=>`<button class="recent-card" data-open-project="${p.id}"><strong>${esc(p.title)}</strong><small>${esc(p.updated.slice(0,16).replace('T',' '))}　继续编辑 ↗</small></button>`).join('')||'<p>创建你的第一个项目，从上方任一入口开始。</p>'}</div></div></div>`;$('#footer-meta').textContent='V2 · 本地口播工作台';}
async function newBlank(title='新的口播项目',initialStage=1){await save();const p=await api('/api/new',{title});await refreshProjects();await load(p.id,initialStage);return p;}
async function openManuscript(intent='polish',fresh=false,draft=null,initialText=null){
 await save();v2Status=await api('/api/v2/status');
 if(fresh&&intent==='import'&&!draft)await newBlank('导入稿件 · 新项目');
 const projectId=draft?.project_id||(fresh&&intent==='polish'?'':P?.id||'');
 manuscript=draft||await api('/api/v2/draft',{title:fresh?'我的口播稿':P?.title||'我的口播稿',text:initialText??(fresh?'':P?.pages.map(p=>p.text).join('\n\n')||''),intent,project_id:projectId});
 openDialog(intent==='import'?'导入稿件 · 分析与排页':'稿件编辑 · AI 润色');$('#dialog').classList.add('manuscript-dialog');
 $('#dialog-body').innerHTML=`<div class="manuscript-head"><input id="manuscript-title" aria-label="稿件名称" value="${esc(manuscript.title)}"><button class="ghost" id="manuscript-file">导入文件</button><button class="ghost" id="draft-save">保存草稿</button></div><div class="manuscript-layout"><div><div id="markdown-editor"></div><div id="draft-review"></div></div><aside class="manuscript-side"><h3>${intent==='import'?'让内容自然成页':'让表达更适合开口'}</h3><p class="hint">${v2Status.ai.ready?'本次请求会把稿件发送给已配置的模型服务。':'当前为 Codex 待办协作。提交后，在聊天中让 AI 处理工作台待办；结果会自动出现在这里。'}</p><label>润稿要求</label><textarea id="draft-instruction">${esc(manuscript.instruction||'保留事实、数字和专名。表达自然易讲，不虚构经历。')}</textarea><button class="key" id="draft-rewrite">AI 润稿</button><button class="key dark" id="draft-paginate">让 AI 分页</button><div id="draft-state" class="ai-state"></div><label class="checkline" ${projectId?'':'hidden'}><input type="checkbox" id="draft-append">追加到现有页面</label><button class="key" id="draft-create">用现稿分页</button><p class="hint">可以等 AI 的分页建议，也可以直接按段落把现稿分成几页。</p></aside></div>`;
 mdSavedText=manuscript.text||'';
 const editorGeneration=++mdGeneration;let editorInstance;mdEditor=editorInstance=new Vditor('markdown-editor',{cdn:'/vendor/vditor',lang:'zh_CN',mode:'ir',height:450,cache:{enable:false},value:mdSavedText,placeholder:'粘贴文章、输入口播稿，或导入 Markdown / 文档…',toolbar:['headings','bold','italic','strike','|','list','ordered-list','check','outdent','indent','quote','line','|','code','inline-code','link','table','upload','|','undo','redo','both','preview','fullscreen'],upload:{accept:'image/*',handler:async files=>{try{for(const f of files){if(!/^image\/(png|jpeg|webp|gif)$/.test(f.type))return '支持 PNG、JPEG、WebP 和 GIF';const r=await fetch('/api/upload?name='+encodeURIComponent(f.name),{method:'POST',headers:{'X-Studio-Token':token},body:f});const j=await r.json();if(!r.ok)throw Error(j.error);mdEditor.insertValue('!['+f.name.replace(/[\[\]]/g,'')+']('+j.url+')\n');}return null;}catch(e){return e.message;}}},preview:{hljs:{enable:false},math:{engine:'KaTeX'},markdown:{sanitize:true}},input:()=>{if(editorGeneration!==mdGeneration)return;$('#draft-state').textContent='稿件已修改 · 点击保存或 AI 处理';clearTimeout(mdEditor._save);mdEditor._save=setTimeout(()=>saveManuscript().catch(e=>toast(e.message,true)),1000);},after:()=>queueMicrotask(()=>{editorInstance._ready=true;if(editorInstance._disposed||editorGeneration!==mdGeneration){editorInstance.destroy();return;}updateDraftState();})});
 $('#draft-save').onclick=()=>saveManuscript().then(()=>toast('稿件草稿已保存')).catch(e=>toast(e.message,true));
 $('#draft-rewrite').onclick=()=>requestDraft('rewrite');$('#draft-paginate').onclick=()=>requestDraft('paginate');
 $('#draft-create').onclick=createFromDraft;$('#manuscript-file').onclick=()=>importManuscriptFile();
 clearInterval(draftPoll);draftPoll=setInterval(checkDraft,1800);updateDraftState();
}
async function saveManuscript(){if(!mdEditor||!manuscript)return;if(!mdEditor._ready)return manuscript;clearTimeout(mdEditor._save);if(manuscript.status==='running')return manuscript;const text=mdEditor.getValue();if(text===mdSavedText&&manuscript.title===$('#manuscript-title').value&&manuscript.instruction===$('#draft-instruction').value)return manuscript;manuscript=await api('/api/v2/draft',{id:manuscript.id,text,title:$('#manuscript-title').value,instruction:$('#draft-instruction').value});mdSavedText=text;return manuscript;}
async function requestDraft(kind){try{await saveManuscript();manuscript=await api('/api/v2/ai',{id:manuscript.id,kind});updateDraftState();}catch(e){toast(e.message,true);}}
async function checkDraft(){if(!manuscript||!$('#dialog').open)return;try{const d=await api('/api/v2/draft?id='+manuscript.id);if(d.status!==manuscript.status){manuscript=d;updateDraftState();}}catch(e){}}
function updateDraftState(){if(!manuscript||!$('#draft-state'))return;const state={editing:'草稿已保存，可开始 AI 润稿或分析。',running:'AI 正在处理…',pending_host:`等待 Codex 处理。\n任务 ${manuscript.id}\n在聊天中说：“处理口播工作台的待办稿件”。`,review:'建议已返回，原稿保留。请检查后采用。',adopted:'已采用，可继续创建项目。',error:'处理失败：'+manuscript.error};$('#draft-state').textContent=state[manuscript.status]||'稿件已保存';const busy=manuscript.status==='running'||!mdEditor?._ready;$('#draft-rewrite').disabled=busy;$('#draft-paginate').disabled=busy;$('#draft-create').disabled=busy;if(mdEditor?._ready){if(busy)mdEditor.disabled();else mdEditor.enable();}
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
async function importManuscriptFile(){const inp=document.createElement('input');inp.type='file';inp.accept='.txt,.md,.docx,.pdf,.pptx';inp.onchange=async()=>{const f=inp.files[0];if(!f)return;try{let text;if(/\.(md|txt)$/i.test(f.name))text=await f.text();else{const r=await fetch('/api/upload?name='+encodeURIComponent(f.name),{method:'POST',headers:{'X-Studio-Token':token},body:f});const j=await r.json();if(!r.ok)throw Error(j.error);text=(await api('/api/v2/extract',{path:j.path})).text;}mdEditor.setValue(text);await saveManuscript();if(manuscript.intent==='import')await requestDraft('paginate');}catch(e){toast(e.message,true)}};inp.click();}
const draftStatusLabels={editing:'草稿',pending_host:'等待 AI 处理',running:'处理中',review:'可查看建议',adopted:'已采用',error:'需要重试'};
async function listDrafts(){const drafts=await api('/api/v2/drafts');openDialog('稿件与 AI 待办',`<p class="hint">待办稿件可由当前 Codex 读取处理，AI 返回后仍需你确认采用。</p><div class="pending-list">${drafts.map(d=>`<button class="recent-card" data-draft="${d.id}"><strong>${esc(d.title||'稿件')}</strong><small>${esc(draftStatusLabels[d.status]||'稿件')} · ${d.kind==='rewrite'?'润稿':d.kind==='paginate'?'分页':'编辑'}</small></button>`).join('')||'还没有稿件'}</div>`);$$('[data-draft]').forEach(b=>b.onclick=()=>openManuscript('polish',false,drafts.find(d=>d.id===b.dataset.draft)));}
async function microphoneDialog(){openDialog('麦克风与本地语音测试',`<p class="mic-note">选择设备后开始测试。浏览器会请求麦克风权限；声音由本地识别处理，测试不保存录音。</p><select id="mic-device" class="mic-device" aria-label="麦克风"><option value="">系统默认麦克风</option></select><div class="mic-meter"><i id="mic-level"></i></div><div class="action-row"><button class="key" id="mic-start">开始语音测试</button><button class="ghost" id="mic-level-only">仅测试音量</button><button class="ghost" id="mic-stop">停止</button></div><p class="mic-note" id="mic-state">尚未启动麦克风</p><div class="mic-transcript" id="mic-text">读一句话，识别结果会显示在这里。</div>`);micTester=new StudioMicrophone({onLevel:n=>{if($('#mic-level'))$('#mic-level').style.width=n*100+'%'},onStatus:s=>{if($('#mic-state'))$('#mic-state').textContent=s},onText:s=>{if($('#mic-text'))$('#mic-text').textContent=s}});async function devices(){const d=await micTester.devices();const val=$('#mic-device').value;$('#mic-device').innerHTML='<option value="">系统默认麦克风</option>'+d.map((x,i)=>`<option value="${esc(x.deviceId)}">${esc(x.label||'麦克风 '+(i+1))}</option>`).join('');$('#mic-device').value=val;}async function start(asr){try{const owner=micTester;const ready=await owner.start($('#mic-device').value,asr);if(ready&&micTester===owner)await devices()}catch(e){}}$('#mic-start').onclick=()=>start(true);$('#mic-level-only').onclick=()=>start(false);$('#mic-stop').onclick=async()=>{await micTester.stop();$('#mic-state').textContent='已停止，麦克风已释放'};$('#mic-device').onchange=()=>{if(micTester.active)start(true)};try{await devices()}catch(e){} }
async function aiSettings(){const c=(await api('/api/v2/status')).ai;openDialog('AI 服务 · 默认 Codex 协作',`<p class="hint">不配置时使用 Codex 待办协作。可选配置兼容 Chat Completions 的模型服务，密钥仅保存在本机服务设置，不进入工程包。</p><div class="field"><label>完整 API 地址</label><input id="ai-url" value="${esc(c.url)}" placeholder="https://…/v1/chat/completions"></div><div class="field"><label>模型名称</label><input id="ai-model" value="${esc(c.model)}"></div><div class="field"><label>密钥 ${c.has_key?'（已保存；留空保留）':''}</label><input id="ai-key" type="password" autocomplete="off"></div><button class="key" id="ai-save">保存本机设置</button>`);$('#ai-save').onclick=async()=>{try{await api('/api/v2/settings',{url:$('#ai-url').value,model:$('#ai-model').value,key:$('#ai-key').value});closeDialog();if(homeMode)dashboard();toast('AI 设置已保存')}catch(e){toast(e.message,true)}};}
document.addEventListener('click',async e=>{const b=e.target.closest('[data-v2],[data-open-project]');if(!b)return;try{if(b.dataset.openProject){await save();await load(b.dataset.openProject);return;}switch(b.dataset.v2){case 'home':await save();await dashboard();break;case 'blank':await newBlank();break;case 'video-new':await newBlank('新的口播视频',2);mediaDialog();break;case 'import-new':await openManuscript('import',true);break;case 'polish-new':await openManuscript('polish',true);break;case 'import':await openManuscript('import');break;case 'polish':await openManuscript('polish');break;case 'mic':await microphoneDialog();break;case 'drafts':await listDrafts();break;case 'ai-settings':await aiSettings();break;}}catch(e){toast(e.message,true)}});
scriptDialog=()=>openManuscript('import');rewriteDialog=()=>openManuscript('polish');
launchPrompt=async function(){await save();promptWindow=window.open(`/prompter?id=${P.id}&page=${selected}`,'studio-prompter','width=1200,height=900');if(!promptWindow)toast('请允许本站弹出提词窗口',true);};
$('#new-project').onclick=()=>newBlank();const oldSettings=$('#settings').onclick;$('#settings').onclick=()=>homeMode?aiSettings():oldSettings();
const homeBtn=document.createElement('button');homeBtn.className='v2-top-home';homeBtn.textContent='工作台首页';homeBtn.dataset.v2='home';$('.top-actions').prepend(homeBtn);
init=async function(){try{await refreshProjects();const id=new URLSearchParams(location.hash.slice(1)).get('project');if(id)await load(id);else await dashboard();setInterval(()=>{if(!homeMode)poll()},1600);}catch(e){toast(e.message,true)}};

const legacyAct=act;act=async function(action,args={}){if(P?.timeline?.mode==='actual')action=({sample:'timeline_sample',final:'timeline_final',approve_final:'approve_timeline'}[action]||action);return legacyAct(action,args);};
