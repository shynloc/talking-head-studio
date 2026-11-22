'use strict';

let fitWholePage = true;
let fitFrame = 0;

function promptOverflow() {
  const viewport = $('viewport');
  const hasMore = viewport.scrollHeight - viewport.clientHeight - viewport.scrollTop > 2;
  $('read-more').hidden = !hasMore;
  $('next-btn').textContent=hasMore?'下一屏 ↓':index<P.pages.length-1?'下一页 →':'录好了，导入视频';
}

function fitPromptPage() {
  const viewport = $('viewport');
  const script = $('text');
  const requested = Number($('font').value) || 52;
  script.style.fontSize = requested+'px';
  if (fitWholePage && script.childElementCount && viewport.scrollHeight > viewport.clientHeight + 1) {
    // Use the largest readable font that fits the actual content area.
    let low = Math.min(requested, 32);
    let high = requested;
    let good = low;
    while (low <= high) {
      const size = Math.floor((low+high)/2);
      script.style.fontSize = size+'px';
      if (viewport.scrollHeight <= viewport.clientHeight+1) {
        good = size;
        low = size+1;
      } else high = size-1;
    }
    script.style.fontSize = good+'px';
  }
  promptOverflow();
}

function queuePromptFit() {
  cancelAnimationFrame(fitFrame);
  fitFrame = requestAnimationFrame(fitPromptPage);
}

function advancePromptScreen() {
  const viewport = $('viewport');
  const bottom = viewport.getBoundingClientRect().bottom;
  const chars = Array.from($('text').children);
  const visible = chars.filter(el=>el.getBoundingClientRect().bottom<=bottom);
  const lastBreak=visible.filter(el=>/[。！？；]/.test(el.textContent)).at(-1);
  const nextChar=lastBreak?.nextElementSibling;
  const delta=nextChar ? nextChar.getBoundingClientRect().top-viewport.getBoundingClientRect().top : 0;
  viewport.scrollTop+=delta>viewport.clientHeight*.4?delta:Math.max(36,Math.floor(viewport.clientHeight*.8));
  promptOverflow();
}

function initPromptFit() {
  const viewport = $('viewport');
  const fit = $('fit-page');
  fit.onclick = () => {
    fitWholePage = !fitWholePage;
    fit.classList.toggle('on',fitWholePage);
    fit.setAttribute('aria-pressed',String(fitWholePage));
    queuePromptFit();
  };
  $('font').oninput = queuePromptFit;

  viewport.addEventListener('scroll',promptOverflow,{passive:true});
  const observer = new ResizeObserver(queuePromptFit);
  observer.observe(viewport);
  $('visual').addEventListener('load',queuePromptFit);
  $('demo-video').addEventListener('loadedmetadata',queuePromptFit);
  document.fonts?.ready.then(queuePromptFit);
  queuePromptFit();
}
