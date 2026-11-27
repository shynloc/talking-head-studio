'use strict';

const openReviewKey = id => 'studio-open-review-' + id;
const reviewPositionKey = (id, kind) => 'studio-' + kind + '-position-' + id;

function readReviewRecord(key) {
  try { return JSON.parse(localStorage.getItem(key)); }
  catch { return null; }
}

function reviewPosition(project, kind) {
  const position = readReviewRecord(reviewPositionKey(project.id, kind));
  return position?.sourceId === project.source_id ? position : null;
}

function saveReviewPosition(project, kind, id, layout) {
  localStorage.setItem(reviewPositionKey(project.id, kind), JSON.stringify({
    sourceId: project.source_id, id, layout,
  }));
}

function activeProjectJob(jobs) {
  return jobs.find(job => job.status === 'queued' || job.status === 'running');
}

const finalActions = ['timeline_final', 'confirm_timeline_final'];
const finishActions = ['timeline_sample', 'caption_proof', ...finalActions];

function projectJobTitle(job) {
  if (finalActions.includes(job.action)) return '正在导出成片';
  if (job.action === 'first_preview') {
    return /字幕|转写|语音|识别/.test(job.message) ? '正在准备字幕' : '正在整理视频';
  }
  return {
    auto_captions:'正在自动加字幕', captions_from_file:'正在导入字幕', plan:'正在生成字幕',
    caption_proof:'正在生成改完的预览', timeline_sample:'正在生成预览',
    prepare_rough:'正在准备剪后试听', prepare_video_tools:'准备视频工具',
    prepare_transcription:'准备自动字幕', prepare_follow:'准备跟读',
    transcribe:'识别说话内容', analyze_cuts:'查找长停顿', render_rough:'生成整理后的预览',
    sample:'生成代表样片', final:'正在导出成片', gif:'GIF 工厂制作',
  }[job.action] || '工作台正在处理';
}

function savedFinishRequest(id) {
  const key = 'studio-review-' + id;
  return readReviewRecord(key) || {id:localStorage.getItem(key)};
}

async function projectResume(project, jobs, draft) {
  const id = project.id;
  const active = activeProjectJob(jobs);
  if (active) {
    return {action:finishActions.includes(active.action)?'finish':'project', label:'查看进度',
      status:`${projectJobTitle(active)} · ${Math.round(active.progress*100)}%`};
  }
  const draftStep = draft && {action:'draft', label:'查看润稿或分页建议', status:'稿件建议已返回', draftId:draft.id};
  const guided = readReviewRecord('studio-preview-task-'+id);
  const guidedJob = guided && jobs.find(job => job.id===guided.id);
  if (guidedJob) {
    if (guidedJob.result?.next==='cuts') return {action:'cuts', label:'查看停顿', status:'整理视频'};
    if (guidedJob.result?.next==='review') return {action:'project', label:'看字幕预览', status:'字幕与导出'};
    return {action:'project', label:'继续处理视频', status:'整理视频'};
  }
  const recording = project.media.find(item => item.id === project.source_id);
  if (!recording?.video) {
    if (draftStep) return draftStep;
    if (recording) return {action:'recording', label:'继续整理录音', status:'写稿与录制'};
    if (Number(localStorage.getItem('studio-stage-'+id)) === 2) {
      return {action:'import-recording', label:'导入录制视频', status:'整理视频'};
    }
    return hasManuscript(project) ? {action:'prompter', label:'继续提词', status:'写稿与录制'}
      : {action:'manuscript', label:'继续写稿', status:'写稿与录制'};
  }
  if (!project.approvals.rough || !project.rough || project.rough_current === false) {
    if (reviewableCuts(project.edl).length) return {action:'cuts', label:'查看停顿', status:'整理视频'};
    return {action:'recording', label:'继续整理视频', status:'整理视频'};
  }
  const state = await api('/api/v2/finish?id='+id);
  if (state.state === 'source') return {action:'relink', label:'重新选择原视频', status:'找不到原视频'};
  if (state.final && state.approved) {
    return {action:'final', label:'下载成片', status:'成片已导出', fileId:state.final.id};
  }
  if (!state.sample && project.exports.some(item => item.kind === 'timeline_final')) {
    return {action:'finish', label:'更新预览', status:'剪辑有更新'};
  }
  const finishJob = jobs.find(job => job.id === savedFinishRequest(id).id);
  if (finishJob && ['error','interrupted'].includes(finishJob.status)) {
    return {action:'finish', label:finalActions.includes(finishJob.action)?'继续导出':'继续预览', status:'上次处理需要重试'};
  }
  if (draftStep) return draftStep;
  if (state.caption_spans?.length) return {action:'captions', label:'继续校字幕', status:'字幕与导出'};
  if (!project.captions.length && !state.sample && recording.audio) {
    return {action:'editor', label:'继续加字幕', status:'字幕与导出'};
  }
  return {action:'finish', label:'看成片效果', status:'字幕与导出'};
}

function restoreOpenReview() {
  if (!P || homeMode || $('#dialog').open) return;
  const kind = localStorage.getItem(openReviewKey(P.id));
  if (kind === 'cuts' && stage===2 && !busy && !P.approvals.rough && reviewPosition(P,'cuts')) {
    openCutReview();
  } else if (kind==='finish' || (kind==='captions' && reviewPosition(P,'captions'))) {
    openFinishReview({captions:kind==='captions', restored:true});
  }
}
