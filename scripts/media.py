"""Local speech, non-destructive editing, frame rendering and GIF Factory."""
from __future__ import annotations
import copy, difflib, html, importlib.util, json, math, os, re, shutil, subprocess, sys, time, wave
from fractions import Fraction
from pathlib import Path
from core import *
import fonts
import materials

HCS_DIR = ROOT / 'vendor/html-creator-studio-core'

def hcs_file(relative_path):
    override = ROOT / 'vendor/html-creator-studio' / relative_path
    return override if override.is_file() else HCS_DIR / relative_path

def run(cmd, log=None, cwd=None):
    if Path(str(cmd[0])).stem.lower() == 'ffmpeg' and '-nostdin' not in cmd:
        cmd = [cmd[0], '-nostdin', *cmd[1:]]
    proc = subprocess.run([str(x) for x in cmd], cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if log: Path(log).write_bytes(proc.stdout + proc.stderr)
    if proc.returncode:
        raise RuntimeError(proc.stderr.decode('utf-8', errors='replace')[-3500:] or '外部工具执行失败')
    return proc.stdout.decode('utf-8', errors='replace')

def probe(path):
    raw = json.loads(run(['ffprobe','-v','error','-show_streams','-show_format','-of','json',path]))
    video = next((s for s in raw['streams'] if s['codec_type'] == 'video'), None)
    audio = next((s for s in raw['streams'] if s['codec_type'] == 'audio'), None)
    duration = float((video or audio or {}).get('duration') or raw['format'].get('duration', 0))
    result = {'alpha_capable': False, 'duration': duration, 'audio': bool(audio), 'video': bool(video), 'width': 0, 'height': 0, 'fps': 30.}
    if video:
        w, h = video['width'], video['height']
        rotations = [s.get('rotation', 0) for s in video.get('side_data_list', [])]
        if any(abs(int(r)) % 180 == 90 for r in rotations): w, h = h, w
        try: fps = float(Fraction(video.get('avg_frame_rate', '30/1')))
        except (ValueError, ZeroDivisionError): fps = 30
        fmt=video.get('pix_fmt','')
        result['alpha_capable']=fmt.startswith(('yuva','gbrap','rgba','bgra','argb','abgr','ya')) or video.get('tags',{}).get('alpha_mode')=='1'
        result.update(width=w, height=h, fps=fps if fps > 0 else 30, codec=video['codec_name'])
    if duration <= 0: raise ValueError('文件没有可用的媒体时长')
    return result

def import_media(store, pid, path, source_video=True, subtitle_path=None):
    path = Path(path).resolve()
    if not path.is_file(): raise ValueError('文件不存在')
    from subtitle_input import read_segments
    meta = probe(path)
    transcript = read_segments(subtitle_path, meta['duration']) if subtitle_path else []
    folder = store.folder(pid); folder.mkdir(exist_ok=True)
    with LOCK:
        p = store.load(pid); item = {'id': uid('file'), 'name': path.name, 'path': str(path), 'kind': 'source', **meta}
        p['media'].append(item)
        if source_video:
            if p.get('source_id') and p.get('timeline',{}).get('mode')=='actual':
                p['timeline']['needs_alignment']=True
            p.update(source_id=item['id'], transcript=transcript, edl=[], proxy_id=None, previous_rough=None, rough=None, captions=[], scenes=[], approvals={})
            p['edl'] = [{'id': uid('cut'), 'start': 0, 'end': meta['duration'], 'keep': True, 'reason': '完整原片', 'protected': False}]
        store.save(p, label='导入原始媒体')
    return item

def extract_document(path):
    path = Path(path); suffix = path.suffix.lower()
    if suffix in ('.txt','.md','.srt','.vtt'):
        return path.read_text(encoding='utf-8-sig', errors='replace')
    extractor = hcs_file('scripts/extract_resume.py')
    if extractor.is_file() and (suffix == '.docx' or (suffix == '.pdf' and shutil.which('pdftotext'))):
        spec = importlib.util.spec_from_file_location('hcs_extract', extractor)
        mod = importlib.util.module_from_spec(spec); spec.loader.exec_module(mod)
        data = mod.extract(path)
        return '\n'.join(r.get('text','') for r in data.get('evidence', []))
    if suffix == '.pdf':
        from pypdf import PdfReader
        text = '\n'.join(pg.extract_text() or '' for pg in PdfReader(path).pages)
        if not text.strip(): raise ValueError('此 PDF 未提取到文字，需要先执行 OCR')
        return text
    if suffix == '.docx':
        from xml.etree import ElementTree
        from zipfile import ZipFile

        with ZipFile(path) as doc:
            root = ElementTree.fromstring(doc.read('word/document.xml'))
        namespaces = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}
        paragraphs = []
        for paragraph in root.findall('.//w:p', namespaces):
            text = ''.join(node.text or '' for node in paragraph.findall('.//w:t', namespaces))
            if text.strip():
                paragraphs.append(text)
        return '\n'.join(paragraphs)
    if suffix == '.pptx':
        from pptx import Presentation
        return '\n'.join(s.text for slide in Presentation(path).slides for s in slide.shapes if s.has_text_frame)
    raise ValueError('支持 TXT、Markdown、DOCX、PDF、PPTX；音视频请使用转写按钮')

def silence_ranges(output, duration):
    raw, start = [], None
    for m in re.finditer(r'silence_(start|end): ([0-9.]+)', output):
        kind, sec = m.group(1), float(m.group(2))
        if kind == 'start': start = sec
        elif start is not None:
            raw.append((start,sec)); start = None
    if start is not None: raw.append((start,duration))
    return raw


def recognition_ranges(item, work):
    log = work / 'recognition-pauses.log'
    run(['ffmpeg','-hide_banner','-i',item['path'],'-vn','-af','silencedetect=noise=-40dB:d=1.25','-f','null','-'],log)
    duration = item['duration']
    spans = []
    start = 0
    for a,b in silence_ranges(log.read_text(encoding='utf8',errors='replace'),duration):
        if a-start > .12:
            spans.extend([start,min(duration,a+.12)])
        start = max(0,b-.12)
    if duration-start > .13:
        spans.extend([start,duration])
    return spans


def transcribe(store, pid, report, model_name='medium', allow_download=False, media_id=None):
    p = store.load(pid); item = next((m for m in p['media'] if m['id'] == (media_id or p['source_id'])), None)
    if not item or not item.get('audio'): raise ValueError('输入没有可转写的声音')
    if model_name not in ('tiny','base','small','medium','large','turbo'): raise ValueError('不支持的语音模型')
    cache = Path(os.environ.get('XDG_CACHE_HOME', str(Path.home()/'.cache'))) / 'whisper'
    if not (cache/f'{model_name}.pt').exists() and not allow_download:
        raise ValueError(f'本机尚无 {model_name} 模型，请在设置中允许下载，或选择已经安装的模型')
    report(.08, '加载本地语音模型，首次加载可能需要一些时间')
    import whisper, torch
    device = 'cuda' if torch.cuda.is_available() else 'cpu'
    model = whisper.load_model(model_name, device=device)
    report(.2, f'正在转写（{model_name} / {device}），保留实际口播内容')
    script_terms=sorted(set(re.findall(r'[A-Za-z][A-Za-z0-9+./-]{1,30}', '\n'.join(pg['text'] for pg in p['pages']))))
    ranges = recognition_ranges(item, store.folder(pid))
    result = model.transcribe(item['path'], language='zh', word_timestamps=True, fp16=device=='cuda',
        initial_prompt='中文口播，保留实际说出的内容。术语：' + p['settings'].get('terms','')+'、'.join(script_terms), verbose=False, clip_timestamps=ranges) if ranges else {'segments':[], 'text':''}
    segments = [{'id': uid('seg'), 'start': s['start'], 'end': s['end'], 'text': s['text'], 'words': s.get('words',[])} for s in result['segments']]
    del model
    if device == 'cuda': torch.cuda.empty_cache()
    write_json(store.folder(pid)/'transcript-raw.json', result)
    with LOCK:
        current = store.load(pid)
        if current['source_id'] != p['source_id']: raise Conflict('转写期间原片已变更，结果已保存但未覆盖新工程')
        current['transcript'] = segments
        for output in ('final', 'timeline'):
            current['approvals'].pop(output, None)
        store.save(current, label='本地转写完成')
    return {'segments': len(segments), 'text': result['text'], 'engine': model_name, 'device': device}

def rough_candidates(p, work, report):
    src = source(p)
    if not src.get('video'): raise ValueError('粗剪需要视频文件')
    cfg = p['settings']; duration = src['duration']; fps = src['fps']
    report(.15, '分析静音、停顿与重复讲述')
    log = work/'silence.log'
    if src['audio']:
        run(['ffmpeg','-hide_banner','-i',src['path'],'-af',f"silencedetect=noise={float(cfg['silence_db'])}dB:d={float(cfg['silence_seconds'])}",'-f','null','-'], log)
        output = log.read_text(encoding='utf-8',errors='replace')
    else: output = ''
    raw = silence_ranges(output, duration)
    deleted=[]; guards=[r for r in p['edl'] if r.get('protected')]
    for a,b in raw:
        trim = float(cfg['keep_pause'])/2
        a = 0 if a < .1 else a+trim; b = duration if b > duration-.1 else b-trim
        if b-a < .15: continue
        a=round(a*fps)/fps;b=min(duration,round(b*fps)/fps)
        if any(a<g['end'] and b>g['start'] for g in guards): continue
        deleted.append((a,b,'长停顿候选'))
    bounds = sorted({0.,duration,*(x for a,b,_ in deleted for x in (a,b)),*(x for g in guards for x in (g['start'],g['end']))})
    edl=[]
    for a,b in zip(bounds,bounds[1:]):
        if b-a < .0001: continue
        reason = next((r for x,y,r in deleted if x <= (a+b)/2 < y), None)
        protected = any(g['start'] <= (a+b)/2 < g['end'] for g in guards)
        edl.append({'id':uid('cut'),'start':a,'end':b,'keep':not reason or protected,'reason':reason or ('保护片段' if protected else '有效内容／自然停顿'),'protected':protected})
    # Silence alone cannot justify discarding the entire recording.
    if not any(row['keep'] for row in edl):
        for row in edl:
            row.update(keep=True, reason='保留整段无声画面')
    suggestions=[]
    segments=p.get('transcript',[])
    for i,a in enumerate(segments):
        for b in segments[i+1:i+5]:
            if b['start']-a['end']>35: break
            aa,bb=normalized(a['text']),normalized(b['text'])
            score=difflib.SequenceMatcher(None,aa,bb).ratio()
            if min(len(aa),len(bb))>=6 and score>.78:
                suggestions.append({'first':[a['start'],a['end']],'second':[b['start'],b['end']], 'text':a['text'],'score':round(score,3),'note':'相似讲述，请试听后选择；尚未自动删除'})
    return {'edl':edl,'repeat_suggestions':suggestions,'rough':None,'approvals':{}}

def make_proxy(store,pid,report):
    p=store.load(pid);src=source(p)
    if not src.get('video'): raise ValueError('请导入视频')
    work=store.folder(pid)/'renders'/uid('proxy');work.mkdir(parents=True)
    out=work/'preview.mp4';report(.1,'生成浏览器兼容预览')
    run(['ffmpeg','-v','error','-i',src['path'],'-vf','scale=w=720:h=720:force_original_aspect_ratio=decrease:force_divisible_by=2',
        '-c:v','libx264','-preset','fast','-crf','25','-c:a','aac','-b:a','128k','-movflags','+faststart','-y',out],work/'proxy.log')
    item=store.register(pid,out,'proxy');store.patch(pid,{'proxy_id':item['id']},'预览准备完成');return item

def render_rough(store,pid,report,skip=False):
    p=store.load(pid);src=source(p)
    if not src.get('video'): raise ValueError('请先导入视频')
    if skip:
        edl=[{'id':uid('cut'),'start':0,'end':src['duration'],'keep':True,'protected':False,'reason':'用户提交的粗剪版'}]
        rough={'media_id':src['id'],'path':src['path'],'duration':src['duration'],'mapping':time_map(edl),'edl_hash':edl_digest(edl)}
        store.patch(pid,{'edl':edl,'rough':rough,'approvals':{'rough':{'at':now(),'kind':'already_cut'}}},'确认已粗剪输入')
        return rough
    validate_edl(p['edl'],src['duration']);mapping=time_map(p['edl'])
    if all(row['keep'] for row in p['edl']):
        with LOCK:
            current = store.load(pid)
            if current['source_id'] != src['id'] or current['edl'] != p['edl']:
                raise Conflict('视频或停顿选择已更改，请重新查看。')
            rough = {'media_id':src['id'], 'path':src['path'], 'duration':src['duration'],
                     'mapping':mapping, 'edl_hash':edl_digest(p['edl'])}
            store.patch(pid, {'rough':rough, 'approvals':{}}, '复用完整原片')
            return rough
    work=store.folder(pid)/'renders'/uid('rough');work.mkdir(parents=True)
    out=work/'rough.mp4';filters=[];labels=[]
    for i,m in enumerate(mapping):
        a,b=m['source_start'],m['source_end']
        filters.append(f'[0:v]trim=start={a}:end={b},setpts=PTS-STARTPTS[v{i}]')
        if src['audio']: filters.append(f'[0:a]atrim=start={a}:end={b},asetpts=PTS-STARTPTS[a{i}]')
        else: filters.append(f'anullsrc=r=48000:cl=stereo,atrim=duration={b-a}[a{i}]')
        labels.append(f'[v{i}][a{i}]')
    filters.append(''.join(labels)+f'concat=n={len(mapping)}:v=1:a=1[v][a]')
    script=work/'filter.txt';script.write_text(';'.join(filters),encoding='utf-8')
    report(.2,f'合成 {len(mapping)} 个保留片段')
    run(['ffmpeg','-v','warning','-i',src['path'],'-/filter_complex',script,'-map','[v]','-map','[a]',
        '-c:v','libx264','-preset','fast','-crf','20','-pix_fmt','yuv420p','-r',src['fps'],'-c:a','aac','-b:a','192k','-movflags','+faststart','-y',out],work/'render.log')
    meta=probe(out)
    with LOCK:
        current = store.load(pid)
        if current['edl'] != p['edl'] or current['source_id'] != p['source_id']:
            raise Conflict('视频或剪辑清单已更改，请重新生成剪辑预览。')
        item=store.register(pid,out,'rough');rough={'media_id':item['id'],'path':str(out),'duration':meta['duration'],'mapping':mapping,'edl_hash':edl_digest(p['edl'])}
        store.patch(pid,{'rough':rough,'approvals':{},'qa':{'rough_decode':True}},'粗剪预览已输出')
    return rough

def ass_time(t):
    cs=round(max(0,t)*100);return f'{cs//360000}:{cs//6000%60:02}:{cs//100%60:02}.{cs%100:02}'

def srt_time(t):
    ms=round(max(0,t)*1000);return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'

def subtitles(p,work,w,h):
    font=max(16,round(h*float(p['settings']['caption_size'])))
    bottom=round(h*(1-float(p['settings']['caption_y'])))
    header=f'''[Script Info]\nScriptType: v4.00+\nPlayResX: {w}\nPlayResY: {h}\nWrapStyle: 0\n[V4+ Styles]\nFormat: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding\nStyle: Default,{fonts.FONT_FAMILY},{font},&H00FFFFFF,&H00FFFFFF,&H00101A20,&H70000000,0,0,0,0,100,100,0,0,1,{max(1,font*.06):.1f},1,2,{round(w*.05)},{round(w*.05)},{bottom},1\n[Events]\nFormat: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n'''
    lines=[];srt=[]
    for i,c in enumerate(p['captions']):
        text=c['text'].replace('\\','＼').replace('{','｛').replace('}','｝').replace('\n','\\N')
        lines.append(f"Dialogue: 0,{ass_time(c['start'])},{ass_time(c['end'])},Default,,0,0,0,,{text}")
        srt.append(f"{i+1}\n{srt_time(c['start'])} --> {srt_time(c['end'])}\n{c['text']}\n")
    (work/'captions.ass').write_text(header+'\n'.join(lines),encoding='utf-8-sig')
    (work/'captions.srt').write_text('\n'.join(srt),encoding='utf-8-sig')

def asset_paths(p):
    return {a['id']:a for a in p['assets']}

def create_overlay(p,work,w,h,fps):
    """Build a frame-addressable overlay, using HCS when available."""
    from PIL import Image,ImageSequence
    fonts.stage_font(work)
    cfg=p['settings'];region=max(40,round(h*cfg['overlay_height']));full=p.get('v2_overlay') or any(s.get('fullscreen') and s.get('enabled') for s in p['scenes'])
    oh=h if full else region;assets=asset_paths(p);scenes=copy.deepcopy(p['scenes'])
    for s in scenes:
        aid=s.get('asset_id')
        if not aid: continue
        if aid not in assets: raise ValueError('场景引用了不存在的素材')
        path=Path(assets[aid]['path']);suffix=path.suffix.lower()
        if suffix=='.gif':
            folder=work/aid;folder.mkdir(exist_ok=True);frames=[];cursor=0
            with Image.open(path) as im:
                for i,fr in enumerate(ImageSequence.Iterator(im)):
                    name=f'{i:04}.png';fr.convert('RGBA').save(folder/name)
                    dur=fr.info.get('duration',80)/1000;frames.append({'src':f'{aid}/{name}','start':cursor,'end':cursor+dur});cursor+=dur
            s['frames']=frames;s['loop_duration']=cursor
        elif suffix in ('.png','.jpg','.jpeg','.webp','.svg'):
            target=work/(aid+suffix);shutil.copy2(path,target);s['src']=target.name
        elif suffix in ('.mp4','.mov','.webm'):
            folder=work/(aid+'-'+s['id']);folder.mkdir()
            vw=w if s.get('fullscreen') else max(80,round(w*.3));vh=h if s.get('fullscreen') else region
            run(['ffmpeg','-v','error','-ss',s.get('source_in',0),'-i',path,'-t',s['end']-s['start'],'-vf',f'scale=w={vw}:h={vh}:force_original_aspect_ratio=decrease:force_divisible_by=2,fps={fps}',
                '-an','-y',folder/'%05d.png'],work/(s['id']+'-decode.log'))
            frames=[{'src':f'{folder.name}/{f.name}','start':i/fps,'end':(i+1)/fps} for i,f in enumerate(sorted(folder.glob('*.png')))]
            if not frames:raise ValueError('演示视频没有可解码画面')
            s['frames']=frames;s['loop_duration']=frames[-1]['end'];s['hold_last']=True
        else: raise ValueError('不支持的叠加素材格式')
    hcs_engine = hcs_file('shared/frame-styles.mjs')
    if hcs_engine.is_file():
        shared = re.sub(r'\bexport\s+', '', hcs_engine.read_text(encoding='utf-8'))
        engine_name = 'HCS frame-styles'
    else:
        shared = (ROOT / 'assets/workbench/overlay-easing.js').read_text(encoding='utf-8')
        engine_name = 'Built-in overlay easing'
    data=json.dumps(scenes,ensure_ascii=False).replace('</','<\\/')
    template=(ROOT/'assets/workbench'/('overlay-v2.html' if p.get('v2_overlay') else 'overlay.html')).read_text(encoding='utf-8')
    content=template.replace('__WIDTH__',str(w)).replace('__HEIGHT__',str(oh)).replace('__FPS__',str(fps))
    layout={'stageH':oh,'regionH':region,'regionY':round(h*cfg['overlay_y']) if full else 0}
    content=content.replace('__SCENES__',data).replace('__HCS_ENGINE__',shared).replace('__ACCENT__',cfg['accent']).replace('__LAYOUT__',json.dumps(layout))
    (work/'overlay.html').write_text(content,encoding='utf-8')
    write_json(work/'timeline.json',{'fps':fps,'width':w,'height':h,'scenes':scenes,'engine':engine_name + ' + Playwright/FFmpeg'})
    return oh

def render_overlay(work,w,oh,fps,start,duration,report):
    from playwright.sync_api import sync_playwright
    count=math.ceil(duration*fps);out=work/'overlay.mov'
    with sync_playwright() as browser_api:
        browser=browser_api.chromium.launch(headless=True,args=['--allow-file-access-from-files'])
        tab=browser.new_page(viewport={'width':w,'height':oh},device_scale_factor=1)
        tab.goto((work/'overlay.html').as_uri());tab.evaluate('window.ready')
        fonts.load_browser_font(tab)
        with (work/'overlay.log').open('wb') as log:
            proc=subprocess.Popen(['ffmpeg','-v','error','-f','image2pipe','-framerate',str(fps),'-vcodec','png','-i','pipe:0','-an','-c:v','qtrle','-pix_fmt','argb','-y',str(out)],stdin=subprocess.PIPE,stderr=log)
            blank=None
            try:
                for i in range(count):
                    active=tab.evaluate('f=>renderAtFrame(f)',round(start*fps)+i)
                    if not active and blank is not None: png=blank
                    else:
                        png=tab.screenshot(omit_background=True)
                        if not active: blank=png
                    proc.stdin.write(png)
                    if i%90==0: report(.15+.55*i/max(1,count),f'渲染透明动画 {i}/{count} 帧')
                proc.stdin.close()
                if proc.wait(): raise RuntimeError((work/'overlay.log').read_text(errors='replace'))
            except Exception:
                proc.kill();proc.wait();raise
            finally: browser.close()
    return out

def synth_sfx(p,work,duration,start):
    import numpy as np
    rate=48000;samples=np.zeros(round(duration*rate),dtype=np.float32)
    times=sorted({s['start'] for s in p['scenes'] if s.get('enabled') and start<=s['start']<start+duration})
    if p['settings'].get('sfx'):
        for sec in times:
            t=np.arange(int(.13*rate))/rate;x=np.sin(2*np.pi*(680*t+160*t*t))*(1-np.exp(-t*500))*np.exp(-t*32)*.025
            i=round((sec-start)*rate);end=min(len(samples),i+len(x));samples[i:end]+=x[:end-i]
    with wave.open(str(work/'sfx.wav'),'wb') as fh:
        fh.setnchannels(1);fh.setsampwidth(2);fh.setframerate(rate);fh.writeframes((np.clip(samples,-1,1)*32767).astype('<i2').tobytes())

def render_final(store,pid,report,sample=True,start=0,duration=10):
    p=store.load(pid);validate_plan(p);signature=plan_hash(p)
    if not sample and p['approvals'].get('final',{}).get('hash')!=signature:
        raise ValueError('请先确认当前版本的字幕、方案和样片；修改后需要重新确认受影响版本')
    rough=p['rough'];meta=probe(rough['path']);w,h=meta['width'],meta['height'];fps=meta['fps']
    start=max(0,min(float(start),rough['duration']-.1)) if sample else 0
    duration=min(max(.1,float(duration)),rough['duration']-start) if sample else rough['duration']
    work=store.folder(pid)/'renders'/uid('sample' if sample else 'final');work.mkdir(parents=True)
    write_json(work/'project-snapshot.json',p);subtitles(p,work,w,h)
    oh=create_overlay(p,work,w,h,fps);overlay=render_overlay(work,w,oh,fps,start,duration,report)
    synth_sfx(p,work,duration,start);report(.78,'合成口播、字幕、透明动画和音效')
    overlay_y=0 if any(s.get('fullscreen') and s.get('enabled') for s in p['scenes']) else round(h*p['settings']['overlay_y'])
    video_filter=f'[0:v][1:v]overlay=0:{overlay_y}:format=auto,setpts=PTS+{start}/TB,{fonts.ASS_FILTER},setpts=PTS-STARTPTS,format=yuv420p[v]'
    audio_filter=('[0:a]aresample=48000[voice]' if meta['audio'] else f'anullsrc=r=48000:cl=stereo,atrim=duration={duration}[voice]')
    audio_filter+=';[voice][2:a]amix=inputs=2:duration=first:normalize=0,alimiter=limit=0.89:level=false:latency=true,apad[a]'
    out=work/('sample.mp4' if sample else 'final.mp4')
    run(['ffmpeg','-v','warning','-ss',start,'-i',rough['path'],'-i',overlay,'-i',work/'sfx.wav','-filter_complex',video_filter+';'+audio_filter,
        '-map','[v]','-map','[a]','-t',duration,'-r',fps,'-c:v','libx264','-preset','fast','-crf','19','-c:a','aac','-b:a','192k','-movflags','+faststart','-y',out],work/'encode.log',cwd=work)
    report(.93,'验证完整解码与画面尺寸')
    run(['ffmpeg','-v','error','-i',out,'-f','null','-'],work/'decode.log')
    final_meta=probe(out)
    if (final_meta['width'],final_meta['height'])!=(w,h): raise RuntimeError('导出画幅发生变化')
    qa={'decode':'PASS','width':w,'height':h,'fps':fps,'duration':final_meta['duration'],'captions':len(p['captions']),
        'subtitle_timing':'ASR timestamps / manual edits','full_subjective_listening':False,'visual_review':'pending user review',
        'plan_hash':signature,'sha256':hashlib.sha256(out.read_bytes()).hexdigest()}
    write_json(work/'qa.json',qa)
    item=store.register(pid,out,'sample' if sample else 'final')
    with LOCK:
        current=store.load(pid);current['exports'].append({'id':item['id'],'kind':'sample' if sample else 'final','hash':signature,'at':now(),'qa':qa})
        current['qa']=qa;store.save(current,label='样片已输出' if sample else '成片已输出')
    for name in ('captions.srt','captions.ass','qa.json','overlay.html'):
        store.register(pid,work/name,'deliverable')
    return item

def gif_factory(store,pid,asset_id,text,motion,report):
    p=store.load(pid);asset=next(a for a in p['assets'] if a['id']==asset_id)
    if Path(asset['path']).suffix.lower()!='.png': raise ValueError('GIF 工厂需输入 PNG 素材，透明 PNG 效果最佳')
    font=fonts.render_font()
    work=store.folder(pid)/'renders'/uid('gif');work.mkdir(parents=True)
    manifest={'title':'口播动态素材','count':1,'groups':[{'name':'贴纸','atlas':asset['path'],'grid':[1,1],
        'ink':'#153c42','tint':'#64f1cc','entries':[{'text':text or '重点','cell':[0,0],'motion':motion,'icon':'none'}]}]}
    write_json(work/'manifest.json',manifest);report(.2,'调用 GIF 工厂生成真实循环动图')
    run([sys.executable,ROOT/'vendor/gif-factory/scripts/export_pack.py',work/'manifest.json',work/'pack','--font',font,'--jobs','1'],work/'gif.log')
    result=next((work/'pack').rglob('*.gif'))
    return materials.add(store,pid,result,text or '动态贴纸','GIF Factory / user PNG','gif-factory',asset_id)

def export_prompt(p,work):
    template=(ROOT/'assets/workbench/prompter.html').read_text(encoding='utf-8')
    fonts.stage_font(work)
    for script in ('microphone.js','prompter-fit.js','prompter-v2.js'):
        template=template.replace(f'<script src="/{script}"></script>','<script>'+(ROOT/'assets/workbench'/script).read_text(encoding='utf-8')+'</script>')
    portable={k:copy.deepcopy(p[k]) for k in ('id','title','pages','settings')};portable['assets']=[];portable['asset_urls']={};portable['timeline']=copy.deepcopy(p.get('timeline',{}))
    refs={pg.get('media_id') for pg in p['pages'] if pg.get('media_id')}
    import base64,mimetypes
    for a in p['assets']:
        if a['id'] not in refs:continue
        path=Path(a['path']);portable['assets'].append({k:a[k] for k in ('id','type','name')})
        if path.suffix.lower() in ('.png','.jpg','.jpeg','.gif','.webp','.svg') and path.stat().st_size<12*1024**2:
            portable['asset_urls'][a['id']]='data:'+(mimetypes.guess_type(path.name)[0] or 'image/png')+';base64,'+base64.b64encode(path.read_bytes()).decode()
        else:
            target=work/'media'/(a['id']+path.suffix);target.parent.mkdir(exist_ok=True);shutil.copy2(path,target);portable['asset_urls'][a['id']]='media/'+target.name
    blob=json.dumps(portable,ensure_ascii=False).replace('</','<\\/')
    target=work/'口播提词器.html';target.write_text(template.replace('__PROJECT__',blob),encoding='utf-8');return target

def inspect_frames(store,pid,report):
    from PIL import Image,ImageDraw
    p=store.load(pid);item=p.get('rough') or source(p)
    if not item.get('path'):raise ValueError('请先导入视频')
    meta=probe(item['path'])
    if not meta['video']:raise ValueError('构图检查需要视频')
    folder=store.folder(pid)/'analysis'/uid('frames');folder.mkdir(parents=True)
    times=[max(0,min(meta['duration']-.05,meta['duration']*x)) for x in (.01,.1,.2,.3,.4,.5,.6,.7,.8,.9,.96,.995)]
    cell_w=270;cell_h=round(meta['height']/meta['width']*cell_w)+26
    sheet=Image.new('RGB',(cell_w*4,cell_h*3),'#101b20');draw=ImageDraw.Draw(sheet)
    for i,t in enumerate(times):
        report(.1+.7*i/len(times),f'提取构图参考 {i+1}/{len(times)}')
        frame=folder/f'{i:02}.jpg';run(['ffmpeg','-v','error','-ss',t,'-i',item['path'],'-frames:v','1','-vf',f'scale={cell_w}:-1','-y',frame])
        x=i%4*cell_w;y=i//4*cell_h
        with Image.open(frame) as im:sheet.paste(im.convert('RGB'),(x,y+26))
        draw.text((x+9,y+7),f'{t:.2f}s',fill='#b5ebdb')
    out=folder/'composition-contact.jpg';sheet.save(out,quality=90)
    registered=store.register(pid,out,'analysis');store.patch(pid,{'layout_sheet_id':registered['id']},'构图关键帧已提取')
    return registered
