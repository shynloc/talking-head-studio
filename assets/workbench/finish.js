'use strict';

let finishReview = null;

function previewableMaterials() {
  return P.timeline.clips.filter(clip => ['title','sticker','pip','music','sfx'].includes(clip.track) &&
    clip.enabled !== false && !clip.orphaned && !P.timeline.tracks[clip.track]?.muted &&
    (clip.asset_id || ['title','flow'].includes(clip.kind)));
}

function previewTimelineMaterial(clip) {
  return openFinishReview(Math.max(0,clip.start-.5), {
    name:clip.name, duration:Math.min(30,Math.max(2,clip.duration+1)),
  });
}

function openMaterialPreview() {
  const clips = previewableMaterials().sort((a,b) => a.start-b.start);
  openDialog('试看动画与音效', `<p>选一个素材，看看它放进口播视频里的效果。</p>
    <div class="finish-materials">${clips.map((clip,index) => `
      <button class="ghost" data-preview-material="${index}">${esc(clip.name)}
      <small>从 ${sec(clip.start)} 秒开始</small></button>`).join('')}</div>`);
  for (const button of document.querySelectorAll('[data-preview-material]')) {
    button.onclick = () => previewTimelineMaterial(clips[Number(button.dataset.previewMaterial)]);
  }
}

function finishPanel(review, html) {
  if (finishReview !== review || P?.id !== review.projectId || !$('#dialog').open) return false;
  const panel = $('#finish-panel');
  if (!panel) return false;
  panel.innerHTML = html;
  return true;
}

function finishURL(review, fileId, download = false) {
  return '/file/' + encodeURIComponent(review.projectId) + '/' + encodeURIComponent(fileId) + (download ? '?download=1' : '');
}

function finishError(review, error) {
  if (!finishPanel(review, `
    <p class="finish-error" role="alert">${esc(error.message)}</p>
    <div class="action-row">
      <button class="key" id="finish-check-again">重新检查</button>
      <button class="ghost" id="finish-back">返回编辑</button>
    </div>`)) return;
  $('#finish-check-again').onclick = () => refreshFinishReview(review).catch(e => finishError(review,e));
  $('#finish-back').onclick = closeDialog;
}

function finishPreparation(review, state) {
  const labels = {
    source: source()?.video ? '重新选择原视频' : '导入录制视频',
    rough: '去整理视频', align: '按这版视频继续',
    material: '补上缺少的素材', blocked: '查看时间线',
  };
  if (!finishPanel(review, `<h3>先准备好录制</h3><p>${esc(state.message)}</p>
    <div class="action-row"><button class="key" id="finish-prepare">${labels[state.state]}</button></div>`)) return;
  $('#finish-prepare').onclick = async () => {
    try {
      if (state.state === 'align') {
        $('#finish-prepare').disabled = true;
        await save();
        if (!finishPanel(review, '<p role="status">正在把字幕和素材对齐到这版视频…</p>')) return;
        const updated = await api('/api/v2/align', {id: P.id, version: P.version});
        if (P?.id !== review.projectId) return;
        P = updated;
        render();
        await refreshFinishReview(review);
        return;
      }
      closeDialog();
      if (state.state === 'source' || state.state === 'rough') {
        stage = 2;
        previewMode = 'auto';
        render();
        if (state.state === 'source') {
          if (source()?.video) relinkDialog();
          else await command('import-video');
        }
      } else if (state.state === 'material') {
        editClip(state.clip_id);
      } else if (state.state === 'blocked') {
        setTimelineExpanded(true);
        $('#timeline')?.scrollIntoView({block:'nearest'});
      }
    } catch (error) { finishError(review,error); }
  };
}

function finishSampleForm(review, state, replace = false) {
  const firstRecording = P.timeline.clips.find(c => c.track === 'main' && c.source_id === P.source_id);
  const start = review.start ?? state.sample?.start ?? firstRecording?.start ?? 0;
  const hint = review.material ? '看看这段素材和口播、字幕放在一起的效果。' : replace ? '选一段更能代表成片的内容。' : state.has_previous_sample
    ? '已有样片对应的是旧版时间线，或样片文件已移走。请生成一段新的样片。'
    : '先看一小段，检查字幕、画面和声音。满意后再导出完整视频。';
  if (!finishPanel(review, `<h3>${review.material ? '试看 · '+esc(review.material.name) : '先看一小段'}</h3><p>${hint}</p>
    <details class="workflow-tools" id="finish-range-options" ${replace && !review.material ? 'open' : ''}><summary>挑选要预览的片段</summary>
    <div class="finish-range">
      <label>起点（秒）<input id="finish-start" type="number" min="0" max="${Math.max(0,state.duration-.1).toFixed(2)}" step=".1" value="${Number(start).toFixed(2)}"></label>
      <label>长度（秒）<input id="finish-duration" type="number" min="1" max="30" step=".1" value="${review.material?.duration ?? 10}"></label>
    </div></details>
    <div class="action-row"><button class="key" id="finish-generate">生成预览</button>
    ${replace ? '<button class="ghost" id="finish-return-review">返回试看</button>' : ''}</div>`)) return;
  $('#finish-generate').onclick = () => {
    const startInput = $('#finish-start');
    const durationInput = $('#finish-duration');
    const maxStart = Number(startInput.max);
    const start = Math.min(maxStart,Math.max(0,startInput.valueAsNumber || 0));
    const duration = Math.min(30,Math.max(1,durationInput.valueAsNumber || 10));
    review.start = start;
    submitFinishJob(review,'timeline_sample',{start,duration});
  };
  if (replace) $('#finish-return-review').onclick = () => finishSampleReview(review,state);
}

function finishSampleReview(review, state) {
  const {sample, final, approved} = state;
  if (final && approved && review.showFinal) {
    finishPanel(review, `<h3>成片已导出</h3><p>完整视频也可在当前项目的「下载」中找到。</p>
      <video class="finish-video" controls playsinline preload="metadata" src="${finishURL(review,final.id)}"></video>
      <div class="action-row"><a class="key" href="${finishURL(review,final.id,true)}">下载完整成片</a></div>`);
    return;
  }
  const range = sample.start != null && sample.duration != null
    ? `<p class="hint">起点 ${sec(sample.start)} 秒 · 样片约 ${sec(sample.duration)} 秒</p>` : '';
  const confirmLabel = approved ? '导出完整视频' : '确认并导出完整视频';
  if (!finishPanel(review, `<h3>试看预览并确认</h3>
    <p>先播放预览，检查字幕、画面和声音。满意后选一种出片方式。</p>${range}
    <video class="finish-video" controls playsinline preload="metadata" src="${finishURL(review,sample.id)}" aria-label="当前时间线样片"></video>
    <div class="finish-choices" aria-label="出片方式">
      <div><button class="key" id="finish-confirm">${confirmLabel}</button><p>直接得到可发布的 MP4。</p></div>
      <div><button class="ghost" data-finish-delivery="editor_package">下载剪辑素材包</button><p>画面、字幕、动效和声音分开，适合在常用剪辑软件里继续做。</p></div>
      <div><button class="ghost" data-finish-delivery="chatcut_package">用 ChatCut 继续剪</button><p>准备素材，交给已连接 ChatCut 的 AI 助手组装。</p></div>
      <div><button class="ghost" data-finish-delivery="jianying_reviewed_export">生成剪映草稿</button><p>用剪映专业版打开，在时间线上继续编辑。打开方式随版本而异。</p></div>
    </div>
    <div class="action-row">
      <button class="ghost" id="finish-another">换一段预览</button>
      <button class="ghost" id="finish-edit">返回修改</button>
      ${final && approved ? `<a class="ghost" href="${finishURL(review,final.id,true)}">下载已导出的成片</a>` : ''}
    </div>`)) return;
  $('#finish-confirm').onclick = () => submitFinishJob(review,'confirm_timeline_final',{sample_id:sample.id,hash:state.hash});
  for (const button of document.querySelectorAll('[data-finish-delivery]')) {
    button.onclick = () => submitFinishJob(review,button.dataset.finishDelivery,{sample_id:sample.id,hash:state.hash});
  }
  $('#finish-another').onclick = () => {
    review.material = null;
    finishSampleForm(review,state,true);
  };
  $('#finish-edit').onclick = closeDialog;
}

const finishDeliveries = {
  editor_package: {busy:'正在整理剪辑素材', title:'剪辑素材包已备好',
    help:'解压后先打开「打开素材包.md」。字幕、动效和声音分开放，可按时间表摆放。'},
  chatcut_package: {busy:'正在准备 ChatCut 素材', title:'素材已备好，可以交给 ChatCut',
    help:'先打开 ChatCut 桌面版并连接 AI 助手。创建待办后，助手会按预览对应的时间线组装工程。'},
  jianying_reviewed_export: {busy:'正在生成剪映草稿', title:'剪映草稿已生成',
    help:'下载并解压。按包内「打开草稿.md」放入剪映的草稿位置，重新打开剪映即可查看。'},
};

function finishDelivery(review, job) {
  const option = finishDeliveries[job.action];
  const result = job.result;
  const handoff = job.action === 'chatcut_package' ?
    '<div class="action-row"><label>由谁接着做 <select id="finish-agent"><option value="codex">Codex</option><option value="workbuddy">WorkBuddy</option></select></label><button class="key" id="finish-handoff">存为剪辑待办</button></div>' : '';
  if (!finishPanel(review, `<h3>${option.title}</h3><p>${option.help}</p>${handoff}
    <div class="action-row"><a class="key" href="${finishURL(review,result.id,true)}">下载${job.action==='jianying_reviewed_export'?'草稿':'素材包'}</a>
    <button class="ghost" id="finish-return">返回试看</button></div>`)) return;
  $('#finish-return').onclick = () => refreshFinishReview(review).catch(e => finishError(review,e));
  const handoffButton = $('#finish-handoff');
  if (!handoffButton) return;
  handoffButton.onclick = async () => {
    const agent = $('#finish-agent').value;
    handoffButton.disabled = true;
    try {
      const task = await api('/api/agents/create', {
        project_id:review.projectId, agent, instruction:result.instruction,
        request_id:'chatcut-'+result.id+'-'+agent,
      });
      if (finishPanelActive(review)) await openAgentTask(task.id);
    } catch (error) { toast(error.message,true); }
    finally { handoffButton.disabled = false; }
  };
}

async function watchFinishJob(review, job) {
  const dialogTitle = job.action === 'timeline_sample' ? '正在生成样片'
    : ['timeline_final','confirm_timeline_final'].includes(job.action) ? '正在导出成片' : finishDeliveries[job.action]?.busy ?? '等待当前任务结束';
  if (!finishPanel(review, `<h3>${dialogTitle}</h3><progress id="finish-progress" max="1" value="0"></progress>
      <p id="finish-progress-text" role="status"></p><p class="hint">关闭窗口后任务会继续，可随时重新打开查看。</p>`)) return;
  for (;;) {
    if (!finishPanelActive(review)) return;
    $('#finish-progress').value = job.progress;
    $('#finish-progress-text').textContent = job.message;
    if (job.status === 'done') {
      if (finishDeliveries[job.action]) { finishDelivery(review,job); return; }
      review.showFinal = ['timeline_final','confirm_timeline_final'].includes(job.action);
      await refreshFinishReview(review, false);
      return;
    }
    if (job.status === 'error' || job.status === 'interrupted') throw Error(job.error || job.message);
    await new Promise(resolve => setTimeout(resolve,650));
    if (!finishPanelActive(review)) return;
    const jobs = await api('/api/jobs?id='+review.projectId);
    job = jobs.find(item => item.id === job.id);
    if (!job) throw Error('找不到任务记录，请重新检查样片。');
  }
}

function finishPanelActive(review) {
  return finishReview === review && P?.id === review.projectId && $('#dialog').open && !!$('#finish-panel');
}

async function refreshFinishReview(review, inspectJobs = true) {
  if (inspectJobs) {
    const jobs = await api('/api/jobs?id='+review.projectId);
    const active = jobs.find(job => job.status === 'running' || job.status === 'queued');
    if (active) return watchFinishJob(review, active);
  }
  const state = await api('/api/v2/finish?id='+review.projectId);
  if (state.state !== 'ready') finishPreparation(review,state);
  else if (!state.sample || review.selectRange) {
    review.selectRange = false;
    finishSampleForm(review,state,!!state.sample);
  } else finishSampleReview(review,state);
}

async function submitFinishJob(review, action, args) {
  if (!finishPanel(review, '<p role="status">正在提交任务…</p>')) return;
  try {
    await save();
    if (!finishPanelActive(review)) return;
    const job = await api('/api/action',{project_id:review.projectId,action,args});
    await watchFinishJob(review,job);
  } catch (error) { finishError(review,error); }
}

async function openFinishReview(start, material = null) {
  const review = {projectId:P.id,start,material,showFinal:false,selectRange:start != null};
  finishReview = review;
  openDialog('预览与导出','<div id="finish-panel" class="finish-panel"><p role="status">正在检查视频…</p></div>');
  try {
    await save();
    if (finishPanelActive(review)) await refreshFinishReview(review);
  } catch (error) { finishError(review,error); }
}
