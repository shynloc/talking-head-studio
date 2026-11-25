"""Edit the caption or visual visible at a time in a reviewed sample."""
import math
from core import LOCK, uid
import materials
import timeline_render


def edit(store, pid, data):
    with LOCK:
        p = store.load(pid)
        state = timeline_render.require_sample(p, data.get('sample_id'), data.get('hash'))
        sample = state['sample']
        time = float(data['time'])
        start = sample['start'] or 0
        if not math.isfinite(time) or not start-.002 <= time <= start+sample['duration']+.002:
            raise ValueError('请选择当前预览中的位置。')
        cap_id = data.get('caption_id')
        span = next((s for s in state['caption_spans'] if s['id']==cap_id and s['start']<=time<s['end']), None)
        if data.get('operation') == 'caption':
            if not span:
                raise ValueError('这里没有字幕，请停在要改的那句话上。')
            text = str(data.get('text','')).strip()
            if not text:
                raise ValueError('请填写字幕文字。')
            next(c for c in p['captions'] if c['id']==cap_id)['text'] = text
        else:
            change_visual(p, data, time, state['duration'], span)
        store.edit(pid, p)
        return {'start':max(0,(span['start'] if span else time)-.35)}


def change_visual(p, data, time, total, span):
    if p['settings'].get('caption_only'):
        raise ValueError('先切回「字幕和画面」，再修改画面。')
    op = data.get('operation')
    if op not in ('visual','hide'):
        raise ValueError('未知的预览修改。')
    clips = p['timeline']['clips']
    clip = next((c for c in clips if c['id']==data.get('clip_id') and c['track'] in ('pip','sticker','title')
                 and c.get('enabled',True) and not p['timeline']['tracks'].get(c['track'],{}).get('muted')
                 and c['start']<=time<c['start']+c['duration']), None)
    if data.get('clip_id') and not clip:
        raise ValueError('这个画面已经移走，请重新试看。')
    tag = next((t for pg in p['pages'] for t in pg['tags'] if clip and t['id']==clip.get('tag_id')), None)
    if op=='hide':
        if not clip:
            raise ValueError('请选择要移除的画面。')
        clip['enabled']=False
        if tag:tag['review']='skipped'
        return
    asset_id=data.get('asset_id','')
    asset=next((a for a in p['assets'] if a['id']==asset_id),None)
    if asset_id and (not asset or asset['type'] not in materials.IMAGES | materials.VIDEO):
        raise ValueError('请选择有效的图片或视频。')
    name=(data.get('name') or (asset and asset['name']) or '').strip()
    if not name:
        raise ValueError('请填写要显示的文字。')
    if not clip:
        start=span['start'] if span else time
        length=min(span['end']-start if span else 2.5,total-start)
        if length<=.02:raise ValueError('请在视频结束前选择一个位置。')
        clip={'id':uid('clip'),'start':start,'duration':length,'anchor':'absolute','enabled':True}
        clips.append(clip)
    kind='demo' if asset_id else 'title'
    track='pip' if asset_id else 'title'
    if p['timeline']['tracks'].get(track,{}).get('muted'):
        raise ValueError('当前画面轨道已隐藏，请先取消隐藏。')
    clip.update(kind=kind,track=track,name=name,asset_id=asset_id,source_in=0)
    if tag:
        tag.setdefault('brief',tag['label'])
        tag.update(kind=kind,label=name,asset_id=asset_id,review='accepted')
