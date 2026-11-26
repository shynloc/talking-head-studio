"""Save caption corrections without rendering; check exact matches before bulk edits."""
from core import LOCK, Conflict, digest, rough_current
from timeline_render import caption_map


def layout_key(p, spans):
    return digest([p['source_id'], (p.get('rough') or {}).get('media_id'),
                   [(s['id'],s['start'],s['end'],s.get('listen_start'),s.get('listen_end')) for s in spans]])


def context(p, spans):
    key = layout_key(p, spans)
    saved = p.get('caption_review', {})
    if saved.get('layout') != key:
        saved = {'layout':key, 'checked':{}, 'pending':[], 'undo':[]}
    return saved


def info(p, spans):
    saved = context(p, spans)
    reasons = {}
    for cap in spans:
        reason = cap.get('listen_reason')
        # Older projects have word timings but no saved confidence hints.
        if not reason and len(cap['text'].strip()) <= 2 and cap['end']-cap['start'] > 2:
            reason = '这句字少、停留时间长，建议听一下。'
        if reason and saved['checked'].get(cap['id']) != cap['text']:
            reasons[cap['id']] = reason
    return {'layout':saved['layout'], 'issues':reasons, 'pending':saved['pending'], 'can_undo':bool(saved['undo'])}


def apply(store, pid, data):
    with LOCK:
        p = store.load(pid)
        if not rough_current(p) or not p['approvals'].get('rough') or p['timeline']['tracks'].get('caption',{}).get('muted'):
            raise Conflict('当前剪辑已变化，请重新打开字幕预览。')
        spans = caption_map(p, audition=True)
        saved = context(p, spans)
        if saved['layout'] != data.get('layout'):
            raise Conflict('视频或字幕位置已变化，请重新打开预览。')
        visible = {s['id'] for s in spans}
        caps = {c['id']:c for c in p['captions'] if c['id'] in visible}
        op = data.get('operation')
        if op == 'undo':
            edits = [{'id':e['id'],'before':e['after'],'after':e['before']} for e in saved['undo']]
            if not edits: raise ValueError('没有可撤销的批量修改。')
        elif op in ('save','bulk','keep'):
            edits = data.get('edits',[])
        else:
            raise ValueError('未知字幕操作。')
        if not edits or len(edits)>len(caps) or len({e['id'] for e in edits})!=len(edits):
            raise ValueError('请选择要修改的字幕。')
        for e in edits:
            cap = caps.get(e['id'])
            if not cap or cap['text'] != e['before']:
                raise Conflict('这句字幕已在其他窗口修改，请重新打开后对照。')
            if not isinstance(e['after'],str) or not e['after'].strip():
                raise ValueError('请填写字幕文字。')
            if op=='keep' and e['after']!=e['before']:
                raise ValueError('保留原文时文字应相同。')
        changed = [e for e in edits if e['after']!=e['before']]
        if op=='bulk':
            if not changed:raise ValueError('没有其他相同的文字。')
            saved['undo'] = [dict(e,checked=saved['checked'].get(e['id'])) for e in changed]
        previous_checks = {e['id']:e.get('checked') for e in saved['undo']} if op=='undo' else {}
        for e in edits:
            caps[e['id']]['text'] = e['after']
            saved['checked'][e['id']] = previous_checks.get(e['id']) if op=='undo' else e['after']
        if op=='undo':saved['undo']=[]
        if changed:
            baseline = saved.setdefault('baseline',{})
            for e in changed:
                baseline.setdefault(e['id'],e['before'])
                if e['after']==baseline[e['id']]:
                    baseline.pop(e['id'])
            saved['pending'] = list(baseline)
            for kind in ('final','timeline'):p['approvals'].pop(kind,None)
        p['caption_review'] = saved
        store.save(p,label='校对口播字幕')
        return {'project':dict(p,rough_current=True),'texts':{e['id']:e['after'] for e in edits},
                'review':info(p,caption_map(p,audition=True))}


def proof(jobs, pid, args, report):
    from timeline_render import review_state, signature, render
    p = jobs.store.load(pid)
    state = review_state(p)
    if state['state']!='ready' or state['hash']!=args.get('hash'):
        raise Conflict('画面或字幕有更新，请重新打开预览。')
    ids = state['caption_review']['pending']
    item = render(jobs.store,pid,report,start=0,duration=state['duration'])
    with LOCK:
        current = jobs.store.load(pid)
        if signature(current)!=state['hash']:
            raise Conflict('试看期间项目已变化，请按最新版重新试看。')
        saved = context(current,caption_map(current,audition=True))
        saved.update(pending=[], baseline={}, proof_id=item['id'], proof_captions=ids)
        current['caption_review']=saved
        jobs.store.save(current,label='已生成校对后的全片预览')
    return item

def export_reviewed_copy(store, pid, state, report):
    """Deliver the exact full-length proof once the user has approved its current hash."""
    import shutil
    from pathlib import Path
    from core import file_digest, now, uid, write_json
    from timeline_render import signature
    p=store.load(pid)
    sample=state['sample']
    if (p.get('caption_review',{}).get('proof_id')!=sample['id'] or sample['start']!=0
            or abs(sample['duration']-state['duration'])>.15):
        return None
    report(.2,'正在保存刚刚看过的完整视频')
    record=next(e for e in p['exports'] if e['id']==sample['id'])
    source=Path(next(m['path'] for m in p['media'] if m['id']==sample['id']))
    folder=store.folder(pid)/'renders'/uid('timeline')
    folder.mkdir(parents=True)
    target=folder/'timeline-final.mp4'
    shutil.copy2(source,target)
    qa=dict(record['qa'],reviewed_sample=sample['id'])
    qa.pop('sample_start',None)
    if file_digest(target)!=qa['sha256']:
        raise Conflict('试看文件有变化，请重新生成预览。')
    for name in ('captions.ass','captions.srt'):
        shutil.copy2(source.with_name(name),folder/name)
    write_json(folder/'qa.json',qa)
    with LOCK:
        current=store.load(pid)
        if (signature(current)!=state['hash'] or
                current['approvals'].get('timeline',{}).get('sample_id')!=sample['id']):
            raise Conflict('字幕或画面已更新，请查看最新预览。')
        item=store.register(pid,target,'final')
        for name in ('captions.ass','captions.srt','qa.json'):
            store.register(pid,folder/name,'deliverable')
        current=store.load(pid)
        current['qa']=qa
        current['exports'].append(dict(id=item['id'],kind='timeline_final',hash=state['hash'],at=now(),qa=qa))
        store.save(current,label='保存已确认的完整试看')
    return item
