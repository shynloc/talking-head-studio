"""Render the exact V2 timeline, including concurrent visuals and mixed audio."""
import copy, hashlib, json, math, shutil
from pathlib import Path
from core import ROOT, LOCK, uid, now, digest, rough_current, aligned_with_cuts, write_json, source, file_digest
import fonts, media, timeline

def signature(p):
    assets={a['id']:a for a in p['assets']};used={c.get('asset_id') for c in p['timeline']['clips'] if c.get('enabled',True)}
    return digest({'timeline':p['timeline'],'captions':p['captions'],'settings':p['settings'],'source':source(p),'assets':{i:file_digest(assets[i]['path']) if Path(assets[i]['path']).exists() else 'missing' for i in used if i in assets}})

def review_state(p):
    """Select playable exports from exactly the saved timeline being reviewed."""
    original = source(p)
    if not original.get('video') or not Path(original.get('path') or '.').is_file():
        return {'state': 'source', 'message': '导入录制视频后，才能生成用于确认的样片。'}
    if not rough_current(p):
        return {'state': 'rough', 'message': '需要按当前保留的片段更新剪辑预览。'}
    tl = p['timeline']
    recordings = [c for c in tl['clips'] if c.get('source_id') and not c.get('asset_id') and c['track'] == 'main']
    if not p['approvals'].get('rough'):
        return {'state': 'approve_rough', 'message': '先试听剪辑预览，满意后使用这一版。'}
    if (tl['mode'] != 'actual' or tl.get('needs_alignment')
            or not aligned_with_cuts(p)
            or any(c['source_id'] != p['source_id'] for c in recordings)):
        return {'state': 'align', 'message': '校准后，工作台会把录制片段对应到时间线，保留安排好的额外素材。'}
    try:
        timeline.validate_output(p)
    except ValueError as exc:
        return {'state': 'blocked', 'message': str(exc)}
    files = {m['id']: m.get('path') for m in p['media'] + p['assets']}
    main = [c for c in tl['clips'] if c['track'] == 'main']
    if not main or tl['tracks'].get('main', {}).get('muted'):
        return {'state': 'blocked', 'message': '请在时间线保留可见的主画面。'}
    for clip in tl['clips']:
        track = clip['track']
        if (p['settings'].get('caption_only') and track != 'main') or track in ('caption','voice') or not clip.get('enabled', True) or tl['tracks'].get(track, {}).get('muted'):
            continue
        file_id = clip.get('asset_id') or clip.get('source_id')
        path = files.get(file_id)
        if file_id or track in ('main','sfx','music') or clip.get('kind') not in ('title','flow'):
            if not path or not Path(path).is_file():
                return {'state':'material', 'clip_id':clip['id'], 'message':f'请为「{clip["name"]}」选择素材，或从本次剪辑中略过。'}
        if clip.get('orphaned'):
            return {'state':'placement', 'clip_id':clip['id'], 'message':f'「{clip["name"]}」原来对应的句子已找不到。'}

    fingerprint = signature(p)
    def latest(kind):
        for item in reversed(p['exports']):
            if item['kind'] != kind or item['hash'] != fingerprint:
                continue
            path = files.get(item['id'])
            if path and Path(path).is_file():
                qa = item.get('qa', {})
                return {'id': item['id'], 'start': qa.get('sample_start'), 'duration': qa.get('duration')}
        return None

    from caption_review import info
    spans = [] if tl['tracks'].get('caption',{}).get('muted') else caption_map(p,audition=True)
    return {'state': 'ready', 'hash': fingerprint, 'sample': latest('timeline_sample'),
            'final': latest('timeline_final'), 'duration': sum(c['duration'] for c in main),
            'caption_spans': spans, 'caption_review':info(p,spans),
            'approved': p['approvals'].get('timeline', {}).get('hash') == fingerprint,
            'has_previous_sample': any(e['kind'] == 'timeline_sample' for e in p['exports'])}

def caption_map(p, audition=False):
    """Intersect kept source ranges with the main track, also mapping audition to the rough file."""
    if not p.get('rough'):return []
    pieces=[]
    for clip in p['timeline']['clips']:
        if clip.get('track')!='main' or clip.get('source_id')!=p['source_id'] or clip.get('asset_id'):continue
        lo=clip.get('source_in',0)
        for m in p['rough']['mapping']:
            a=max(lo,m['source_start']); b=min(lo+clip['duration'],m['source_end'])
            if b-a<.001:continue
            rough=m['start']+a-m['source_start']; position=clip['start']+a-lo
            pieces.append((position,rough,b-a))
    runs=[]
    for pos,rough,length in sorted(pieces):
        if runs and abs(pos-runs[-1][0]-runs[-1][2])<.002 and abs(rough-runs[-1][1]-runs[-1][2])<.002:
            runs[-1][2]+=length
        else:
            runs.append([pos,rough,length])
    result=[]
    for pos,rough,length in runs:
        for cap in p['captions']:
            a=max(rough,cap['start']); b=min(rough+length,cap['end'])
            if b<=a+.02:continue
            span=dict(cap,start=pos+a-rough,end=pos+b-rough)
            if audition:span.update(listen_start=max(rough,a-.42),listen_end=min(rough+length,b+.42))
            result.append(span)
    return sorted(result,key=lambda c:c['start'])


def require_sample(p, sample_id, fingerprint):
    state = review_state(p)
    sample = state.get('sample') or {}
    if state.get('state') != 'ready' or sample.get('id') != sample_id or not sample_id or state['hash'] != fingerprint:
        raise ValueError('当前样片已变化，请重新试看并选择导出方式。')
    return state


def render_base(p, tl, work, w, h, fps, start, duration, report):
    assets = {a['id']: a for a in p['assets']}
    files = {m['id']: m for m in p['media']}
    main = [c for c in tl['clips'] if c['track'] == 'main']
    parts=[]
    report(.02,'构建主画面与原声，保持原始比例')
    for c in main:
        if c.get('orphaned'):raise ValueError(c['name']+' 的插入位置已删除，请重新指定')
        a=max(start,c['start']);b=min(start+duration,c['start']+c['duration'])
        if b<=a:continue
        length=b-a;offset=a-c['start'];path=assets.get(c.get('asset_id'),files.get(c.get('source_id'),{})).get('path');out=work/(c['id']+'.mp4')
        volume=0 if tl['tracks'].get('voice',{}).get('muted') else float(c.get('volume',1))
        if path:
            image=Path(path).suffix.lower() in ('.png','.jpg','.jpeg','.webp','.svg');info={'audio':False} if image else media.probe(path)
            cut=float(c.get('source_in',0))+offset
            if not image and info['duration']+1/fps<cut+length:raise ValueError(c['name']+' 的素材长度不足，请缩短片段或更换素材')
            inputs=['-loop','1','-i',path] if image else ['-ss',cut,'-i',path]
            vf=f'scale={w}:{h}:force_original_aspect_ratio=decrease,pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:color=0xf4ecdf,setsar=1,fps={fps}'
            if info.get('audio') and not image:
                inputs+=['-vf',vf,'-af',f'volume={volume},aresample=48000,apad','-map','0:v','-map','0:a']
            else:inputs+=['-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-vf',vf,'-map','0:v','-map','1:a']
        else:
            if tl['mode']=='actual':raise ValueError(c['name']+' 尚未绑定主画面素材')
            from PIL import Image, ImageDraw, ImageFont
            import textwrap
            im=Image.new('RGB',(w,h),'#f4ecdf');draw=ImageDraw.Draw(im);font=ImageFont.truetype(fonts.render_font(),max(18,h//20));pg=next((pg for pg in p['pages'] if pg['id']==c.get('page_id')),{});text=c['name']+'\n\n'+'\n'.join(textwrap.wrap(pg.get('text','待录制 / 待制作'),max(12,w//(h//20)-6)))
            draw.multiline_text((w*.08,h*.14),text,font=font,fill='#002fa7',spacing=12);imagefile=work/(c['id']+'.png');im.save(imagefile)
            inputs=['-loop','1','-i',imagefile,'-f','lavfi','-i','anullsrc=r=48000:cl=stereo','-map','0:v','-map','1:a']
        media.run(['ffmpeg','-v','error',*inputs,'-t',length,'-r',fps,'-c:v','libx264','-pix_fmt','yuv420p','-preset','fast','-crf','19','-c:a','aac','-ac','2','-ar','48000','-y',out],work/(c['id']+'.log'));parts.append(out)
    (work/'concat.txt').write_text('\n'.join("file '"+x.name+"'" for x in parts),encoding='utf-8')
    base=work/'base.mp4';media.run(['ffmpeg','-v','error','-f','concat','-safe','0','-i',work/'concat.txt','-c','copy','-y',base])
    return base


def layers(p, tl, start, duration):
    scenes=[];audio=[]
    for c in tl['clips']:
        if p['settings'].get('caption_only') or c['track'] in ('main','caption','voice') or not c.get('enabled',True) or tl['tracks'].get(c['track'],{}).get('muted'):continue
        if c['start']>=start+duration or c['start']+c['duration']<=start:continue
        if c.get('orphaned'):raise ValueError(c['name']+' 失去句子关联，请重新定位')
        if c['track'] in ('music','sfx'):
            if not c.get('asset_id'):raise ValueError(c['name']+' 尚未绑定音频素材')
            audio.append(c);continue
        kind=c.get('kind','title')
        if kind not in ('title','flow') and not c.get('asset_id'):raise ValueError(c['name']+' 尚未绑定画面素材')
        x,y,cw,ch=[float(c.get(k,v)) for k,v in [('x',.06),('y',.04),('width',.35),('height',.2)]]
        if not c.get('fullscreen'):
            px,py,pw,ph=p['settings']['protected_rect']
            if x<0 or y<0 or cw<=0 or ch<=0 or x+cw>1.001 or y+ch>1.001:raise ValueError(c['name']+' 的画面区域越界')
            if max(x,px)<min(x+cw,px+pw) and max(y,py)<min(y+ch,py+ph):raise ValueError(c['name']+' 与人物保护区重叠，请调整布局或明确允许全屏演示')
        scenes.append({**c,'title':c['name'],'kind':kind,'start':c['start'],'end':c['start']+c['duration'],'enabled':True,'x':x,'y':y,'width':cw,'height':ch,'layer':dict((k,i) for i,(k,_) in enumerate(reversed(timeline.TRACKS))).get(c['track'],0)})
    return scenes, audio


def render(store,pid,report,start=0,duration=10,final=False,trial_project=None):
    p=trial_project if trial_project is not None else store.load(pid)
    tl=timeline.validate_output(p);sig=signature(p)
    if final and tl['mode']!='actual':raise ValueError('当前是录制前编排，请先导入并校准实际视频')
    if final and p.get('approvals',{}).get('timeline',{}).get('hash')!=sig:
        raise ValueError('时间线已变化或尚未确认。请从「成片检查与导出」生成样片，试看后再确认。')
    main=[c for c in tl['clips'] if c['track']=='main'];total=sum(c['duration'] for c in main)
    if not main:raise ValueError('没有主画面')
    if any(c.get('enabled',True) and c['start']+c['duration']>total+.05 for c in tl['clips'] if c['track']!='main' and not p['settings'].get('caption_only')):raise ValueError('辅助素材超出主画面末尾，请调整长度，避免留空画面')
    if tl['tracks'].get('main',{}).get('muted'):raise ValueError('主画面已隐藏，不能导出空白画面')
    meta=source(p);w,h=int(meta.get('width') or 1280),int(meta.get('height') or 720);fps=float(meta.get('fps') or 25)
    if not w or not h:w,h=1280,720
    start=0 if final else max(0,min(float(start),total-.1));duration=total if final else min(max(.1,float(duration)),total-start)
    work=store.folder(pid)/'renders'/uid('timeline');work.mkdir(parents=True);assets={a['id']:a for a in p['assets']}
    base = render_base(p, tl, work, w, h, fps, start, duration, report)
    scenes, audio = layers(p, tl, start, duration)
    q=copy.deepcopy(p);q['scenes']=scenes;q['v2_overlay']=True;q['captions']=caption_map(p) if tl['mode']=='actual' and not tl['tracks'].get('caption',{}).get('muted') else []
    media.subtitles(q,work,w,h);media.create_overlay(q,work,w,h,fps);overlay=media.render_overlay(work,w,h,fps,start,duration,report)
    inputs=['-i',base,'-i',overlay];filters=[f'[0:v][1:v]overlay=0:0:format=auto,setpts=PTS+{start}/TB,{fonts.ASS_FILTER},setpts=PTS-STARTPTS,format=yuv420p[v]','[0:a]aresample=48000[voice]'];mix=['[voice]']
    music_count=sum(c['track']=='music' for c in audio)
    if music_count:filters[1]='[0:a]aresample=48000,asplit='+str(music_count+1)+'[voice]'+''.join(f'[duck{k}]' for k in range(music_count))
    duck_index=0
    for i,c in enumerate(audio,2):
        asset=assets.get(c['asset_id']);path=asset and asset['path']
        if not path or not Path(path).exists():raise ValueError(c['name']+' 音频素材不存在')
        a=max(start,c['start']);b=min(start+duration,c['start']+c['duration']);offset=float(c.get('source_in',0))+a-c['start'];length=b-a
        info=media.probe(path)
        if not info.get('audio') or info['duration']+.05<offset+length:raise ValueError(c['name']+' 音频长度不足或没有音轨')
        inputs+=['-ss',offset,'-t',length,'-i',path];fade=min(float(c.get('fade',.2)),length/2);volume=float(c.get('volume',.15 if c['track']=='music' else 1));delay=round((a-start)*1000)
        filters.append(f'[{i}:a]aresample=48000,volume={volume},afade=t=in:d={fade},afade=t=out:st={max(0,length-fade)}:d={fade},adelay={delay}:all=1[a{i}]');
        if c['track']=='music':
            filters.append(f'[a{i}][duck{duck_index}]sidechaincompress=threshold=0.025:ratio=6:attack=20:release=300[ducked{i}]');mix.append(f'[ducked{i}]');duck_index+=1
        else:mix.append(f'[a{i}]')
    filters.append(''.join(mix)+f'amix=inputs={len(mix)}:duration=first:normalize=0,alimiter=limit=0.89:level=false:latency=true,apad[a]')
    out=work/('timeline-final.mp4' if final else 'timeline-sample.mp4');report(.82,'合成多层画面、字幕及音频')
    media.run(['ffmpeg','-v','warning',*inputs,'-filter_complex',';'.join(filters),'-map','[v]','-map','[a]','-t',duration,'-r',fps,'-c:v','libx264','-preset','fast','-crf','19','-c:a','aac','-b:a','192k','-movflags','+faststart','-y',out],work/'encode.log',cwd=work)
    media.run(['ffmpeg','-v','error','-i',out,'-f','null','-'],work/'decode.log');result=media.probe(out)
    if (result['width'],result['height'])!=(w,h):raise RuntimeError('画幅检查失败')
    if trial_project is not None:
        return store.register(pid,out,'note_preview')
    item=store.register(pid,out,'final' if final else 'sample');qa={'decode':'PASS','width':w,'height':h,'duration':result['duration'],'fps':fps,'timeline_hash':sig,'subjective_review':'pending','sha256':file_digest(out)}
    if not final:qa['sample_start']=start
    write_json(work/'qa.json',qa)
    with LOCK:
        current=store.load(pid);current['qa']=qa;current['exports'].append({'id':item['id'],'kind':'timeline_final' if final else 'timeline_sample','hash':sig,'at':now(),'qa':qa});store.save(current,label='时间线视频已输出')
    for name in ('captions.srt','captions.ass','qa.json'):store.register(pid,work/name,'deliverable')
    return item
