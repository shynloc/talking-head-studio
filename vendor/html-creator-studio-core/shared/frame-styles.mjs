/**
 * HCS v1.4: pure, frame-addressable visual state.
 * Shared by the standalone HTML preview and the Remotion React Composition.
 * Every returned style is computed exclusively from frame + validated JSON inputs.
 * No clock, random input, DOM reads, state mutations or animation side effects.
 */
export const clamp = (value, low = 0, high = 1) => Math.max(low, Math.min(high, value));
export const lerp = (a, b, p) => a + (b - a) * p;
export const easeOutCubic = (p) => 1 - (1 - clamp(p)) ** 3;
export const smoothstep = (edge0, edge1, x) => {
  const p = clamp((x - edge0) / (edge1 - edge0));
  return p * p * (3 - 2 * p);
};
export const easingValue = (easing, p) => {
  const v = clamp(p);
  if (easing === 'linear') return v;
  if (easing === 'easeInOut') return v * v * (3 - 2 * v);
  if (easing === 'easeInCubic') return v ** 3;
  return easeOutCubic(v);
};
const n = (x) => Number(Number(x).toFixed(4));
const safeCssId = (value) => String(value).replace(/\\/g, '\\\\').replace(/"/g, '\\"').replace(/\n|\r|\f/g, ' ');
const properties = ['opacity', 'translateX', 'translateY', 'rotateDeg', 'scale', 'progress', 'strokeDashProgress'];

export function valueAt(frame, track) {
  const a = track.animation;
  if (!a) return {};
  const length = Math.max(1, a.endFrame - a.startFrame);
  const p = easingValue(a.easing, (frame - a.startFrame) / length);
  const values = {};
  for (const prop of properties) {
    const start = a.from?.[prop];
    const end = a.to?.[prop];
    if (typeof start === 'number' && typeof end === 'number') values[prop] = lerp(start, end, p);
    else if (typeof end === 'number' && frame >= a.startFrame) values[prop] = end;
    else if (typeof start === 'number') values[prop] = start;
  }
  return values;
}

export function sceneAtFrame(frame, timeline) {
  const scenes = timeline.scenes;
  const f = Math.max(0, Math.min(timeline.durationFrames - 1, Math.round(frame)));
  let chosen = scenes[0];
  for (const scene of scenes) if (f >= scene.startFrame) chosen = scene;
  return chosen;
}

function animationCSS(frame, track) {
  const state = valueAt(frame, track);
  const lines = [];
  if (typeof state.opacity === 'number') lines.push(`opacity:${n(state.opacity)}!important`);
  const x = state.translateX ?? 0, y = state.translateY ?? 0;
  const rot = state.rotateDeg ?? 0, scale = state.scale ?? 1;
  if (['translateX','translateY','rotateDeg','scale'].some(k => typeof state[k] === 'number')) {
    lines.push(`transform:translate3d(${n(x)}px,${n(y)}px,0) rotate(${n(rot)}deg) scale(${n(scale)})!important`);
  }
  if (typeof state.progress === 'number') lines.push(`left:${n(15 + state.progress * 73)}%!important`);
  if (typeof state.strokeDashProgress === 'number') lines.push(`--stroke-progress:${n(state.strokeDashProgress)}`);
  if (!lines.length) return '';
  return `[data-review-id="${safeCssId(track.element)}"]{${lines.join(';')}}`;
}

function extraCssHcs(frame, timeline) {
  // Demonstration-specific secondary choreography; all values are frame-derived.
  const fps = timeline.fps;
  const t = frame / fps;
  const pieces = [];
  const key = (p,a,b) => easeOutCubic((p-a)/(b-a));
  const animate = (scene, selector, p, delay, dur, opts={}) => {
    const k=key(p,delay,delay+dur), x=(opts.dx??0)*(1-k), y=(opts.dy??70)*(1-k);
    const scale=lerp(opts.scale??1,1,k),rotate=(opts.rotate??0)*(1-k);
    pieces.push(`.scene-${scene} ${selector}{opacity:${n(k)}!important;transform:translate3d(${n(x)}px,${n(y)}px,0) rotate(${n(rotate)}deg) scale(${n(scale)})!important}`);
  };
  let p = clamp(t,0,6);
  animate(0,'.intro-eyebrow',p,.15,.7,{dy:28});
  pieces.push(`.scene-0 .intro-underline{transform:scaleX(${n(key(p,.8,2.5))})!important}`);
  pieces.push(`.scene-0 .orb-dot{transform:translate(${n(15*Math.cos(p))}px,${n(19*Math.sin(p*.75))}px)!important}`);
  // Orbit is a continuous action authored in the original pilot. It is an intentional
  // exception from the metadata ease to retain the legacy motion art direction.
  pieces.push(`.scene-0 .intro-rings{opacity:${n(key(p,.25,1.3))}!important;transform:rotate(${n(-35+p*16)}deg) scale(${n(lerp(.85,1.03,key(p,.25,2.8)))})!important}`);
  p=clamp(t-6,0,6);
  animate(1,'.s1-title',p,.05,.85,{dy:55});
  animate(1,'.s1-bottom',p,2.15,.7,{dy:30});
  pieces.push(`.scene-1 #connect-path{stroke-dasharray:600;stroke-dashoffset:${n(600*(1-key(p,1.15,3)))}!important}`);
  for(let i=0;i<5;i++) pieces.push(`.scene-1 .bars>i:nth-child(${i+1}){transform-origin:bottom;transform:scaleY(${n(key(p,1.8+i*.2,3.5+i*.15))})!important}`);
  p=clamp(t-12,0,6);
  animate(2,'.direction-kicker',p,0,.6,{dy:25});
  for(let i=0;i<3;i++){
    const k=key(p,.7+i*.25,2.1+i*.25);
    pieces.push(`.scene-2 .art-card:nth-child(${i+1}){opacity:${n(k)}!important;transform:translateY(${n(95*(1-k))}px) rotateX(${n(-12*(1-k)+1.8*Math.sin(p*.45+i))}deg)!important}`);
  }
  p=clamp(t-18,0,6);
  animate(3,'.motion-tag',p,.08,.7,{dy:26});
  animate(3,'.motion-description',p,.7,.65,{dy:29});
  animate(3,'.motion-sublabel',p,1.7,.7,{dy:22});
  for(let i=0;i<4;i++)pieces.push(`.scene-3 .track:nth-of-type(${i+1}) .track-bar{transform-origin:left;transform:scaleX(${n(key(p,1.1+i*.22,2.9+i*.15))})!important}`);
  p=clamp(t-24,0,6);
  animate(4,'.edit-title',p,.05,.8,{dy:60});
  animate(4,'.edit-caption',p,1.7,.7,{dy:33});
  pieces.push(`.scene-4 .selected-element{transform:translateX(${n(key(p,3,4.65)*24)}px) scale(${n(1-.045*key(p,3,4.6))})!important}`);
  pieces.push(`.scene-4 .selected-element h3{font-size:${p>=3.75?'61':'67'}px!important}`);
  const slide=55-22*key(p,2.7,4.7);
  pieces.push(`.scene-4 #fontsize-progress{width:${n(slide)}%!important}.scene-4 #fontsize-knob{left:${n(slide-2)}%!important}`);
  pieces.push(`.scene-4 #speed-progress{width:${n(35+34*key(p,2.9,4.4))}%!important}.scene-4 #speed-knob{left:${n(33+34*key(p,2.9,4.4))}%!important}`);
  pieces.push(`.scene-4 .fake-cursor{transform:translate3d(${n(-455*key(p,1.5,3.2))}px,${n(-85*key(p,1.5,3.2))}px,0)!important}`);
  p=clamp(t-30,0,6);
  animate(5,'.outro-kicker',p,.08,.65,{dy:22});
  animate(5,'.outro-title',p,.24,.95,{dy:85,scale:.97});
  animate(5,'.outro-footer',p,2.5,1,{dy:40});
  return pieces.join('\n');
}

/** Return CSS rules for all scenes at the requested frame. Do not interpolate DOM directly. */
export function frameCSS(requestedFrame, timeline, storyboard, tokens, preset = 'generic') {
  const frame = clamp(Math.round(requestedFrame), 0, timeline.durationFrames-1);
  const overlap = Math.max(0, Math.round(timeline.fps * .62));
  const blocks = [];
  for (let i=0; i<timeline.scenes.length; i++) {
    const sc=timeline.scenes[i];
    const opacityIn=i===0?1:smoothstep(sc.startFrame-overlap,sc.startFrame+2,frame);
    const opacityOut=i===timeline.scenes.length-1?1:1-smoothstep(sc.endFrame-overlap,sc.endFrame+1,frame);
    const opacity=clamp(opacityIn*opacityOut);
    blocks.push(`.scene-${i}{opacity:${n(opacity)}!important;visibility:${opacity<.001?'hidden':'visible'}!important;z-index:${i}!important}`);
  }
  for (const track of timeline.tracks) blocks.push(animationCSS(frame,track));
  if (preset === 'hcs-brand-pilot') blocks.push(extraCssHcs(frame,timeline));
  const scene = sceneAtFrame(frame,timeline);
  const theme = scene.visualMode==='paper' ? '#1B2B44' : '#DDE9FF';
  blocks.push(`.stage .stage-overlay{color:${theme}!important}`);
  return blocks.filter(Boolean).join('\n');
}

/** Returns markup for one frame, updating counter and optional demonstration text. */
export function markupAtFrame(markup, requestedFrame, timeline, preset='generic') {
  const frame=clamp(Math.round(requestedFrame),0,timeline.durationFrames-1);
  const scene=sceneAtFrame(frame,timeline);
  const index=timeline.scenes.indexOf(scene)+1;
  const time=Math.floor(frame / timeline.fps);
  const timecode=String(Math.floor(time/60)).padStart(2,'0')+':'+String(time%60).padStart(2,'0');
  let html=markup.replace(/(<span id="stageCurrent">)[^<]*/,`$1${String(index).padStart(2,'0')}`)
                 .replace(/(<span id="stageTime">)[^<]*/,`$1${timecode}`);
  if(preset==='hcs-brand-pilot' && frame>=Math.round(27.75*timeline.fps))html=html.replace('BUILD <b>BEAUTIFUL.</b>','BUILD <b>REMARKABLE.</b>');
  return html;
}
