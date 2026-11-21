'use strict';

let finishReview = null;

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
    source: '导入录制视频', rough: '去整理录制', align: '校准录制',
    material: '打开主轨片段', blocked: '返回时间线',
  };
  if (!finishPanel(review, `<h3>先准备好录制</h3><p>${esc(state.message)}</p>
    <div class="action-row"><button class="key" id="finish-prepare">${labels[state.state]}</button></div>`)) return;
  $('#finish-prepare').onclick = async () => {
    try {
      if (state.state === 'align') {
        $('#finish-prepare').disabled = true;
        await save();
        if (!finishPanel(review, '<p role="status">正在校准录制…</p>')) return;
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
        if (state.state === 'source') await command('import-video');
      } else if (state.state === 'material') {
        editClip(state.clip_id);
      }
    } catch (error) { finishError(review,error); }
  };
}

function finishSampleForm(review, state, replace = false) {
  const firstRecording = P.timeline.clips.find(c => c.track === 'main' && c.source_id === P.source_id);
  const start = review.start ?? state.sample?.start ?? firstRecording?.start ?? 0;
  const hint = replace ? '选一段更能代表成片的内容。' : state.has_previous_sample
    ? '已有样片对应的是旧版时间线，或样片文件已移走。请生成一段新的样片。'
    : '样片是当前时间线的一小段预览，用来检查画面、字幕和声音。生成后可在这里直接播放。';
  if (!finishPanel(review, `<h3>1 · 生成样片</h3><p>${hint}</p>
    <div class="finish-range">
      <label>起点（秒）<input id="finish-start" type="number" min="0" max="${Math.max(0,state.duration-.1).toFixed(2)}" step=".1" value="${Number(start).toFixed(2)}"></label>
      <label>长度（秒）<input id="finish-duration" type="number" min="1" max="30" step="1" value="10"></label>
    </div>
    <div class="action-row"><button class="key" id="finish-generate">生成样片</button>
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
    finishPanel(review, `<h3>成片已导出</h3><p>完整视频已保存到当前项目的「输出」。</p>
      <video class="finish-video" controls playsinline preload="metadata" src="${finishURL(review,final.id)}"></video>
      <div class="action-row"><a class="key" href="${finishURL(review,final.id,true)}">下载完整成片</a></div>`);
    return;
  }
  const range = sample.start != null && sample.duration != null
    ? `<p class="hint">起点 ${sec(sample.start)} 秒 · 样片约 ${sec(sample.duration)} 秒</p>` : '';
  const confirmLabel = approved ? '导出完整成片' : '确认样片并导出成片';
  if (!finishPanel(review, `<h3>2 · 试看并确认</h3>
    <p>请播放下面这段样片，检查字幕、画面和声音。满意后点击确认，工作台会导出完整视频。</p>${range}
    <video class="finish-video" controls playsinline preload="metadata" src="${finishURL(review,sample.id)}" aria-label="当前时间线样片"></video>
    <div class="action-row">
      <button class="key" id="finish-confirm">${confirmLabel}</button>
      <button class="ghost" id="finish-another">换一段样片</button>
      <button class="ghost" id="finish-edit">返回修改</button>
      ${final && approved ? `<a class="ghost" href="${finishURL(review,final.id,true)}">下载已导出的成片</a>` : ''}
    </div>`)) return;
  $('#finish-confirm').onclick = () => submitFinishJob(review,'confirm_timeline_final',{sample_id:sample.id,hash:state.hash});
  $('#finish-another').onclick = () => finishSampleForm(review,state,true);
  $('#finish-edit').onclick = closeDialog;
}

async function watchFinishJob(review, job) {
  const dialogTitle = job.action === 'timeline_sample' ? '正在生成样片'
    : ['timeline_final','confirm_timeline_final'].includes(job.action) ? '正在导出成片' : '等待当前任务结束';
  if (!finishPanel(review, `<h3>${dialogTitle}</h3><progress id="finish-progress" max="1" value="0"></progress>
      <p id="finish-progress-text" role="status"></p><p class="hint">关闭窗口后任务会继续，可随时重新打开查看。</p>`)) return;
  for (;;) {
    if (!finishPanelActive(review)) return;
    $('#finish-progress').value = job.progress;
    $('#finish-progress-text').textContent = job.message;
    if (job.status === 'done') {
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

async function openFinishReview(start) {
  const review = {projectId:P.id,start,showFinal:false,selectRange:start != null};
  finishReview = review;
  openDialog('成片检查与导出','<div id="finish-panel" class="finish-panel"><p role="status">正在检查当前时间线…</p></div>');
  try {
    await save();
    if (finishPanelActive(review)) await refreshFinishReview(review);
  } catch (error) { finishError(review,error); }
}
