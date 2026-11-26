'use strict';

const recordingAccept = 'video/*,audio/*,.mkv,.mov,.mts,.m2ts,.srt,.vtt';
const openingPreview = new Set();

async function uploadRecordingFile(pid, file) {
  const response = await fetch('/api/upload?project='+encodeURIComponent(pid)+'&name='+encodeURIComponent(file.name),
    {method:'POST', headers:{'X-Studio-Token':token}, body:file});
  const data = await response.json();
  if (!response.ok) throw Error(data.error || '文件导入失败。');
  return data.path;
}

async function importRecordingFiles(files, fresh, use_as) {
  if (!files.length) return;
  const subtitles = files.filter(file=>/\.(srt|vtt)$/i.test(file.name));
  const recordings = files.filter(file=>!subtitles.includes(file));
  if (subtitles.length > 1 || recordings.length !== 1 ||
      !(/^(audio|video)\//.test(recordings[0].type) || /\.(mp4|mov|m4v|webm|mkv|avi|wmv|mts|m2ts|ts|mpe?g|3gp|wav|mp3|m4a|aac|ogg|flac|aiff?|opus)$/i.test(recordings[0].name))) {
    throw Error('请选择一个视频或录音，可以同时附上一份 SRT 或 VTT 字幕。');
  }
  const button = $('#video-file');
  if (button?.disabled) return;
  if (button) button.disabled = true;
  try {
    if (fresh) await newBlank(recordings[0].name.replace(/\.[^.]+$/,''),2);
    const pid = P.id;
    toast('正在导入录制…');
    const path = await uploadRecordingFile(pid, recordings[0]);
    const subtitle_path = subtitles.length ? await uploadRecordingFile(pid, subtitles[0]) : undefined;
    if (P?.id !== pid || homeMode) return;
    await importRecording({path, subtitle_path, use_as});
  } finally { if (button) button.disabled = false; }
}

function importRecording(args) {
  return (['raw','captions'].includes(args.use_as) || !doctorInfo.tools.ffmpeg || !doctorInfo.tools.ffprobe) ? startFirstPreview({entry:'import', ...args}) : act('import_media',args);
}

async function startFirstPreview(args) {
  const pid = P.id;
  const previousSource = P.source_id;
  const job = await act('first_preview', args, pid);
  localStorage.setItem('studio-preview-task-'+pid, JSON.stringify({id:job.id,entry:args.entry,previousSource}));
}

async function presentFirstPreview(pid, list) {
  const key = 'studio-preview-task-'+pid;
  const saved = localStorage.getItem(key);
  if (!saved) return;
  const pending = JSON.parse(saved);
  const job = list.find(item=>item.id===pending.id);
  const available = ()=>P?.id===pid && !homeMode && !dirty && !saving && !$('#dialog').open && !busy;
  if (!job || !available() || openingPreview.has(pid) || ['queued','running'].includes(job.status)) return;
  openingPreview.add(pid);
  try {
    const updated = await api('/api/project?id='+pid);
    if (!available() || localStorage.getItem(key)!==saved) return;
    P = updated;
    localStorage.removeItem(key);
    const result = job.result || {};
    if (result.source_id && result.source_id !== P.source_id) return;
    if (job.status!=='done' && pending.entry==='import' && P.source_id===pending.previousSource) {
      goToWorkflowStage(2);
      mediaDialog();
      const message=document.createElement('p');
      message.setAttribute('role','alert');
      message.textContent=job.error || job.message;
      $('#dialog-body').prepend(message);
      return;
    }
    if (result.next==='tools') {
      openDialog('准备本机视频工具','<p>首次处理视频需要下载 FFmpeg 和视频组件。装好后会自动继续处理刚才选择的文件。</p><button class="key" id="prepare-video-tools">同意下载并继续</button>');
      $('#prepare-video-tools').onclick=()=>startFirstPreview({entry:'import',...result.options,allow_tools:true}).catch(e=>toast(e.message,true));
      return;
    }
    if (result.next==='editor') { goToWorkflowStage(3,'captions'); return; }
    if (result.next==='cuts') { goToWorkflowStage(2); return; }
    if (result.next==='recording') { goToWorkflowStage(2); return; }
    if (job.status!=='done' && (!P.approvals.rough || !P.rough)) {
      goToWorkflowStage(2);
      toast(job.error || job.message,true);
      return;
    }
    goToWorkflowStage(3,'captions');
    if (result.next==='review') { await openFinishReview(undefined,null,true); return; }
    const setup = result.next==='setup';
    const title = setup ? '准备本机自动字幕' : result.next==='subtitles' ? '选择字幕来源' : '字幕预览还没完成';
    const message = setup ? [result.install ? '需要安装本地语音识别组件。' : '',
      result.download ? '首次下载 '+result.model+' 语音模型（约 140 MB）。' : '',
      '准备好后会自动识别并打开预览，视频留在本机。'].join('') : result.message || job.error || job.message;
    openDialog(title,`<p>${esc(message)}</p><div class="action-row">
      ${setup?'<button class="key" id="guided-retry">同意下载并继续</button>':!result.next?'<button class="key" id="guided-retry">继续准备预览</button>':''}
      <button class="${result.next==='subtitles'?'key':'ghost'}" id="guided-subtitles">导入已有字幕</button>
      <button class="ghost" id="guided-skip">先看画面</button></div>`);
    const retry = $('#guided-retry');
    if (retry) retry.onclick=()=>startFirstPreview({entry:'resume',source_id:P.source_id,allow_download:setup}).catch(e=>toast(e.message,true));
    $('#guided-subtitles').onclick=()=>chooseFile('guided-subtitles','.srt,.vtt,.json');
    $('#guided-skip').onclick=()=>openFinishReview();
  } finally { openingPreview.delete(pid); }
}
