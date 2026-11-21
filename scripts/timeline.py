"""V2 timeline: stable page/tag identities, planning and measured time domains."""
import copy, math

TRACKS = [('title','强调文字'),('sticker','贴纸 / 动画'),('pip','画中画 / 额外素材'),('caption','口播字幕'),('main','主画面'),('voice','原声'),('sfx','音效'),('music','背景音乐')]

def duration(pg, rate=240):
    return max(.5, float(pg.get('duration') or max(3, len(pg.get('text',''))/max(60,rate)*60)))

def sync(p):
    tl=p.setdefault('timeline',{'mode':'planned','clips':[], 'tracks':{}})
    tl.setdefault('tracks',{});tl.setdefault('clips',[]);tl.setdefault('mode','planned')
    pages={pg['id']:pg for pg in p['pages']};old={c['id']:c for c in tl['clips']}
    main=[];cursor=0;rate=p['settings']['speech_rate']
    extras=[c for c in tl['clips'] if c.get('track')=='main' and not c.get('page_id')]
    for c in extras:
        if c.get('before_page_id') and c['before_page_id'] not in pages:c.update(before_page_id='',orphaned=True)
    def insert(before):
        nonlocal cursor
        for c in extras:
            if c.get('before_page_id','')==before:
                c['start']=round(cursor,3);main.append(c);cursor+=c['duration']
    if tl['mode']=='planned':
        for pg in p['pages']:
            insert(pg['id']);c=old.get('page_'+pg['id'],{})
            c.update(id='page_'+pg['id'],track='main',page_id=pg['id'],name=pg['title'],start=round(cursor,3),duration=duration(pg,rate),kind=pg['type'],asset_id=pg.get('media_id',''))
            main.append(c);cursor+=c['duration']
        insert('')
    else:
        main=[c for c in tl['clips'] if c.get('track')=='main']
        for c in main:c['start']=round(cursor,3);cursor+=c['duration']
    starts={}
    for c in main:
        if c.get('page_id'):starts.setdefault(c['page_id'],c['start'])
    aux=[c for c in tl['clips'] if c.get('track')!='main' and not c.get('tag_id')]
    tags=[]
    for pg in p['pages']:
        for t in pg.get('tags',[]):
            c=old.get('tag_'+t['id'],{})
            sid=t.get('sentence_id','');sentences=pg.get('sentences',[]);ids=[s['id'] for s in sentences]
            orphan=bool(sid and sid not in ids) or (tl['mode']=='actual' and pg['id'] not in starts)
            base=starts.get(pg['id'],0)
            if sid in ids and tl['mode']=='planned':
                base+=sum(len(s['text']) for s in sentences[:ids.index(sid)])/max(1,len(pg['text']))*duration(pg,rate)
            if tl['mode']=='actual' and sid:
                caps=[x for x in p['captions'] if x.get('sentence_id')==sid]
                if caps:
                    from core import inverse_time
                    raw=inverse_time(caps[0]['start'],p['rough']['mapping']) if p.get('rough') else None
                    clip=next((c for c in main if c.get('source_id')==p['source_id'] and raw is not None and c.get('source_in',0)<=raw<c.get('source_in',0)+c['duration']),None)
                    if clip:base=clip['start']+raw-clip.get('source_in',0)
                    else:orphan=True
                else:orphan=True
            c.update(id='tag_'+t['id'],tag_id=t['id'],page_id=pg['id'],sentence_id=sid,name=t['label'],kind=t['kind'],asset_id=t.get('asset_id',''),steps=t.get('steps',[]),orphaned=orphan)
            c.setdefault('track',{'product':'pip','demo':'pip','sfx':'sfx','title':'title'}.get(t['kind'],'sticker'))
            c.setdefault('anchor','sentence');c.setdefault('offset',0);c.setdefault('duration',min(4,duration(pg,rate)));c.setdefault('enabled',True)
            if c['anchor']!='absolute':c['start']=round(max(0,base+c['offset']),3)
            tags.append(c)
    tl['clips']=main+aux+tags;tl['duration']=round(max([cursor]+[c['start']+c['duration'] for c in aux+tags]),3)
    p['schema_version']=2
    return tl

def validate(p):
    tl=sync(p);seen=set();tracks={x[0] for x in TRACKS}
    if len(tl['clips'])>5000:raise ValueError('轨道片段过多')
    for c in tl['clips']:
        if c['id'] in seen:raise ValueError('重复的轨道片段 ID')
        seen.add(c['id'])
        if c['track'] not in tracks:raise ValueError('未知轨道')
        for k in ('start','duration'):
            if not isinstance(c[k],(int,float)) or not math.isfinite(c[k]):raise ValueError('时间必须是有限数字')
        if c['start']<0 or c['duration']<=0 or c['duration']>86400:raise ValueError('时间范围无效')
        if not 0<=float(c.get('volume',1))<=2:raise ValueError('音量应为 0–2')
    return tl

def validate_output(p):
    """Editing stale timelines is allowed; rendering them is not."""
    from core import digest
    tl=validate(p)
    if any(c['track']=='main' and c.get('enabled') is False for c in tl['clips']):
        raise ValueError('主轨不支持禁用片段。请打开片段并保存以重新启用，或使用裁剪 / 删除调整主画面')
    if tl.get('needs_alignment'):
        raise ValueError('原片已更换，请完成粗剪并重新校准录制后导出')
    if tl['mode']=='actual':
        rough=p.get('rough')
        if not rough or rough.get('edl_hash')!=digest(p['edl']):
            raise ValueError('请先完成当前粗剪并重新校准录制')
        recordings=[c for c in tl['clips'] if c['track']=='main' and c.get('source_id') and not c.get('asset_id')]
        if any(c['source_id']!=p['source_id'] for c in recordings):
            raise ValueError('时间线仍关联旧原片，请重新校准录制')
        if tl.get('alignment') and tl['alignment']!={'source_id':p['source_id'],'edl_hash':digest(p['edl'])}:
            raise ValueError('剪辑清单已变化，请重新校准录制')
    return tl

def calibrate(p):
    from core import uid, time_map, build_captions, digest
    tl=sync(p)
    p.setdefault('timeline_before_alignment',copy.deepcopy(tl))
    if p.get('transcript'):p['captions']=build_captions(p)
    mapping=time_map(p['edl'])
    previous=[c for c in tl['clips'] if c['track']=='main']
    recordings=[c for c in previous if c.get('source_id') and not c.get('asset_id')]
    # Intersect with new keep ranges, retaining manual trim, order and inserted media.
    if tl['mode']=='actual' and recordings and not tl.get('needs_alignment') and all(c['source_id']==p['source_id'] for c in recordings):
        main=[]
        for c in previous:
            if c not in recordings:
                main.append(c);continue
            pieces=[]
            for m in mapping:
                a=max(c.get('source_in',0),m['source_start']);b=min(c.get('source_in',0)+c['duration'],m['source_end'])
                if b>a+.001:
                    piece=copy.deepcopy(c);piece.update(source_in=a,duration=round(b-a,6),role='recording')
                    if pieces:piece['id']=uid('clip')
                    pieces.append(piece)
            main.extend(pieces)
        tl['clips']=[c for c in tl['clips'] if c['track']!='main']+main
        tl['alignment']={'source_id':p['source_id'],'edl_hash':digest(p['edl'])}
        return sync(p)
    main=[]
    for m in mapping:
        boundaries=sorted({m['start'],m['end']}|{c['start'] for c in p['captions'] if c.get('page_id') and m['start']<c['start']<m['end']})
        for a,b in zip(boundaries,boundaries[1:]):
            cap=next((c for c in reversed(p['captions']) if c['start']<=a+.001 and c.get('page_id')), {})
            match={k:cap[k] for k in ('page_id','sentence_id') if k in cap}
            main.append({'id':uid('clip'),'track':'main','role':'recording','kind':'video','name':cap.get('text','实际口播')[:22], 'start':a,'duration':b-a,'source_in':m['source_start']+a-m['start'],'source_id':p['source_id'],**match})
    pages={pg['id']:pg for pg in p['pages']}
    extras=[]
    for i,c in enumerate(previous):
        pg=pages.get(c.get('page_id'))
        if c.get('source_id') and not c.get('asset_id'):continue
        if pg and pg.get('type')=='speech' and tl['mode']=='planned':continue
        extra=copy.deepcopy(c);extra['role']='extra'
        target=extra.get('before_page_id')
        if target is None or pg:
            target=next((x.get('page_id') for x in previous[i+1:] if x.get('page_id') and pages.get(x['page_id'],{}).get('type')=='speech'),'')
        extra['before_page_id']=target;extras.append(extra)
    merged=[];placed=set()
    for c in main:
        for i,e in enumerate(extras):
            if i not in placed and e.get('before_page_id') and e['before_page_id']==c.get('page_id'):
                e['orphaned']=False;merged.append(e);placed.add(i)
        merged.append(c)
    for i,e in enumerate(extras):
        if i not in placed:
            e['orphaned']=bool(e.get('before_page_id'));merged.append(e)
    main=merged
    tl['clips']=[c for c in tl['clips'] if c['track']!='main']+main;tl['mode']='actual';sync(p)
    tl.pop('needs_alignment',None)
    tl['alignment']={'source_id':p['source_id'],'edl_hash':digest(p['edl'])}
    return tl
