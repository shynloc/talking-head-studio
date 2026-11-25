"""Try a recording note against the actual cut before applying it to the project."""
import difflib
from core import Conflict, LOCK, digest, normalized
import materials
import timeline
import timeline_render


def notes(project):
    return [(page, tag) for page in project['pages'] for tag in page.get('tags', [])]


def suggested_caption(project, page, tag):
    if tag.get('cue_caption'):
        return next((c for c in project['captions'] if c['id'] == tag['cue_caption']), None)
    sentence = tag.get('sentence_id')
    matches = [c for c in project['captions'] if c.get('page_id') == page['id']
               and (not sentence or c.get('sentence_id') == sentence)
               and c.get('match_score', 0) >= .68 and not c.get('ambiguous_match')]
    if not matches:
        return None
    label = normalized(tag.get('brief') or tag.get('label', ''))
    # A product may be mentioned near the end of a long page or sentence.
    def overlap(cap):
        return difflib.SequenceMatcher(None, label, normalized(cap['text'])).find_longest_match().size
    ordered = sorted(matches, key=overlap, reverse=True)
    if len(ordered) == 1 or overlap(ordered[0]) >= 3 and overlap(ordered[0]) > overlap(ordered[1]):
        return ordered[0]
    return matches[0] if sentence or len({c.get('sentence_id') for c in matches}) == 1 else None


def suggested_asset(project, tag):
    if tag.get('asset_id'):
        return tag['asset_id']
    if tag['kind'] in ('flow','title'):
        return ''
    types = materials.AUDIO if tag['kind']=='sfx' else materials.IMAGES | materials.VIDEO
    label = normalized(tag.get('brief') or tag.get('label', ''))
    matches = [a['id'] for a in project['assets'] if a['type'] in types
               and len(normalized(a['name'])) >= 3 and normalized(a['name']) in label]
    return matches[0] if len(matches)==1 else ''


def summaries(project):
    return [{'id': tag['id'], 'page': pg['title'], 'label': tag.get('brief') or tag['label'],
             'status': tag.get('review', 'existing'), 'kind': tag['kind'],
             'asset_id': suggested_asset(project, tag), 'caption_id': (suggested_caption(project, pg, tag) or {}).get('id', '')}
            for pg, tag in notes(project)] if project['captions'] else []


def find(project, tag_id):
    for page, tag in notes(project):
        if tag['id'] == tag_id:
            return page, tag
    raise ValueError('这条画面备注已移除，请重新打开字幕。')


def options(project, tag, cap, data):
    mode = data.get('mode', 'original')
    name = (data.get('name') or tag.get('brief') or tag['label']).strip()
    asset_id = data.get('asset_id') or tag.get('asset_id', '')
    kind = tag['kind']
    if mode == 'title':
        kind, asset_id = 'title', ''
    elif mode == 'flow':
        kind, asset_id = 'flow', ''
    elif mode in ('asset', 'animated') or mode == 'original' and asset_id:
        asset = next((a for a in project['assets'] if a['id'] == asset_id), None)
        if not asset:
            raise ValueError('先选一份素材。')
        if asset['type'] in materials.AUDIO:
            kind = 'sfx'
        elif asset['type'] in materials.IMAGES | materials.VIDEO:
            kind = 'sticker' if asset['type'] in ('gif', 'png') else 'demo'
        else:
            raise ValueError('请选择图片、动画、视频或音效。')
    elif mode != 'original':
        raise ValueError('未知画面样式。')
    elif kind not in ('title', 'flow'):
        raise ValueError('请选择实际素材，或先试文字提示。')
    steps = tag.get('steps') or [part.strip() for part in cap['text'].replace('，','、').split('、') if part.strip()]
    return kind, name, asset_id, steps[:5]


def prepare(project, data):
    page, tag = find(project, data['tag_id'])
    cap = next((c for c in project['captions'] if c['id'] == data.get('caption_id')), None)
    if not cap:
        raise ValueError('请先选择这条备注对应的口播句子。')
    mapped = next((c for c in timeline_render.caption_map(project) if c['id'] == cap['id']), None)
    if not mapped:
        raise ValueError('这句话已被剪掉，请重新选一句。')
    kind, name, asset_id, steps = options(project, tag, cap, data)
    tag.setdefault('brief', tag['label'])
    tag.update(review='accepted', cue_caption=cap['id'], kind=kind, label=name, asset_id=asset_id, steps=steps)
    clip = next(c for c in project['timeline']['clips'] if c.get('tag_id') == tag['id'])
    length = mapped['end'] - mapped['start']
    asset = next((a for a in project['assets'] if a['id'] == asset_id), {})
    if kind == 'sfx' and asset.get('duration'):
        length = min(length, asset['duration'])
    clip.update(anchor='sentence', offset=0, source_in=0, duration=max(.025, length), enabled=True,
                track={'title':'title','flow':'sticker','sfx':'sfx','demo':'pip'}.get(kind,'sticker'))
    timeline.sync(project)
    return mapped['start'], length


def note_key(project, tag_id):
    _, tag = find(project, tag_id)
    return digest([timeline_render.signature(project), tag])


def preview(store, pid, data, report):
    import media
    p = store.load(pid)
    if p['settings'].get('caption_only'):
        raise ValueError('请先取消「只加口播字幕」。')
    key = note_key(p, data['tag_id'])
    variant = dict(data)
    if data.get('mode') == 'animated':
        _, tag = find(p, data['tag_id'])
        original = next((a for a in p['assets'] if a['id'] == data.get('asset_id') and a['type']=='png'), None)
        if not original:
            raise ValueError('请先选择一张 PNG 图片。')
        gif = media.gif_factory(store, pid, original['id'], data.get('name') or tag['label'], 'pulse', report)
        p = store.load(pid)
        if note_key(p, data['tag_id']) != key:
            raise Conflict('画面安排已改变，请重新试看。')
        variant.update(mode='asset', asset_id=gif['id'])
    start, length = prepare(p, variant)
    begin = max(0, start - .45)
    item = timeline_render.render(store, pid, report, begin, min(10, length+1), trial_project=p)
    return dict(id=item['id'], selection=variant, baseline=key)


def decide(store, pid, data):
    with LOCK:
        p = store.load(pid)
        _, tag = find(p, data['tag_id'])
        if data.get('skip'):
            tag['review'] = 'skipped'
            clip = next(c for c in p['timeline']['clips'] if c.get('tag_id') == tag['id'])
            clip['enabled'] = False
        else:
            if p['settings'].get('caption_only'):
                raise ValueError('请先取消「只加口播字幕」。')
            if note_key(p, tag['id']) != data.get('baseline'):
                raise Conflict('画面或字幕已改动，请重新试看这条备注。')
            prepare(p, data)
        timeline.validate(p)
        p['approvals'].pop('timeline', None)
        p['approvals'].pop('final', None)
        store.save(p, label='处理录制前的画面备注')
        return {'ok': True}
