'use strict';

const workSteps = ['写稿与录制', '整理视频', '字幕与导出'];

function recordingStep() {
  const recording = source();
  if (!recording?.path) return ['放入已经录好的视频', '有原始录制或已经剪好的视频，都可以从这里继续。',
    recording ? '重新选择原视频' : '导入录制视频', recording ? 'relink' : 'recording'];
  if (!recording.video) {
    return P.transcript.length
      ? ['把录音整理成稿件', '已识别录音里的文字，可以带到稿件编辑器里再修改。', '用这段录音写稿', 'speech-draft']
      : ['先识别录音里的文字', '识别完成后，可以把录音里的文字整理成口播稿。', '识别录音', 'transcribe'];
  }
  if (P.approvals.rough && P.rough) {
    return ['视频已准备好', '接下来可以加字幕、插入画面，或者直接预览导出。', '去字幕与导出', 'captions'];
  }
  if (P.rough) {
    return ['听一遍整理好的视频', '确认停顿剪得自然、该保留的话都在，再继续。', '确认这版视频', 'approve-rough',
      [['播放整理后的预览', 'play-rough']]];
  }
  if (P.edl.length > 1 || P.edl.some(cut => cut.reason !== '完整原片')) {
    const count = P.edl.filter(cut => !cut.keep).length;
    return ['看看要保留哪些片段', count
      ? `已标记 ${count} 处可能要剪掉的片段。要保留某一段，在下方把它勾上。`
      : '目前每段都保留。可以直接生成预览，也可以在下方手动调整。',
    '生成整理后的预览', 'render-rough', [['重新查找长停顿', 'find-pauses']]];
  }
  return ['这条视频还需要剪吗？', '如果还有长停顿，可以先查找，让工作台标出来给你检查。',
    '查找长停顿', 'find-pauses', [['已经剪好，直接用这版', 'keep-recording']]];
}

function exportStep() {
  const recording = source();
  if (!recording?.video || !recording.path) {
    return ['先准备一条视频', '导入录制视频后，可以加字幕并导出。',
      recording?.video ? '重新选择原视频' : '导入录制视频', recording?.video ? 'relink' : 'recording'];
  }
  if (!P.rough || !P.approvals.rough) {
    return ['先确认要使用哪版视频', '整理视频后确认预览。已有剪好的版本可以直接使用。', '去整理视频', 'organize'];
  }
  if (P.captions.length) {
    return ['检查字幕，预览后导出', '可以改错字或补充素材。满意后先看一小段，再导出完整视频。',
      '预览与导出', 'finish', [['检查字幕', 'edit-captions']]];
  }
  if (P.transcript.length) {
    return ['生成字幕', '工作台会按识别到的说话内容排字幕，并带入准备时留下的画面备注。',
      '生成字幕', 'make-captions', [['暂不加字幕，去预览', 'finish']]];
  }
  if (!recording.audio) {
    return ['这条视频没有声音', '可以导入已有字幕，也可以先看画面后导出。',
      '预览与导出', 'finish', [['导入字幕文件', 'caption-file']]];
  }
  return ['给视频加字幕', '先识别视频里说的话。已有字幕文件也可以直接导入。',
    '识别视频里的说话', 'transcribe', [['导入字幕文件', 'caption-file'], ['暂不加字幕，去预览', 'finish']]];
}

function workflowStep() {
  if (stage === 2) return recordingStep();
  if (stage === 3) return exportStep();
  const hasScript = P.pages.some(page => page.text?.trim() || page.media_id ||
    (page.type !== 'speech' && (page.notes?.trim() || page.duration > 0)));
  const next = source()?.video ? ['继续整理视频', 'organize'] : ['我已录好视频', 'recording'];
  return hasScript
    ? ['用提词器开始录制', '打开提词器后，用手机或相机录制。录好再回这里导入视频。',
      '打开提词器', 'prompt', [next]]
    : ['从第一段口播稿开始', '在下方写第一段，也可以导入文章或已经写好的口播稿。',
      '写第一段', 'write', [next]];
}

function refreshWorkflow() {
  const guide = $('#workflow-guide');
  if (!guide || !P) return;
  const [title, hint, label, action, alternatives = []] = workflowStep();
  if (stage === 3 && P.timeline.mode === 'actual' && previewableMaterials().length) {
    alternatives.push(['试看动画与音效', 'material-preview']);
  }
  const html = `<div class="workflow-copy">
    <span class="workflow-label">第 ${stage} 步 · ${workSteps[stage - 1]}</span>
    <h1>${esc(title)}</h1><p>${esc(hint)}</p></div>
    <div class="workflow-actions"><button class="key workflow-primary" data-workflow="${action}">${esc(label)}</button>
    ${alternatives.map(([text, id]) => `<button class="ghost" data-workflow="${id}">${esc(text)}</button>`).join('')}</div>`;
  if (guide._view !== html) {
    guide.innerHTML = html;
    guide._view = html;
  }
}

function goToWorkflowStage(next, panel = 'plan') {
  stage = next;
  tab = panel;
  previewMode = 'auto';
  render();
  document.querySelector('.stages .active')?.scrollIntoView({block:'nearest'});
}

document.addEventListener('click', async event => {
  const button = event.target.closest('button[data-workflow]');
  if (!button) return;
  const action = button.dataset.workflow;
  button.disabled = true;
  try {
    switch (action) {
      case 'write':
        $('#page-text')?.focus();
        break;
      case 'recording':
        await save();
        goToWorkflowStage(2);
        mediaDialog();
        break;
      case 'organize':
        await save();
        goToWorkflowStage(2);
        break;
      case 'captions':
        await save();
        goToWorkflowStage(3, 'captions');
        break;
      case 'prompt':
        await launchPrompt();
        break;
      case 'relink':
        relinkDialog();
        break;
      case 'transcribe':
        transcribeDialog();
        break;
      case 'speech-draft':
        await openManuscript('import', false, null, P.transcript.map(line => line.text).join('\n'));
        break;
      case 'find-pauses':
        await act('analyze_cuts');
        break;
      case 'keep-recording':
        await act('skip_rough');
        break;
      case 'render-rough':
        await act('render_rough');
        break;
      case 'play-rough': {
        previewMode = 'rough';
        render();
        const video = $('#player');
        video?.focus();
        await video?.play();
        break;
      }
      case 'approve-rough':
        await act('approve_rough');
        break;
      case 'caption-file':
        chooseFile('transcript', '.srt,.vtt,.json');
        break;
      case 'make-captions':
        await act('plan');
        break;
      case 'edit-captions':
        await save();
        tab = 'captions';
        render();
        document.querySelector('[data-tab="captions"]')?.focus();
        break;
      case 'finish':
        await openFinishReview();
        break;
      case 'material-preview':
        openMaterialPreview();
        break;
    }
  } catch (error) {
    toast(error.message, true);
  } finally {
    button.disabled = false;
  }
});
