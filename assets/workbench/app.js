'use strict';
const $=s=>document.querySelector(s),$$=s=>[...document.querySelectorAll(s)],esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const makeId=p=>p+'_'+crypto.randomUUID().replaceAll('-','').slice(0,12),sec=n=>Number(n||0).toFixed(2),fmt=n=>`${Math.floor(n/60)}:${String(Math.floor(n%60)).padStart(2,'0')}`;
let P=null,token='',stage=1,selected='',tab='plan',dirty=false,saving=null,timer=null,undo=[],jobsSeen=new Set(),busy=false,previewMode='auto',filePurpose='',doctorInfo={},promptWindow=null;
const kindNames={speech:'口播页',showcase:'成品展示',demo:'演示页',pause:'停顿 / 转场'};
const tagKinds={product:['▧','产品实物'],sticker:['✦','动态贴纸'],flow:['⇄','流程动画'],demo:['▶','演示画面'],title:['T','重点字幕'],sfx:['♫','提示音效']};
function toast(text,error=false){const el=$('#toast');el.textContent=text;el.classList.toggle('error',error);el.hidden=false;clearTimeout(el._timer);el._timer=setTimeout(()=>el.hidden=true,error?9000:4500)}
async function api(path,data){const headers=token?{'X-Studio-Token':token}:{};if(data)headers['Content-Type']='application/json';const r=await fetch(path,{method:data?'POST':'GET',headers,body:data?JSON.stringify(data):undefined});const result=await r.json();if(!r.ok)throw Error(result.error||'请求失败');return result}
function currentPage(){return P.pages.find(p=>p.id===selected)||P.pages[0]}
function fileURL(id,download=false){return `/file/${P.id}/${id}${download?'?download=1':''}`}
function assetURL(id){return `/asset/${P.id}/${id}`}
function snapshot(){undo.push(JSON.stringify(P));if(undo.length>35)undo.shift()}
function mark(){dirty=true;$('#save-status').textContent='保存中…';localStorage.setItem('studio-draft-'+P.id,JSON.stringify(P));clearTimeout(timer);timer=setTimeout(()=>save().catch(e=>toast(e.message,true)),700)}
async function save(){clearTimeout(timer);if(saving)await saving;if(!dirty||!P)return;const payload=JSON.parse(JSON.stringify(P));dirty=false;
saving=api('/api/save',payload).then(result=>{P.version=result.version;P.history=result.history;P.rough=result.rough;P.rough_current=result.rough_current;P.approvals=result.approvals;P.qa=result.qa;refreshWorkflow();P.pages.forEach(pg=>{const saved=result.pages.find(x=>x.id===pg.id);if(saved&&saved.text===pg.text){const anchor=pg.id===selected?$('#anchor'):null;
if(anchor && JSON.stringify(pg.sentences)!==JSON.stringify(saved.sentences)){
  const value=anchor.value;
  anchor.replaceChildren(new Option('整页内容',''),...saved.sentences.map(s=>new Option(s.text.slice(0,28),s.id)));
  if(saved.sentences.some(s=>s.id===value))anchor.value=value;
}
pg.sentences=saved.sentences;if(JSON.stringify(pg.tags)===JSON.stringify(payload.pages.find(x=>x.id===pg.id)?.tags))pg.tags=saved.tags}});$('#save-status').textContent='已保存在本机';$('#save-status').classList.remove('error');if(!dirty)localStorage.removeItem('studio-draft-'+P.id)}).catch(e=>{dirty=true;$('#save-status').textContent='保存失败 · 草稿已留存';$('#save-status').classList.add('error');throw e}).finally(()=>saving=null);await saving;if(dirty)await save()}
async function refreshProjects(){const b=await api('/api/bootstrap');token=b.token;doctorInfo=b.doctor;$('#projects').innerHTML=b.projects.map(x=>`<option value="${x.id}">${esc(x.title)}</option>`).join('');if(P)$('#projects').value=P.id;return b}
async function load(id){clearTimeout(timer);localStorage.setItem('studio-current-project',id);P=await api('/api/project?id='+id);dirty=false;selected=P.pages.find(pg=>pg.id===localStorage.getItem('studio-page-'+id))?.id||P.pages[0]?.id||'';undo=[];$('#projects').value=P.id;render();const draft=localStorage.getItem('studio-draft-'+id);if(draft)toast('发现未保存的浏览器草稿，可在设置中恢复。');await poll()}
let dialogOpener=null,dialogOpenerSelector='';
function openDialog(title,body){
  const dialog=$('#dialog');
  if(!dialog.open){
    dialogOpener=document.activeElement;
    const attr=['data-workflow','data-cmd','data-v2','data-illustrate','data-tl'].find(key=>dialogOpener?.hasAttribute(key));
    dialogOpenerSelector=dialogOpener?.id?'#'+CSS.escape(dialogOpener.id):attr?'['+attr+'="'+CSS.escape(dialogOpener.getAttribute(attr))+'"]':'';
  }
  $('#dialog-title').textContent=title;$('#dialog-body').innerHTML=body||'';
  if(!dialog.open)dialog.showModal();
}
function closeDialog(){
  const dialog=$('#dialog');
  if(!dialog.open)return;
  dialog.close();
  if(document.activeElement===document.body){
    const origin=dialogOpener?.isConnected?dialogOpener:dialogOpenerSelector?document.querySelector(dialogOpenerSelector):null;
    (origin||document.querySelector('.workflow-primary'))?.focus({preventScroll:true});
  }
}
async function act(action,args={}){try{await save();const job=await api('/api/action',{project_id:P.id,action,args});busy=true;document.body.classList.add('busy');showJob(job);closeDialog();return job}catch(e){toast(e.message,true);throw e}}
function showJob(j){$('#jobbar').hidden=false;$('#job-title').textContent={auto_captions:'正在自动加字幕',captions_from_file:'正在导入字幕',prepare_rough:'正在准备剪后试听',prepare_video_tools:'准备视频工具',prepare_transcription:'准备自动字幕',prepare_follow:'准备跟读',transcribe:'识别说话内容',analyze_cuts:'查找长停顿',render_rough:'生成整理后的预览',plan:'生成字幕',sample:'生成代表样片',final:'输出完整成片',gif:'GIF 工厂制作'}[j.action]||'工作台正在处理';$('#job-message').textContent=j.message;$('#job-percent').textContent=Math.round(j.progress*100)+'%';$('.job-progress i').style.width=j.progress*100+'%'}
async function poll(){if(!P||homeMode)return;const pid=P.id;try{const list=await api('/api/jobs?id='+pid);if(homeMode||P.id!==pid)return;const active=list.find(j=>['running','queued'].includes(j.status));busy=!!active;document.body.classList.toggle('busy',busy);if(active)showJob(active);else $('#jobbar').hidden=true;
let reload=false;for(const j of list){if(['done','error','interrupted'].includes(j.status)&&!jobsSeen.has(j.id)){jobsSeen.add(j.id);if(Date.now()-Date.parse(j.created)<1800000){reload=true;toast(j.status==='done'?(j.result?.message||'任务完成'):(j.error||j.message),j.status!=='done');if(j.result?.project_id){await refreshProjects();await load(j.result.project_id);return}}}}
if(reload&&!dirty&&!saving){const latest=await api('/api/project?id='+pid);if(homeMode||P.id!==pid||dirty||saving)return;P=latest;
const direct=list.find(j=>j.result?.ready_for_captions&&j.result.id===P.source_id);
if(direct&&localStorage.getItem('studio-routed-'+pid)!==direct.id){
  localStorage.setItem('studio-routed-'+pid,direct.id);
  if(stage===2){stage=3;tab='captions';previewMode='auto';}
}
if(!P.pages.some(x=>x.id===selected))selected=P.pages[0]?.id;render();await refreshProjects()}}
catch(e){$('#save-status').textContent='连接中断 · 请保留页面'}}
function stageHeader(metrics){return `
<section id="workflow-guide" class="workflow-guide" aria-label="当前操作"></section>
<div class="hero-metrics workflow-metrics" aria-label="项目概况">${metrics.map(([v,l])=>`<div class="metric"><strong>${v}</strong><small>${l}</small></div>`).join('')}</div>`}
function render(){if(!P)return;$$('[data-stage]').forEach(el=>{el.disabled=false;const current=Number(el.dataset.stage)===stage;el.classList.toggle('active',current);if(current)el.setAttribute('aria-current','step');else el.removeAttribute('aria-current')});$('#main').innerHTML=stage===1?stageOne():stage===2?stageTwo():stageThree();$('#footer-meta').textContent=P.title;bindStage();document.body.classList.toggle('busy',busy)}
function stageOne(){const pg=currentPage(),words=P.pages.reduce((n,p)=>n+p.text.length,0),tags=P.pages.reduce((n,p)=>n+p.tags.length,0);return stageHeader([[String(P.pages.length).padStart(2,'0'),'口播页面'],[fmt(words/P.settings.speech_rate*60),'预计时长'],[tags,'制作标记']])+`
<div class="workspace"><aside class="panel"><div class="panel-head">稿件分页 <small>${P.pages.length} 页</small></div><div class="page-list">${P.pages.map((p,i)=>`<article class="page-card ${pg?.id===p.id?'selected':''}" tabindex="0" role="button" draggable="true" data-page="${p.id}" aria-label="第 ${i+1} 页 ${esc(p.title)}"><div class="num"><span>${String(i+1).padStart(2,'0')} / ${esc(kindNames[p.type])}</span><span>⠿</span></div><h3>${esc(p.title||p.text.slice(0,18)||'新的页面')}</h3><div class="mini-lines"><i></i><i></i><i></i></div>${p.tags.length?`<span class="tag-count">✦ ${p.tags.length}</span>`:''}</article>`).join('')}</div><div class="page-controls"><button class="ghost" data-cmd="add-page">＋ 新增</button><button class="ghost" data-cmd="duplicate-page">复制</button><button class="ghost" data-cmd="delete-page">删除</button><button class="ghost" data-cmd="move-up">↑</button><button class="ghost" data-cmd="move-down">↓</button></div></aside>
<section class="panel"><div class="editor-toolbar"><select id="page-type" aria-label="页面类型">${Object.entries(kindNames).map(([v,l])=>`<option value="${v}" ${pg?.type===v?'selected':''}>${l}</option>`).join('')}</select><button class="ghost mini" data-cmd="import-script">导入稿件</button><button class="ghost mini job-action" data-cmd="rewrite">AI 润稿</button></div>${pg?`<div class="editor-canvas"><div class="slide-top"><span>本页口播</span><span>${String(P.pages.indexOf(pg)+1).padStart(2,'0')} / ${String(P.pages.length).padStart(2,'0')}</span></div><input id="page-title" class="slide-title" value="${esc(pg.title)}" aria-label="页面标题" placeholder="这一页的主题"><textarea id="page-text" class="script-text" aria-label="口播稿" placeholder="这一页，你想说什么？">${esc(pg.text)}</textarea><div class="slide-bottom"><span id="word-count">${pg.text.length} 字 · ≈ ${Math.ceil(pg.text.length/P.settings.speech_rate*60)} 秒</span></div></div><div class="notes"><div class="row"><label for="page-notes">录制提醒 · 不会进入字幕</label><div class="row"><label for="page-duration">计划秒数</label><input id="page-duration" type="number" min="0" value="${pg.duration||0}" style="width:75px;padding:4px 6px" title="0 表示按语速估算"></div></div><textarea id="page-notes" placeholder="例如：停顿一下，拿起产品，再开始讲解。">${esc(pg.notes)}</textarea>${pg.type!=='speech'?`<label>展示素材</label><select id="page-media" style="width:100%"><option value="">稍后添加素材</option>${P.assets.map(a=>`<option value="${a.id}" ${pg.media_id===a.id?'selected':''}>${esc(a.name)}</option>`).join('')}</select><button class="ghost mini" data-cmd="import-asset" style="margin-top:8px">＋ 导入展示图片 / 视频</button>`:''}</div>`:'<div class="empty">新增一页开始创作</div>'}<div class="editor-bottom"><div class="action-row"><button class="ghost mini" data-cmd="split-page">拆为两页</button><button class="ghost mini" data-cmd="merge-page">合并下一页</button></div><div class="action-row"><button class="ghost mini job-action" data-action="prompt_export">导出提词器</button></div></div></section>
<details class="panel annotations"><summary class="panel-head">加画面备注 · ${pg?.tags.length||0}</summary><div class="panel-body"><div><label>将标记添加到</label><select id="anchor" class="anchor-select"><option value="">整页内容</option>${(pg?.sentences||[]).map(s=>`<option value="${s.id}">${esc(s.text.slice(0,28))}</option>`).join('')}</select><div class="tag-grid">${Object.entries(tagKinds).map(([k,[icon,name]])=>`<button class="tag-chip" data-tag="${k}"><span>${icon}</span>${name}</button>`).join('')}</div><p class="hint">提前记下画面想法。粗剪后，这些标记会跟着对应的句子一起移动。</p></div><div>${(pg?.tags||[]).map(t=>`<div class="annotation" data-tag-id="${t.id}"><div class="row"><span>${esc(tagKinds[t.kind]?.[1]||t.kind)} ${t.orphaned?'· 待重新绑定':''}</span><button class="icon-btn mini" data-delete-tag="${t.id}" aria-label="删除标记">×</button></div><input data-tag-label="${t.id}" value="${esc(t.label)}" placeholder="这张素材想表达什么"><select data-tag-asset="${t.id}"><option value="">暂不绑定素材</option>${P.assets.map(a=>`<option value="${a.id}" ${t.asset_id===a.id?'selected':''}>${esc(a.name)}</option>`).join('')}</select>${t.kind==='flow'?`<input data-tag-steps="${t.id}" value="${esc((t.steps||[]).join(' → '))}" placeholder="电脑 → 路由器 → 设备">`:''}<div class="hint">${t.sentence_id?'绑定指定句子':'绑定整页'}</div></div>`).join('')||'<div class="empty">✦<br>给这一页加一个画面想法</div>'}</div></div></details></div>`}
function source(){return P?.media.find(m=>m.id===P.source_id)}
function chosenVideo(){if(previewMode==='source')return source()?.id;if(previewMode==='proxy')return P.proxy_id;if(previewMode==='rough')return P.rough?.media_id;if(previewMode==='final')return [...P.exports].reverse().find(e=>['final','timeline_final'].includes(e.kind))?.id;if(previewMode==='sample')return [...P.exports].reverse().find(e=>['sample','timeline_sample'].includes(e.kind))?.id;
return P.rough?.media_id||P.proxy_id||source()?.id}
function videoPanel(){const id=chosenVideo();return `<div class="viewer">${id?`<video id="player" controls preload="metadata" src="${fileURL(id)}"></video>`:`<div class="viewer-empty"><span class="record-icon">▷</span><h3>把你的录制放进来</h3><p class="hint">支持本地视频。原始素材会一直保留。</p><button class="key job-action" data-cmd="import-video">导入录制视频</button></div>`}</div><details class="workflow-tools video-options"><summary>播放选项</summary><div class="video-tools"><select id="preview-mode" aria-label="预览版本">${[['auto','最新版本'],['source','原始视频'],['proxy','兼容预览'],['rough','粗剪版本'],['sample','代表样片'],['final','完整成片']].map(([v,l])=>`<option value="${v}" ${previewMode===v?'selected':''}>${l}</option>`).join('')}</select><span class="spacer"></span><button class="ghost mini job-action" data-cmd="import-video">更换视频</button><button class="ghost mini job-action" data-action="proxy">生成兼容预览</button></div></details>`}
function stageTwo(){const src=source(),kept=P.edl.filter(c=>c.keep).reduce((s,c)=>s+c.end-c.start,0);const header=stageHeader([[fmt(src?.duration||0),'原片时长'],[fmt(kept),'保留时长'],[P.edl.filter(c=>!c.keep).length,'待删除片段']]);
if(!src?.video||!src?.path)return header;
return header+`
<details class="workflow-tools"><summary>手动调整</summary><div class="action-row"><button class="ghost job-action" data-cmd="transcribe">识别说话内容</button><button class="ghost job-action" data-action="analyze_cuts">查找长停顿和重复</button><button class="ghost" data-cmd="import-transcript">导入字幕文件</button><button class="ghost job-action" data-action="skip_rough">直接使用原视频</button></div></details>
<div class="review-grid"><section class="panel"><div class="panel-head">视频预览</div>${videoPanel()}<details class="workflow-tools"><summary>手动剪片段</summary><div class="timeline">${P.edl.map(c=>`<button class="${c.keep?'':'cut'}" style="flex:${c.end-c.start}" data-seek="${c.start}" title="${sec(c.start)}–${sec(c.end)} ${esc(c.reason)}"></button>`).join('')}</div><div class="video-tools"><button class="ghost mini" data-cmd="split-cut">在当前位置切一刀</button><button class="ghost mini" data-cmd="reset-cuts">恢复全部</button></div><div class="panel-body"><p class="hint">先用原片定位再拆分。开启“保护”后，自动分析会保留该区间。相似重录只提示，由你试听后选择。</p>${(P.repeat_suggestions||[]).map((r,i)=>`<div class="repeat-note">可能重复：${esc(r.text)}<br>${fmt(r.first[0])} 与 ${fmt(r.second[0])}<br><button class="ghost" data-repeat="${i}" data-choice="first">删除第一次</button><button class="ghost" data-repeat="${i}" data-choice="second">删除第二次</button></div>`).join('')}</div></details></section>
<details class="panel" ${P.edl.length>1?"open":""}><summary class="panel-head">逐段调整</summary><div class="cut-list">${P.edl.map(c=>`<div class="cut-row ${c.keep?'':'removed'}"><input type="checkbox" data-keep="${c.id}" ${c.keep?'checked':''} aria-label="保留这段"><div><b>${c.keep?"保留":"剪去"}</b> <strong data-seek="${c.start}">${sec(c.start)} → ${sec(c.end)}</strong><small>${esc(c.reason)}</small></div><button class="ghost ${c.protected?'protect':''}" data-protect="${c.id}">${c.protected?'◆ 已保护':'◇ 保护'}</button></div>`).join('')||'<div class="empty">导入视频后，这里会显示可恢复的剪辑清单。</div>'}</div><div class="panel-body"><p class="hint">${P.approvals.rough?'粗剪已确认，可以进入第三阶段。':'试听后再确认。改过片段后需生成新预览。'}</p></div></details></div>`}
function stageThree(){return stageHeader([[P.captions.length,'字幕片段'],[P.scenes.filter(s=>s.enabled).length,'已加画面'],[P.assets.length,'素材']])+`
<details class="workflow-tools"><summary>更多画面与字幕设置</summary><div class="action-row"><button class="ghost" data-cmd="import-asset">＋ 添加素材</button><button class="ghost job-action" data-action="plan">重新生成字幕与画面建议</button><button class="ghost job-action" data-action="inspect_frames">截取画面检查图</button>${P.layout_sheet_id?'<button class="ghost" data-cmd="view-layout">查看构图</button>':''}<button class="ghost" data-cmd="visual-settings">构图与字幕设置</button><button class="ghost" data-cmd="feedback">记录修改意见</button></div></details>
<div class="review-grid"><section class="panel"><div class="panel-head">视频预览</div>${videoPanel()}</section>
<section class="panel"><div class="tabs">${[['plan','画面备注'],['captions','字幕'],['assets','素材库'],['exports','下载']].map(([v,l])=>`<button data-tab="${v}" class="${tab===v?'active':''}">${l}</button>`).join('')}</div><div id="review-content" style="max-height:660px;overflow:auto">${reviewContent()}</div></section></div>`}
function reviewContent(){if(tab==='plan')return P.scenes.map(s=>`<article class="scene-row"><div class="row"><input type="checkbox" data-scene="${s.id}" data-field="enabled" ${s.enabled?'checked':''} aria-label="启用场景"><small>${esc(tagKinds[s.kind]?.[1]||s.kind)} ${s.orphaned?'· 未匹配，请定位':''}</small><span class="spacer"></span><input class="time-input" type="number" step=".01" data-scene="${s.id}" data-field="start" value="${sec(s.start)}" aria-label="开始时间"><span>→</span><input class="time-input" type="number" step=".01" data-scene="${s.id}" data-field="end" value="${sec(s.end)}" aria-label="结束时间"><button class="ghost mini" data-seek="${s.start}">定位</button></div><input type="text" data-scene="${s.id}" data-field="title" value="${esc(s.title)}" aria-label="画面标题"><select data-scene="${s.id}" data-field="asset_id" aria-label="绑定素材"><option value="">文字 / 流程图（无图片）</option>${P.assets.map(a=>`<option value="${a.id}" ${s.asset_id===a.id?'selected':''}>${esc(a.name)}</option>`).join('')}</select>${s.kind==='flow'?`<input type="text" data-scene="${s.id}" data-field="steps" value="${esc((s.steps||[]).join(' → '))}" placeholder="步骤一 → 步骤二 → 步骤三" style="margin-top:7px">`:''}<label class="checkline" style="margin-top:10px"><input type="checkbox" data-scene="${s.id}" data-field="fullscreen" ${s.fullscreen?'checked':''}>此段使用全屏演示（允许覆盖人物）</label><textarea data-scene="${s.id}" data-field="note" placeholder="制作备注 / 修改意见">${esc(s.note)}</textarea></article>`).join('')||'<div class="empty">确认粗剪后，生成字幕与精剪建议。<br>第一阶段的句子标记会带到这里。</div>';
if(tab==='captions')return `<div class="panel-body">${P.captions.length?'<label class="checkline"><input id="caption-only" type="checkbox" '+(P.settings.caption_only?'checked':'')+'> 只加口播字幕</label>':''}${noteButtons('')}<button class="ghost mini" data-cmd="add-caption">＋ 添加字幕</button></div>`+P.captions.map(c=>`
  <div class="caption-line"><button class="ghost mini" data-listen="${c.id}">听这句</button>
    <input data-caption="${c.id}" data-field="text" value="${esc(c.text)}" aria-label="字幕文字">
    ${P.settings.caption_only?'':`<button class="ghost mini" data-illustrate="${c.id}">这里加画面</button>`}
    ${noteButtons(c.id)}
    <details><summary>调整</summary><div class="action-row"><label>开始 <input type="number" step=".01" data-caption="${c.id}" data-field="start" value="${sec(c.start)}" aria-label="字幕开始"></label>
    <label>结束 <input type="number" step=".01" data-caption="${c.id}" data-field="end" value="${sec(c.end)}" aria-label="字幕结束"></label>
    <button class="ghost" data-delete-cap="${c.id}" aria-label="删除字幕">删除字幕</button></div></details></div>`).join('');
if(tab==='assets')return `<div class="panel-body"><button class="key small" data-cmd="import-asset">＋ 添加素材</button><p class="hint">透明 PNG 可交给 GIF 工厂做轻动效。原创生图、实物抠图可由当前 AI 制作后导入。</p></div><div class="assets-grid">${P.assets.map(a=>`<div class="asset-card">${['mp4','mov','webm'].includes(a.type)?`<video src="${assetURL(a.id)}" controls></video>`:['wav','mp3','m4a','flac','ogg'].includes(a.type)?`<audio src="${assetURL(a.id)}" controls style="width:100%"></audio>`:`<img src="${assetURL(a.id)}" alt="${esc(a.name)}">`}<p>${esc(a.name)}</p>${a.type==='png'?`<button class="ghost job-action" data-gif="${a.id}">✦ 做成动图</button>`:''}<div class="hint">${esc(a.source)}</div></div>`).join('')}</div>`;
return [...P.media].reverse().filter(m=>['final','sample','deliverable','rough'].includes(m.kind)).map(m=>`<div class="export-item"><div><span>${esc(m.name)}</span><small>${{final:'完整视频',sample:'预览片段',deliverable:'可下载文件',rough:'整理后的预览'}[m.kind]} · ${esc(m.created||'')}</small></div><a href="${fileURL(m.id,true)}" download>下载 ↗</a></div>`).join('')||'<div class="empty">样片、成片、字幕和工程包会出现在这里。</div>'}
function bindStage(){
  const captionOnly=$('#caption-only');
  if(captionOnly)captionOnly.onchange=async()=>{snapshot();P.settings.caption_only=captionOnly.checked;mark();try{await save();render()}catch(error){toast(error.message,true)}};
  const pg=currentPage();if(stage===1&&pg){for(const [id,key] of [['page-title','title'],['page-text','text'],['page-notes','notes'],['page-duration','duration'],['page-type','type'],['page-media','media_id']]){const el=$('#'+id);if(!el)continue;el.addEventListener('focus',snapshot,{once:true});el.addEventListener('input',()=>{pg[key]=key==='duration'?Number(el.value):el.value;mark();if(key==='text')$('#word-count').textContent=`${pg.text.length} 字 · ≈ ${Math.ceil(pg.text.length/P.settings.speech_rate*60)} 秒`});el.addEventListener('change',async()=>{await save();if(key==='type')render()})}
let drag='';$$('[data-page]').forEach(el=>{el.addEventListener('dragstart',()=>drag=el.dataset.page);el.addEventListener('dragover',e=>e.preventDefault());el.addEventListener('drop',async e=>{e.preventDefault();if(drag&&drag!==el.dataset.page){snapshot();const from=P.pages.findIndex(p=>p.id===drag),to=P.pages.findIndex(p=>p.id===el.dataset.page);P.pages.splice(to,0,P.pages.splice(from,1)[0]);mark();render()}});el.addEventListener('keydown',e=>{if(e.key==='Enter')el.click()})})}
$('#preview-mode')?.addEventListener('change',e=>{previewMode=e.target.value;render()})}
document.addEventListener('click',async e=>{const b=e.target.closest('button,[data-page],[data-seek]');if(!b)return;try{
if(b.dataset.stage){await save();goToWorkflowStage(Number(b.dataset.stage),Number(b.dataset.stage)===3?'captions':'plan');return}
if(b.dataset.page){await save();selected=b.dataset.page;render();return}
if(b.dataset.tab){await save();tab=b.dataset.tab;render();return}
if(b.dataset.listen){
  const caption=P.captions.find(c=>c.id===b.dataset.listen);
  previewMode='rough';render();
  const player=$('#player');
  if(player&&caption){
    const listen=()=>{player.currentTime=caption.start;player.ontimeupdate=()=>{if(player.currentTime>=caption.end){player.pause();player.ontimeupdate=null}};player.play().catch(()=>{})};
    if(player.readyState)listen();else player.addEventListener('loadedmetadata',listen,{once:true});
  }
  return;
}
if(b.dataset.illustrate){const caption=P.captions.find(c=>c.id===b.dataset.illustrate);if(caption){await addCaptionMaterial(caption);}return}
if(b.dataset.seek){const v=$('#player');if(v){v.currentTime=Number(b.dataset.seek);v.play().catch(()=>{})}return}
if(b.dataset.action){await act(b.dataset.action);return}
if(b.dataset.tag){snapshot();const pg=currentPage();pg.tags.push({id:makeId('tag'),kind:b.dataset.tag,review:'pending',label:tagKinds[b.dataset.tag][1],sentence_id:$('#anchor').value,asset_id:'',steps:b.dataset.tag==='flow'?['步骤一','步骤二','步骤三']:[]});mark();refreshAnnotations();return}
if(b.dataset.deleteTag){snapshot();currentPage().tags=currentPage().tags.filter(t=>t.id!==b.dataset.deleteTag);mark();refreshAnnotations();return}
if(b.dataset.protect){snapshot();const cut=P.edl.find(c=>c.id===b.dataset.protect);cut.protected=!cut.protected;if(cut.protected)cut.keep=true;refreshCutEdit();return}
if(b.dataset.repeat){snapshot();const r=P.repeat_suggestions[Number(b.dataset.repeat)];deleteRange(...r[b.dataset.choice]);refreshCutEdit();return}
if(b.dataset.deleteCap){snapshot();P.captions=P.captions.filter(c=>c.id!==b.dataset.deleteCap);mark();render();return}
if(b.dataset.gif){gifDialog(b.dataset.gif);return}
if(b.dataset.cmd)await command(b.dataset.cmd)
}catch(err){toast(err.message,true)}});
document.addEventListener('change',e=>{const t=e.target;if(t.dataset.keep){snapshot();P.edl.find(c=>c.id===t.dataset.keep).keep=t.checked;refreshCutEdit()}
if(t.dataset.tagLabel){currentPage().tags.find(x=>x.id===t.dataset.tagLabel).label=t.value;mark()}
if(t.dataset.tagAsset){currentPage().tags.find(x=>x.id===t.dataset.tagAsset).asset_id=t.value;mark()}
if(t.dataset.tagSteps){currentPage().tags.find(x=>x.id===t.dataset.tagSteps).steps=t.value.split(/→|->/).map(x=>x.trim()).filter(Boolean);mark()}
if(t.dataset.scene){const s=P.scenes.find(s=>s.id===t.dataset.scene),f=t.dataset.field;s[f]=['enabled','fullscreen'].includes(f)?t.checked:['start','end'].includes(f)?Number(t.value):f==='steps'?t.value.split(/→|->/).map(x=>x.trim()).filter(Boolean):t.value;mark()}
if(t.dataset.caption){const c=P.captions.find(c=>c.id===t.dataset.caption),f=t.dataset.field;c[f]=f==='text'?t.value:Number(t.value);mark()}});
function blankPage(){return {id:makeId('page'),type:'speech',title:'新的一页',text:'',notes:'',duration:0,tags:[],sentences:[],media_id:''}}
function splitAt(t){const i=P.edl.findIndex(c=>c.start<t&&t<c.end);if(i<0)return false;const c=P.edl[i];P.edl.splice(i,1,{...c,id:makeId('cut'),end:t},{...c,id:makeId('cut'),start:t});return true}
function refreshCutEdit(){P.rough=null;P.approvals={};P.qa={};mark();render()}
function deleteRange(a,b){splitAt(a);splitAt(b);P.edl.forEach(c=>{if(c.start>=a-.001&&c.end<=b+.001&&!c.protected){c.keep=false;c.reason='用户选择删除重复讲述'}})}
async function command(cmd){const pg=currentPage();switch(cmd){
case 'add-page':snapshot();{let p=blankPage();P.pages.splice(P.pages.indexOf(pg)+1,0,p);selected=p.id}mark();render();break;
case 'duplicate-page':snapshot();{let p=JSON.parse(JSON.stringify(pg));p.id=makeId('page');p.sentences=[];p.tags=p.tags.map(t=>({...t,id:makeId('tag'),sentence_id:''}));P.pages.splice(P.pages.indexOf(pg)+1,0,p);selected=p.id}mark();render();break;
case 'delete-page':if(P.pages.length===1)return toast('至少保留一页');snapshot();P.pages=P.pages.filter(p=>p.id!==pg.id);selected=P.pages[0].id;mark();render();break;
case 'move-up':case 'move-down':{const i=P.pages.indexOf(pg),j=i+(cmd==='move-up'?-1:1);if(j<0||j>=P.pages.length)return;snapshot();[P.pages[i],P.pages[j]]=[P.pages[j],P.pages[i]];mark();render();break}
case 'split-page':{const pos=$('#page-text').selectionStart;if(pos<=0||pos>=pg.text.length)return toast('先把光标放在需要拆页的位置');snapshot();const p=blankPage();p.text=pg.text.slice(pos);p.title=p.text.slice(0,16);pg.text=pg.text.slice(0,pos);P.pages.splice(P.pages.indexOf(pg)+1,0,p);mark();await save();render();break}
case 'merge-page':{const i=P.pages.indexOf(pg);if(i===P.pages.length-1)return;snapshot();const next=P.pages[i+1];pg.text+='\n'+next.text;pg.tags.push(...next.tags.map(t=>({...t,sentence_id:''})));pg.notes+='\n'+next.notes;P.pages.splice(i+1,1);mark();await save();render();break}
case 'import-script':scriptDialog();break;
case 'rewrite':rewriteDialog();break;
case 'import-video':mediaDialog();break;
case 'import-transcript':chooseFile('transcript','.json,.srt,.vtt');break;
case 'import-asset':chooseFile('asset','.png,.jpg,.jpeg,.webp,.gif,.svg,.mp4,.mov,.webm,.wav,.mp3,.m4a,.flac,.ogg');break;
case 'transcribe':transcribeDialog();break;
case 'prompt':await launchPrompt();break;
case 'reset-cuts':if(P.edl.some(c=>!c.keep)){snapshot();P.edl.forEach(c=>c.keep=true);refreshCutEdit()}break;
case 'split-cut':if(!['source','proxy'].includes(previewMode))return toast('先切换到原始视频或兼容预览，再定位剪点');snapshot();if(splitAt($('#player')?.currentTime||0))refreshCutEdit();break;
case 'finish':await openFinishReview();break;
case 'visual-settings':visualDialog();break;case 'view-layout':openDialog('构图关键帧 · 请核对人物区域',`<p class="hint">根据实际人物位置调整保护区；抽帧不能代替全片遮挡检查。</p><img src="${fileURL(P.layout_sheet_id)}" style="width:100%" alt="构图检查图">`);break;
case 'feedback':openDialog('记录这一轮修改',`<label>绑定场景</label><select id="feedback-scene"><option value="">整个项目</option>${P.scenes.map(s=>`<option value="${s.id}">${esc(s.title)}</option>`).join('')}</select><div class="field"><textarea id="feedback-text" placeholder="例如：连接流程的动画提前一点；保留第三段的停顿。"></textarea></div><button class="key" id="save-feedback">保存意见</button>`);$('#save-feedback').onclick=async()=>{P.feedback.push({id:makeId('feedback'),scene_id:$('#feedback-scene').value,text:$('#feedback-text').value,at:new Date().toISOString(),status:'pending'});mark();await save();closeDialog();toast('修改意见已保存在工程，可交给当前 AI 继续处理')};break;
case 'add-caption':snapshot();{let end=P.captions.at(-1)?.end||0;P.captions.push({id:makeId('cap'),start:end,end:end+1,text:'新字幕'})}mark();render();break;
}}
function scriptDialog(){openDialog('把内容变成口播页面',`<p class="hint">直接粘贴定稿，或导入文章。音频 / 视频请进入第二阶段转写后，再用转写结果排页。</p><div class="action-row"><button class="ghost" id="document-file">导入 TXT / DOCX / PDF / PPTX</button><button class="ghost" id="use-transcript">使用实际转写</button></div><div class="field"><textarea id="script-input" placeholder="粘贴文章或已处理好的口播稿…">${esc(P.source_text)}</textarea></div><label>处理方式</label><select id="script-mode"><option value="original">原稿直接使用 · 按语义自动排页</option><option value="light">规则口语化 · 清理格式和书面连接词</option></select><p class="hint">需要按主题深度改写或调整时长，可在排页后使用“AI 润稿”。重新排页会替换当前页面，可从历史版本恢复。</p><button class="key" id="make-script">生成口播工作台 →</button>`);$('#document-file').onclick=()=>chooseFile('document','.txt,.md,.docx,.pdf,.pptx');$('#use-transcript').onclick=()=>$('#script-input').value=P.transcript.map(s=>s.text).join('\n');$('#make-script').onclick=()=>act('script',{text:$('#script-input').value,mode:$('#script-mode').value}).catch(()=>{})}
function rewriteDialog(){const drafts=P.tasks.filter(t=>t.status==='draft_ready');openDialog('AI 润稿与待办',`<p class="hint">${doctorInfo.llm_configured?'已配置模型服务，可联网生成草稿。':'当前使用 Codex 协作模式：生成改稿任务后，在聊天中让 AI 处理待办，再回到这里采用草稿。'}</p>${drafts.map(t=>`<div class="task-draft">${esc(t.result)}</div><button class="key small" data-apply-task="${t.id}">采用这份草稿</button>`).join('')}<div class="field"><label>改写要求</label><textarea id="rewrite-instruction" style="min-height:100px">保留事实，改成自然易讲的中文口播。句子不要太长，保持我的表达习惯。</textarea></div>${doctorInfo.llm_configured?'<label class="checkline"><input id="allow-network" type="checkbox">允许将本次稿件发送给已配置的模型服务</label>':''}<button class="key" id="rewrite-go">${doctorInfo.llm_configured?'生成改稿草案':'创建 AI 改稿任务'}</button>`);$$('[data-apply-task]').forEach(b=>b.onclick=()=>act('apply_task',{task_id:b.dataset.applyTask}).catch(()=>{}));$('#rewrite-go').onclick=()=>act('rewrite',{instruction:$('#rewrite-instruction').value,allow_network:$('#allow-network')?.checked||false}).catch(()=>{})}
function mediaDialog(fresh=false){
  if(!doctorInfo.tools.ffmpeg||!doctorInfo.tools.ffprobe){
    openDialog('准备视频工具','<p>导入录音或视频需要 FFmpeg。工作台可使用本机软件管理器下载 FFmpeg 和视频组件。首次下载可能需要几分钟。已有稿件可以继续写和提词。</p><button class="key" id="prepare-video-tools">下载并准备视频工具</button> <button class="ghost" id="back-to-script">先写稿</button>');
    $('#prepare-video-tools').onclick=async()=>{if(fresh)await newBlank('新的口播视频',2);await act('prepare_video_tools').catch(()=>{})};
    $('#back-to-script').onclick=async()=>{closeDialog();if(fresh)await newBlank();else goToWorkflowStage(1)};
    return;
  }
  openDialog('导入录制',`<p>选择已经录好的视频。录音也可以用来整理口播稿。</p>
    <label for="recording-use">这份录制怎么用</label><select id="recording-use">
      <option value="raw">导入后决定怎么剪</option><option value="ready">已经剪好，去做字幕和画面</option><option value="captions">已经剪好，只加字幕</option></select>
    <button class="key" id="video-file">选择本机文件</button>
    <details class="workflow-tools"><summary>大文件可按路径导入</summary>
    <p class="hint">填写本机路径可直接引用文件，节省一份复制空间。</p>
    <input id="media-path" aria-label="本机文件路径" placeholder="粘贴本机文件的完整路径">
    <button class="ghost" id="media-path-go">按路径导入</button></details>`);
  $('#video-file').onclick=()=>chooseFile((fresh?'new-video':'video')+'|'+$('#recording-use').value,'video/*,audio/*');
  $('#media-path-go').onclick=async()=>{const path=$('#media-path').value.trim();if(!path)return;const use_as=$('#recording-use').value;if(fresh)await newBlank('新的口播视频',2);await act('import_media',{path,use_as}).catch(()=>{})};
}
function relinkDialog(){
  openDialog('重新选择原视频',`<p>请选择之前用于这个项目的视频，工作台会保留已有剪辑和字幕。</p>
    <button class="key" id="relink-file">选择本机视频</button>
    <details class="workflow-tools"><summary>使用文件路径</summary>
    <input id="relink-path" aria-label="原视频路径" placeholder="粘贴新的完整路径">
    <button class="ghost" id="relink-go">重新关联</button></details>`);
  $('#relink-file').onclick=()=>chooseFile('relink','video/*');
  $('#relink-go').onclick=()=>act('relink_source',{path:$('#relink-path').value.trim()}).catch(()=>{});
}
async function transcribeDialog(makeCaptions=false){
  if(!source()?.audio){
    toast('这份文件没有可识别的声音。',true);
    return;
  }
  if(!doctorInfo.modules?.whisper){
    openDialog('还没有安装语音识别',`
      <p>可以导入已有字幕，也可以关闭窗口，先预览视频。</p>
      <button class="key" id="prepare-transcription">下载语音识别组件</button> <button class="ghost" id="transcribe-caption-file">导入字幕文件</button>
      <details class="workflow-tools"><summary>如何启用自动识别</summary>
      <p>用工作台的 Python 运行 <code>python scripts/setup.py --speech</code>，然后刷新页面。</p></details>`);
    $('#prepare-transcription').onclick=()=>act('prepare_transcription').catch(()=>{});
    $('#transcribe-caption-file').onclick=()=>chooseFile(makeCaptions?'caption-file':'transcript','.srt,.vtt,.json');
    return;
  }
  const models=['tiny','base','small','medium','large','turbo'];
  const installed=doctorInfo.models||[];
  const preferred=installed.includes(P.settings.model)?P.settings.model:
    models.find(model=>installed.includes(model))||'base';
  const action = makeCaptions ? 'auto_captions' : 'transcribe';
  if (makeCaptions && installed.includes(preferred)) {
    return act(action, {model:preferred});
  }
  openDialog('识别说话内容',`<p>工作台会在这台电脑上把说话内容变成文字。</p>
    <details class="workflow-tools"><summary>识别选项</summary>
    <label for="model-choice">识别模型</label>
    <select id="model-choice">${models.map(model=>`<option value="${model}">${model}${installed.includes(model)?' · 已下载':''}</option>`).join('')}</select>
    <div class="field"><label for="terms">容易听错的名字或词语</label>
    <input id="terms" value="${esc(P.settings.terms)}" placeholder="例如品牌名、人名"></div></details>
    <label class="checkline" id="download-model"><input id="allow-download" type="checkbox">允许首次下载语音模型 <span id="model-size"></span></label>
    <button class="key" id="transcribe-go">开始识别</button>`);
  const model=$('#model-choice'), permission=$('#allow-download'), go=$('#transcribe-go');
  model.value=preferred;
  const refresh=()=>{
    const needsDownload=!installed.includes(model.value);
    $('#model-size').textContent='（约 '+({tiny:'72 MiB',base:'140 MiB',small:'460 MiB',medium:'1.4 GiB',large:'2.9 GiB',turbo:'1.5 GiB'}[model.value])+'）';
    $('#download-model').hidden=!needsDownload;
    go.disabled=needsDownload&&!permission.checked;
  };
  model.onchange=refresh;
  permission.onchange=refresh;
  refresh();
  go.onclick=async()=>{
    P.settings.model=model.value;
    P.settings.terms=$('#terms').value;
    mark();
    await act(action,{model:model.value,allow_download:permission.checked}).catch(()=>{});
  };
}
function gifDialog(aid){openDialog('GIF 工厂 · 制作轻动效',`<p class="hint">使用你的 PNG 素材制作循环轻动效，输出真实透明 GIF。新角色姿态可先由生图工具准备。</p><div class="field"><label>贴纸文字</label><input id="gif-text" value="重点来了"></div><label>动作</label><select id="gif-motion">${[['pulse','轻轻呼吸'],['offer','递出提示'],['jump','轻跳出现'],['sway','左右摇摆'],['nod','点头强调']].map(([v,l])=>`<option value="${v}">${l}</option>`).join('')}</select><div class="action-row" style="margin-top:18px"><button class="key" id="gif-go">制作动态贴纸</button></div>`);$('#gif-go').onclick=()=>act('gif',{asset_id:aid,text:$('#gif-text').value,motion:$('#gif-motion').value}).catch(()=>{})}
function visualDialog(){const s=P.settings;openDialog('构图与字幕设置',`<p class="hint">比例以源视频为准。先确定人物所在区域，再安排上方动画。保护区使用相对画面比例。</p><div class="form-grid">${[['caption_y','字幕底部位置（0–1）'],['caption_size','字号 / 画面高度'],['overlay_y','动画距顶部（0–1）'],['overlay_height','动画区域高度（0–1）']].map(([k,l])=>`<div class="field"><label>${l}</label><input type="number" step=".01" id="set-${k}" value="${s[k]}"></div>`).join('')}<div class="field"><label>人物保护区顶部（0–1）</label><input type="number" step=".01" id="protect-y" value="${s.protected_rect[1]}"></div><div class="field"><label>人物保护区高度（0–1）</label><input type="number" step=".01" id="protect-h" value="${s.protected_rect[3]}"></div><div class="field"><label>动画强调色</label><input type="color" id="set-accent" value="${s.accent}"></div><label class="checkline"><input id="set-sfx" type="checkbox" ${s.sfx?'checked':''}>动画入场配轻音效</label></div><div class="divider"></div><button class="key" id="visual-save">保存构图设置</button>`);$('#visual-save').onclick=async()=>{snapshot();['caption_y','caption_size','overlay_y','overlay_height'].forEach(k=>s[k]=Number($('#set-'+k).value));s.protected_rect[1]=Number($('#protect-y').value);s.protected_rect[3]=Number($('#protect-h').value);s.accent=$('#set-accent').value;s.sfx=$('#set-sfx').checked;mark();await save();closeDialog();render()}}
function chooseFile(purpose,accept){filePurpose=purpose;$('#file-picker').accept=accept;$('#file-picker').value='';$('#file-picker').click()}
$('#file-picker').onchange=async e=>{const file=e.target.files[0];if(!file)return;const [purpose,use_as]=filePurpose.split('|');try{if(purpose==='new-video')await newBlank(file.name.replace(/\.[^.]+$/,''),2);toast('正在导入文件…');const r=await fetch(`/api/upload?project=${P.id}&name=${encodeURIComponent(file.name)}`,{method:'POST',headers:{'X-Studio-Token':token},body:file});const data=await r.json();if(!r.ok)throw Error(data.error);const action={'new-video':'import_media',video:'import_media',document:'import_document',asset:'add_asset',relink:'relink_source',project:'import_project',transcript:'import_transcript','caption-file':'captions_from_file'}[purpose];await act(action,{path:data.path,use_as})}catch(e){toast(e.message,true)}};
async function launchPrompt(){await save();const win=window.open('','studio-prompter','width=1200,height=850');if(!win)return toast('请允许本站弹出提词窗口',true);const template=await (await fetch('/prompter.html')).text();const data=JSON.parse(JSON.stringify(P));data.start_page_id=selected;data.asset_urls=Object.fromEntries(P.assets.map(a=>[a.id,new URL(assetURL(a.id),location.href).href]));const blob=new Blob([template.replace('__PROJECT__',JSON.stringify(data).replaceAll('</','<\\/'))],{type:'text/html'});win.location=URL.createObjectURL(blob);promptWindow=win}
window.addEventListener('message',e=>{
  if(e.origin!==location.origin || e.source!==promptWindow || !P || homeMode || e.data?.projectId!==P.id)return;
  if(e.data.type==='studio-import-recording'){save().then(()=>{goToWorkflowStage(2);mediaDialog()}).catch(err=>toast(err.message,true));return}
  if(e.data.type==='studio-recording-log'){
    const entry=e.data.entry;
    if(entry.event==='page_enter' && P.pages.some(pg=>pg.id===entry.page_id)){
      selected=entry.page_id;
      localStorage.setItem('studio-page-'+P.id,selected);
      if(stage===1)render();
    }
    P.recording_log.push(entry);mark()
  }});
$('#projects').onchange=async e=>{try{await save();await load(e.target.value)}catch(err){toast(err.message,true)}};
$('#new-project').onclick=()=>{openDialog('新的口播项目','<label>项目名称</label><input id="new-title" placeholder="例如：我的下一期科技口播" value="新的口播项目"><div style="margin-top:20px"><button class="key" id="create-project">创建工作台 →</button></div>');$('#create-project').onclick=async()=>{try{await save();const p=await api('/api/new',{title:$('#new-title').value||'新的口播项目'});await refreshProjects();await load(p.id);stage=1;render();closeDialog()}catch(e){toast(e.message,true)}}};
$('#undo').onclick=async()=>{if(!undo.length)return toast('当前没有可撤销操作，历史版本可在设置中恢复');const prev=JSON.parse(undo.pop());prev.version=P.version;P=prev;mark();render()};
$('#package').onclick=()=>{
  const hasSource=Boolean(source()?.path);
  openDialog('导出工程包',`
    <p class="hint">工程包包含稿件、字幕、时间线和素材。默认生成轻量包，换电脑后可重新关联原片。</p>
    <label class="checkline"><input type="checkbox" id="package-source" ${hasSource?'':'disabled'}> 同时打包当前原片和已有粗剪文件</label>
    <p class="hint">${hasSource?'在另一台电脑继续剪辑时，可以勾选此项。':'导入或关联原片后可将原片一同打包。'}</p>
    <button class="key" id="package-go">生成工程 ZIP</button>`);
  $('#package-go').onclick=()=>act('package',{include_source:$('#package-source').checked}).catch(()=>{});
};
$('#close-dialog').onclick=closeDialog;
$('#settings').onclick=()=>{openDialog('项目与运行设置',`<div class="form-grid"><div class="field"><label>项目名称</label><input id="project-title" value="${esc(P.title)}"></div><div class="field"><label>语速估算（字 / 分钟）</label><input id="speech-rate" type="number" value="${P.settings.speech_rate}"></div><div class="field"><label>目标时长（秒）</label><input id="target-seconds" type="number" value="${P.settings.target_seconds}"></div><div class="field"><label>静音候选最短时长（秒）</label><input id="silence-seconds" type="number" step=".1" value="${P.settings.silence_seconds}"></div></div><div class="field"><button class="key" id="settings-save">保存设置</button></div><div class="divider"></div><p class="hint">FFmpeg ${doctorInfo.tools.ffmpeg?'✓':'缺失'} · 本地转写 ${doctorInfo.modules.whisper?'✓':'未安装'} · 浏览器渲染 ${doctorInfo.modules.playwright?'✓':'未安装'}<br>HCS ${doctorInfo.vendors['html-creator-studio']?'✓':'缺失'} · GIF 工厂 ${doctorInfo.vendors['gif-factory']?'✓':'缺失'} · 已下载模型：${doctorInfo.models.join('、')||'无'}</p><div class="action-row"><button class="ghost" id="import-project">导入工程 ZIP</button><button class="ghost" id="restore-draft">恢复浏览器草稿</button><button class="ghost" id="relink-source">重新定位原片</button></div><div class="field"><label>恢复历史版本（恢复后需重新确认）</label><select id="history-version">${[...P.history].reverse().map(h=>`<option value="${h.version}">V${h.version} · ${esc(h.label)} · ${esc(h.at)}</option>`).join('')}</select><button class="ghost" id="restore-version" style="margin-top:8px">恢复选中版本</button></div>`);$('#settings-save').onclick=async()=>{P.title=$('#project-title').value;P.settings.speech_rate=Math.max(60,Number($('#speech-rate').value));P.settings.target_seconds=Math.max(10,Number($('#target-seconds').value));P.settings.silence_seconds=Math.max(.2,Number($('#silence-seconds').value));mark();await save();await refreshProjects();closeDialog();render()};$('#import-project').onclick=()=>chooseFile('project','.zip');$('#relink-source').onclick=()=>{closeDialog();relinkDialog()};$('#restore-draft').onclick=async()=>{const d=localStorage.getItem('studio-draft-'+P.id);if(!d)return toast('没有待恢复的浏览器草稿');const old=JSON.parse(d);old.version=P.version;P=old;mark();await save();closeDialog();render()};$('#restore-version').onclick=()=>act('restore',{version:Number($('#history-version').value)}).catch(()=>{})};
window.addEventListener('beforeunload',e=>{if(dirty||saving){e.preventDefault();e.returnValue='尚有未保存修改'}});
async function init(){try{const b=await refreshProjects();if(!b.projects.length){const p=await api('/api/new',{title:'我的第一条口播'});await refreshProjects();await load(p.id)}else await load(b.projects.some(p=>p.id===localStorage.getItem('studio-current-project'))?localStorage.getItem('studio-current-project'):b.projects[0].id);setInterval(poll,1600)}catch(e){$('#main').innerHTML=`<div class="empty">工作台连接失败：${esc(e.message)}<br>请通过启动脚本打开本地服务。</div>`}}
