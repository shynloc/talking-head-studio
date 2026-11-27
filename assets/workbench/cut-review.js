'use strict';

function reviewableCuts(edl) {
  return edl.filter(row => !row.protected && (!row.keep || row.reason === '长停顿候选'));
}

// All preview times refer to the original video. The selected cut has the same
// neighbours in both versions, including when nearby cuts share their context.
function cutPreviewRanges(edl, point, original = false) {
  const before = point && edl.filter(row => row.keep && row.end <= point.start).at(-1);
  const after = point && edl.find(row => row.keep && row.start >= point.end);
  const left = before ? Math.max(before.start, before.end - 1.6) : point?.start ?? 0;
  const right = after ? Math.min(after.end, after.start + 1.6) : point?.end ?? edl.at(-1).end;
  if (original) return [[left, right]];
  const ranges = [];
  for (const row of edl) {
    const start = Math.max(left, row.start);
    const end = Math.min(right, row.end);
    if (!row.keep || start >= end) continue;
    const prior = ranges.at(-1);
    if (prior && Math.abs(prior[1] - start) < .001) prior[1] = end;
    else ranges.push([start, end]);
  }
  return ranges;
}

async function confirmCutSelection() {
  await startFirstPreview({entry:'use_cuts', source_id:P.source_id, edl:P.edl});
}

function openCutReview() {
  const points = reviewableCuts(P.edl).map(cut => cut.id);
  if (!points.length) return;
  $('#player')?.pause();
  openDialog('看看剪过的地方', `<section id="cut-review">
    <video id="cut-video" playsinline preload="auto" aria-label="停顿前后的画面与原声"></video>
    <div class="cut-heading"><strong id="cut-count"></strong><span id="cut-state" role="status"></span></div>
    <div class="action-row"><button type="button" class="key" id="cut-play">暂停</button>
      <button type="button" class="ghost" id="cut-compare">看这段原片</button>
      <button type="button" class="ghost" id="cut-restore">恢复这处停顿</button></div>
    <div class="action-row cut-nav"><button class="ghost" id="cut-prev">上一处</button>
      <button class="ghost" id="cut-next">下一处</button><button class="ghost" id="cut-full">从头看整版</button></div>
    <p hidden id="cut-error" role="alert"></p>
    <button hidden class="ghost" id="cut-proxy">生成兼容预览</button>
    <button class="key" id="cut-confirm">用这版，继续加字幕</button></section>`);
  const dialog = $('#dialog');
  const video = $('#cut-video');
  const pid = P.id, sourceId = P.source_id;
  const savedIndex = points.indexOf(reviewPosition(P,'cuts')?.id);
  let index = Math.max(0,savedIndex), ranges = [], range = 0, mode = 'sequence';
  let frame = 0, pass = 0, finished = false;
  const current = () => P.edl.find(row => row.id === points[index]);
  const active = () => dialog.open && video.isConnected && P?.id === pid && P.source_id === sourceId;
  localStorage.setItem(openReviewKey(pid),'cuts');
  saveReviewPosition(P,'cuts',points[index]);
  function labels() {
    if (!active()) return;
    const row = current();
    $('#cut-count').textContent = mode === 'full' ? '完整剪后视频' : `第 ${index+1} 处，共 ${points.length} 处`;
    $('#cut-state').textContent = mode === 'original' ? '原片对照' : mode === 'full' ? '' :
      row.keep ? '已恢复原停顿' : `已缩短 ${(row.end-row.start).toFixed(1)} 秒`;
    $('#cut-play').textContent = finished ? (mode==='sequence'?'再连看一遍':'重播') : video.paused ? '播放' : '暂停';
    $('#cut-compare').textContent = mode === 'original' ? '看剪后效果' : '看这段原片';
    $('#cut-restore').textContent = row.keep ? '撤销恢复' : '恢复这处停顿';
    $('#cut-prev').disabled = index===0;
    $('#cut-next').disabled = index===points.length-1;
    $('#cut-full').textContent = mode === 'full' ? '回到剪过的地方' : '从头看整版';
    for (const id of ['#cut-prev','#cut-next','#cut-compare','#cut-restore']) $(id).hidden = mode === 'full';
  }
  function play() {
    if (!active()) return;
    const request = pass;
    video.play().catch(err => {
      if (request !== pass || !active() || err.name === 'AbortError') return;
      if (err.name !== 'NotAllowedError' && !video.error) toast('预览暂时无法播放，请重试。', true);
      labels();
    });
  }
  function start(nextMode = 'sequence', autoplay = true) {
    if (!active() || !current()) return;
    pass++;
    mode = nextMode;
    ranges = cutPreviewRanges(P.edl, mode==='full'?null:current(), mode==='original');
    range = 0;
    finished = false;
    saveReviewPosition(P,'cuts',points[index]);
    if (ranges.length) {
      video.currentTime = ranges[0][0];
      if (autoplay) play();
    } else {
      video.pause();
      finished = true;
    }
    labels();
  }
  function advance() {
    if (finished || !ranges.length) return;
    if (range+1 < ranges.length) {
      video.currentTime = ranges[++range][0];
      if (video.ended || video.paused) play();
    } else if (mode === 'sequence' && index+1 < points.length) {
      index++;
      start();
    } else {
      video.pause();
      finished = true;
      labels();
    }
  }
  function tick() {
    if (!active()) { video.pause(); return; }
    if (!video.paused && !video.seeking && ranges.length && video.currentTime >= ranges[range][1]) advance();
    frame = requestAnimationFrame(tick);
  }
  video.onended = advance;
  video.onplay = video.onpause = labels;
  video.onerror = () => {
    if (!active()) return;
    $('#cut-error').hidden = false;
    $('#cut-error').textContent = '浏览器读取这段视频失败。可以为原片生成兼容预览，再回来连看。';
    $('#cut-proxy').hidden = false;
  };
  $('#cut-proxy').onclick = () => act('proxy').catch(e=>toast(e.message,true));
  $('#cut-prev').onclick = () => { if (index>0) { index--; start(); } };
  $('#cut-next').onclick = () => { if (index<points.length-1) { index++; start(); } };
  $('#cut-play').onclick = () => {
    if (finished) { if (mode==='sequence') index=0; start(mode); }
    else if (!ranges.length) start(mode);
    else if (video.paused) play();
    else video.pause();
  };
  $('#cut-compare').onclick = () => start(mode==='original'?'sequence':'original');
  $('#cut-full').onclick = () => start(mode==='full'?'sequence':'full');
  $('#cut-restore').onclick = () => {
    const row = current();
    if (!row || row.protected) return;
    snapshot();
    row.keep = !row.keep;
    mark();
    refreshWorkflow();
    start('single');
    save().catch(err => toast(err.message,true));
  };
  $('#cut-confirm').onclick = async event => {
    const button = event.currentTarget;
    button.disabled = true;
    video.pause();
    try { await confirmCutSelection(); }
    catch (err) { toast(err.message,true); button.disabled = false; }
  };
  const pauseWhenHidden = () => { if (document.hidden) video.pause(); };
  document.addEventListener('visibilitychange', pauseWhenHidden);
  dialog.addEventListener('close', () => {
    document.removeEventListener('visibilitychange', pauseWhenHidden);
    cancelAnimationFrame(frame);
    video.pause();
    if (P?.id === pid && stage===2 && !homeMode) render();
  }, {once:true});
  video.src = fileURL(P.proxy_id || sourceId);
  video.onloadedmetadata = () => { if (!ranges.length && active()) start('sequence',savedIndex<0); };
  labels();
  frame = requestAnimationFrame(tick);
}
