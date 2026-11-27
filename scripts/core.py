"""Persistent project model and content/time correspondence. No GUI dependencies."""
from __future__ import annotations
import copy, difflib, hashlib, json, math, os, re, threading, time, uuid
from pathlib import Path
from manuscript_annotations import spoken

VERSION = '3.18.0'
ROOT = Path(__file__).resolve().parents[1]
LOCK = threading.RLock()

def uid(prefix='id'):
    return prefix + '_' + uuid.uuid4().hex[:12]

def now():
    return time.strftime('%Y-%m-%dT%H:%M:%S%z')

def digest(value):
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True).encode()).hexdigest()

def edl_digest(edl):
    """Use the same time representation after JSON passes through a browser."""
    return digest([dict(row, start=float(row['start']), end=float(row['end'])) for row in edl])

def matches_edl(stored, edl):
    if not stored:
        return False
    if stored in (edl_digest(edl), digest(edl)):
        return True
    # V3.5 skip_rough used integer zero and ffprobe's floating-point duration.
    if len(edl) == 1 and edl[0]['start'] == 0:
        return stored == digest([dict(edl[0], start=0, end=float(edl[0]['end']))])
    return False

def rough_current(p):
    return matches_edl((p.get('rough') or {}).get('edl_hash'), p['edl'])

def aligned_with_cuts(p):
    alignment = p['timeline'].get('alignment')
    return not alignment or (alignment.get('source_id') == p['source_id']
                             and matches_edl(alignment.get('edl_hash'), p['edl']))

def write_json(path, data):
    path = Path(path); path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix('.tmp-' + uuid.uuid4().hex[:6])
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    os.replace(tmp, path)

def normalized(text):
    return re.sub(r'[^\w\u4e00-\u9fff]', '', text).lower()

def split_sentences(text):
    return [x.strip() for x in re.findall(r'[^。！？!?\n]+[。！？!?]?|[^\n]+$', text) if x.strip()]

def sync_sentences(page):
    page['text'] = spoken(page.get('text', ''))
    old = page.get('sentences', []); available = old.copy(); new = []
    for text in split_sentences(page.get('text', '')):
        match = next((s for s in available if s['text'] == text), None)
        if match is None and available:
            best = max(available, key=lambda s: difflib.SequenceMatcher(None, normalized(text), normalized(s['text'])).ratio())
            if difflib.SequenceMatcher(None, normalized(text), normalized(best['text'])).ratio() >= .70:
                match = best
        if match:
            available.remove(match)
        new.append({'id': match['id'] if match else uid('sent'), 'text': text})
    page['sentences'] = new
    valid = {s['id'] for s in new}
    for tag in page.get('tags', []):
        tag['orphaned'] = bool(tag.get('sentence_id') and tag['sentence_id'] not in valid)
    return page

def page(text='', kind='speech', title='', duration=0):
    return sync_sentences({'id': uid('page'), 'type': kind, 'title': title or ('口播' if kind == 'speech' else '展示'),
        'text': text, 'notes': '', 'duration': duration, 'tags': [], 'media_id': '', 'sentences': []})

def script_pages(text, mode='original'):
    text = spoken(text).replace('\r\n', '\n').strip()
    if mode == 'light':
        text = re.sub(r'^\s{0,3}#{1,6}\s*', '', text, flags=re.M)
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        text = re.sub(r'\*\*([^*]+)\*\*', r'\1', text)
        for a, b in [('综上所述', '简单来说'), ('此外，', '另外，'), ('因此，', '所以，'), ('首先，', '先说第一点，')]:
            text = text.replace(a, b)
    result, chunk = [], ''
    for paragraph in text.split('\n'):
        for sentence in split_sentences(paragraph):
            if chunk and len(chunk) + len(sentence) > 115:
                result.append(page(chunk, title=chunk[:16])); chunk = ''
            chunk += sentence
        if len(chunk) > 70:
            result.append(page(chunk, title=chunk[:16])); chunk = ''
    if chunk:
        result.append(page(chunk, title=chunk[:16]))
    return result or [page()]

def default_project(title='未命名口播'):
    return {'schema_version': 2, 'id': uid('project'), 'title': title, 'version': 0, 'created': now(), 'updated': now(),
        'pages': [page('', title='新的一页')],
        'source_text': '', 'script_mode': 'original', 'media': [], 'source_id': '', 'transcript': [], 'edl': [],
        'rough': None, 'captions': [], 'scenes': [], 'assets': [], 'exports': [], 'approvals': {}, 'feedback': [], 'tasks': [],
        'settings': {'speech_rate': 240, 'font_size': 52, 'prompt_width': 760, 'scroll_speed': 24,
            'caption_y': .84, 'caption_size': .042, 'overlay_y': .04, 'overlay_height': .20,
            'protected_rect': [.08, .29, .84, .45], 'accent': '#f19a50', 'sfx': True, 'model': 'medium',
            'silence_seconds': .75, 'silence_db': -34, 'keep_pause': .34, 'terms': '', 'target_seconds': 180},
        'recording_log': [], 'qa': {}, 'history': []}

class Conflict(Exception):
    pass

class Store:
    def __init__(self, root):
        self.root = Path(root).resolve(); self.root.mkdir(parents=True, exist_ok=True)

    def folder(self, project_id):
        if not re.fullmatch(r'project_[a-f0-9]{12}', project_id):
            raise ValueError('无效的工程编号')
        return self.root / project_id

    def load(self, project_id):
        p = json.loads((self.folder(project_id) / 'project.json').read_text(encoding='utf-8'))
        if p.get('schema_version')==1:
            backup=self.folder(project_id)/'project-v1-backup.json'
            if not backup.exists():write_json(backup,p)
        import timeline
        timeline.sync(p)
        return p

    def listing(self):
        result = []
        for path in self.root.glob('project_*/project.json'):
            try:
                p = json.loads(path.read_text(encoding='utf-8'))
                item = {k: p[k] for k in ('id', 'title', 'updated', 'version')}
                item['example'] = bool(p.get('example') or any(h.get('label') == '创建可编辑示例工程' for h in p.get('history', [])))
                result.append(item)
            except (OSError, ValueError):
                continue
        return sorted(result, key=lambda p: p['updated'], reverse=True)

    def save(self, p, expected=None, label='保存'):
        with LOCK:
            path = self.folder(p['id']) / 'project.json'
            if path.exists():
                current = self.load(p['id'])
                if expected is not None and current['version'] != expected:
                    raise Conflict('工程已有更新。当前编辑已保存在浏览器恢复草稿中；请重新载入后比较。')
                revision = self.folder(p['id']) / 'revisions' / f"{current['version']:06}.json"
                write_json(revision, current)
                p['version'] = current['version'] + 1
            p['updated'] = now()
            p['history'] = (p.get('history', []) + [{'at': now(), 'label': label, 'version': p['version']}])[-120:]
            write_json(path, p)
            return p

    def patch(self, project_id, changes, label='任务完成'):
        with LOCK:
            p = self.load(project_id); p.update(changes)
            return self.save(p, label=label)

    def edit(self, project_id, data):
        with LOCK:
            p = self.load(project_id)
            if p['version'] != data['version']:
                raise Conflict('工程已更新，请重新载入；未保存内容已保存在恢复草稿。')
            editable = ['title', 'pages', 'settings', 'edl', 'captions', 'scenes', 'feedback', 'recording_log', 'timeline']
            if len(data.get('pages', [])) > 1000:
                raise ValueError('单工程页面过多')
            for key in editable:
                if key not in data or data[key] == p.get(key): continue
                if key == 'edl' and data[key] != p[key]:
                    validate_edl(data[key], source(p)['duration'])
                    p['previous_rough'] = p['rough']; p['rough'] = None; p['approvals'] = {}; p['qa'] = {}
                if key in ['captions', 'scenes', 'timeline'] and data[key] != p[key]:
                    p['approvals'].pop('final', None);p['approvals'].pop('timeline',None)
                if key == 'settings' and any(data[key].get(k)!=p[key].get(k) for k in VISUAL_SETTINGS):
                    p['approvals'].pop('final', None);p['approvals'].pop('timeline',None)
                if key == 'pages':
                    if data[key] != p[key]:
                        p['approvals'].pop('script', None); p['approvals'].pop('final', None);p['approvals'].pop('timeline',None)
                    for pg in data[key]: sync_sentences(pg)
                if key == 'scenes':
                    for scene in data[key]:
                        old = next((s for s in p['scenes'] if s['id'] == scene['id']), {})
                        if p.get('rough') and (not old or scene.get('start') != old.get('start') or scene.get('end') != old.get('end')):
                            scene['source_start'] = inverse_time(scene['start'], p['rough']['mapping'])
                            scene['source_end'] = inverse_time(scene['end'], p['rough']['mapping'], end=True)
                            scene['manual_timing'] = True
                p[key] = data[key]
            import timeline
            timeline.validate(p)
            return self.save(p, data['version'])

    def register(self, project_id, path, kind='output', name=None):
        with LOCK:
            p = self.load(project_id); item = {'id': uid('file'), 'path': str(Path(path).resolve()), 'kind': kind,
                'name': name or Path(path).name, 'created': now()}
            p['media'].append(item); self.save(p, label='登记文件')
            return item

def source(p):
    return next((m for m in p['media'] if m['id'] == p['source_id']), {})

def validate_edl(edl, duration):
    if not edl: raise ValueError('剪辑清单不能为空')
    last = 0
    for row in edl:
        if abs(row['start'] - last) > .005 or row['end'] <= row['start'] or row['end'] > duration + .01:
            raise ValueError('剪辑区间必须连续覆盖原片，且不重叠')
        last = row['end']
    if abs(last - duration) > .01: raise ValueError('剪辑清单没有覆盖整个原片')
    if not any(r['keep'] for r in edl): raise ValueError('至少保留一个片段')

def time_map(edl):
    out, cursor = [], 0.
    for r in edl:
        if r['keep']:
            out.append({'id': r['id'], 'source_start': r['start'], 'source_end': r['end'],
                'start': cursor, 'end': cursor + r['end'] - r['start']})
            cursor = out[-1]['end']
    return out

def inverse_time(t, mapping, end=False):
    for m in (reversed(mapping) if end else mapping):
        if m['start']-.001 <= t <= m['end']+.001:
            return m['source_start'] + max(0,min(t-m['start'],m['end']-m['start']))
    return None

def forward_time(t, mapping, end=False):
    if t is None: return None
    for m in (reversed(mapping) if end else mapping):
        if m['source_start']-.001 <= t <= m['source_end']+.001:
            return m['start'] + max(0,min(t-m['source_start'],m['source_end']-m['source_start']))
    return None

def match_script(p, text):
    target = normalized(text); best, score, runner_up = None, 0, 0
    for pg in p['pages']:
        for sent in pg['sentences']:
            value = normalized(sent['text'])
            ratio = difflib.SequenceMatcher(None, target, value).ratio()
            if target and target in value: ratio = max(ratio, .85)
            if ratio > score:
                runner_up, score = score, ratio
                best = {'page_id': pg['id'], 'sentence_id': sent['id']}
            else:
                runner_up = max(runner_up, ratio)
    return {**(best or {}), 'match_score': round(score, 3), 'ambiguous_match': score - runner_up < .08} if score >= .4 else {'match_score': round(score, 3)}

def mapped_words(p):
    mapping = time_map(p['edl']); result = []
    for seg in p['transcript']:
        words = seg.get('words') or []
        estimated = not words
        if estimated:
            chars = list(seg['text']); n = max(len(chars), 1)
            words = [{'word': c, 'start': seg['start'] + i * (seg['end'] - seg['start']) / n,
                      'end': seg['start'] + (i + 1) * (seg['end'] - seg['start']) / n} for i, c in enumerate(chars)]
        for wi, w in enumerate(words):
            # ASR can extend the last word across a long silent pause. Its midpoint
            # may be deleted even though the spoken beginning is retained.
            overlaps=[(min(w['end'],m['source_end'])-max(w['start'],m['source_start']),m) for m in mapping]
            if not overlaps:continue
            length,m=max(overlaps,key=lambda x:x[0])
            point = w['start']==w['end']
            if point:
                m=next((r for r in mapping if r['source_start']<=w['start']<r['source_end']),None)
                if m is None and mapping and w['start']==mapping[-1]['source_end'] and mapping[-1]['source_end']==p['edl'][-1]['end']:
                    m=mapping[-1]
            if length>0 or (point and m):
                result.append({'text': w.get('word', w.get('text', '')), 'start': max(w['start'], m['source_start']) - m['source_start'] + m['start'],
                    'end': min(w['end'], m['source_end']) - m['source_start'] + m['start'], 'segment_id': seg['id'],
                    'word_id': f"{seg['id']}:{wi}", 'probability': w.get('probability'), 'estimated':estimated})
    return result

def build_captions(p):
    from caption_phrasing import groups, display_text, review_reason
    captions = []
    previous = {c['id']:c for c in p.get('captions',[])}
    imported = {s['id'] for s in p['transcript'] if s.get('subtitle_cue')}
    for group in groups(mapped_words(p), imported, previous.values()):
        cue = group[0]['segment_id'] in imported
        text = spoken(''.join(w['text'] for w in group) if cue else display_text(group)).strip()
        if not text:
            continue
        ids = [w['word_id'] for w in group]
        capid = 'cap_'+digest(ids)[:12]
        start, end = group[0]['start'], group[-1]['end']
        cap = {'id':capid, 'text':spoken(previous.get(capid,{}).get('text',text)), 'original_text':text,
               'word_ids':ids, 'start':round(start,3), 'end':round(end if cue else max(end,start+.1),3),
               **match_script(p,text)}
        reason = '' if cue else review_reason(group)
        if reason:
            cap['listen_reason'] = reason
        captions.append(cap)
    for i, c in enumerate(captions):
        if c['word_ids'][0].rsplit(':',1)[0] in imported:
            continue
        c['end'] = min(c['end'] + .08, captions[i + 1]['start'] if i + 1 < len(captions) else time_map(p['edl'])[-1]['end'])
    return captions

def scene_plan(p):
    scenes = []
    for pg in p['pages']:
        for tag in pg.get('tags', []):
            matches = [c for c in p['captions'] if c.get('page_id') == pg['id'] and (not tag.get('sentence_id') or c.get('sentence_id') == tag['sentence_id'])]
            if not matches:
                scenes.append({'id': 'scene_'+tag['id'], 'page_id': pg['id'], 'tag_id': tag['id'], 'title': tag.get('label', pg['title']),
                    'kind': tag['kind'], 'start': 0, 'end': 0, 'enabled': False, 'orphaned': True, 'asset_id': tag.get('asset_id', ''), 'note': '未找到已保留的对应语音，请手动定位'})
                continue
            scenes.append({'id': 'scene_'+tag['id'], 'page_id': pg['id'], 'tag_id': tag['id'], 'title': tag.get('label') or pg['title'],
                'kind': tag['kind'], 'start': matches[0]['start'], 'end': min(matches[-1]['end'], matches[0]['start'] + 7),
                'enabled': True, 'orphaned': False, 'asset_id': tag.get('asset_id', ''), 'note': tag.get('note', ''), 'steps': tag.get('steps', [])})
    if not scenes:
        for i, c in enumerate(p['captions'][::5]):
            scenes.append({'id': 'scene_'+c['id'], 'caption_id':c['id'], 'title': c['text'].strip('。，'), 'kind': 'title', 'start': c['start'],
                'end': c['end'], 'enabled': True, 'asset_id': '', 'note': '自动建议，可修改或关闭', 'steps': []})
    old_by_id={s['id']:s for s in p.get('scenes',[])}
    mapping=time_map(p['edl'])
    for scene in scenes:
        old=old_by_id.get(scene['id'])
        if old and not scene.get('orphaned'):
            for k in ('title','kind','steps','note','asset_id','fullscreen','enabled'):
                if k in old:scene[k]=old[k]
            if old.get('manual_timing'):
                a=forward_time(old.get('source_start'),mapping);b=forward_time(old.get('source_end'),mapping,end=True)
                scene.update(manual_timing=True,source_start=old.get('source_start'),source_end=old.get('source_end'))
                if a is None or b is None or b<=a:scene.update(enabled=False,orphaned=True,note='剪点变更后原锚点已被删除，请重新定位')
                else:scene.update(start=a,end=b)
    new_ids={s['id'] for s in scenes}
    for old in p.get('scenes',[]):
        if old['id'] in new_ids:continue
        scene=copy.deepcopy(old)
        a=forward_time(old.get('source_start'),mapping);b=forward_time(old.get('source_end'),mapping,end=True)
        if a is not None and b is not None and b>a and not old.get('tag_id') and not old.get('caption_id'):
            scene.update(start=a,end=b)
        else:scene.update(enabled=False,orphaned=True,note='原句或场景锚点不再匹配，请重新定位')
        scenes.append(scene)
    return scenes

VISUAL_SETTINGS = ('caption_only','caption_y','caption_size','overlay_y','overlay_height','protected_rect','accent','sfx')

def file_digest(path):
    value=hashlib.sha256()
    with Path(path).open('rb') as fh:
        for chunk in iter(lambda:fh.read(1024*1024),b''):value.update(chunk)
    return value.hexdigest()

def plan_hash(p):
    used={s.get('asset_id') for s in p['scenes'] if s.get('enabled') and s.get('asset_id')}
    assets=[{'id':a['id'],'content':file_digest(a['path']) if Path(a['path']).is_file() else 'missing:'+a['path']} for a in p['assets'] if a['id'] in used]
    return digest({'captions': p['captions'], 'scenes': p['scenes'], 'settings': {k:p['settings'].get(k) for k in VISUAL_SETTINGS},
                   'rough': p['rough'], 'assets': assets, 'edl': p['edl'], 'timeline': p.get('timeline',{})})

def validate_plan(p):
    if not p.get('rough'): raise ValueError('请先生成粗剪，或确认输入已经粗剪完成')
    duration = p['rough']['duration']; last = 0
    for c in p['captions']:
        if not c['text'].strip() or c['start'] < last - .001 or c['end'] <= c['start'] or c['end'] > duration + .05:
            raise ValueError('字幕有空文字、重叠或超出片长，请修正')
        last = c['end']
    for s in p['scenes']:
        if s.get('enabled') and (s['start'] < 0 or s['end'] <= s['start'] or s['end'] > duration + .05):
            raise ValueError('素材时间超出片长或起止顺序不正确')
    cfg = p['settings']
    if not .1 <= float(cfg['caption_y']) <= .95: raise ValueError('字幕位置应在画面 10%–95% 范围内')
    if not 0 <= float(cfg['overlay_y']) < .9 or not .08 <= float(cfg['overlay_height']) <= .5:
        raise ValueError('动画区域位置或高度超出范围')
    y0, y1 = cfg['overlay_y'], cfg['overlay_y'] + cfg['overlay_height']
    _, py, _, ph = cfg['protected_rect']
    active = [s for s in p['scenes'] if s.get('enabled') and s['kind'] != 'sfx']
    if any(not s.get('fullscreen') for s in active) and max(y0, py) < min(y1, py + ph):
        raise ValueError('动画区域与人物保护区重叠，请在精剪设置中调整位置')
    missing = [s for s in active if s['kind'] in ('product', 'sticker', 'demo') and not s.get('asset_id')]
    if missing: raise ValueError('有素材场景尚未绑定文件，请上传并绑定，或关闭该场景')
    ordered = sorted(active, key=lambda s: s['start'])
    if any(a['end'] > b['start'] + .001 for a,b in zip(ordered,ordered[1:])):
        raise ValueError('有两个画面事件重叠，请调整起止时间或关闭其中一个，避免素材互相遮挡')
    asset_ids = {a['id'] for a in p['assets']}
    if any(s.get('asset_id') and s['asset_id'] not in asset_ids for s in active):
        raise ValueError('有画面事件引用了已不存在的素材')
    if not .015 <= float(cfg['caption_size']) <= .1: raise ValueError('字幕字号应为画面高度的 1.5%–10%')
    if not all(isinstance(x,(float,int)) and 0<=x<=1 for x in cfg['protected_rect']):raise ValueError('人物保护区应使用 0–1 的比例')
    if y1>1:raise ValueError('动画区域超出画面')
    return True
