"""Small loopback API extensions, sharing the server's origin/token checks."""
import json, copy
from pathlib import Path
from core import *
from ai_service import balanced_pages
import timeline

def get(server,path,q):
    if path=='/api/v2/status':return {'ai':server.manuscripts.config(),'speech':server.speech.status(),'version':VERSION}
    if path=='/api/v2/finish':
        from timeline_render import review_state
        return review_state(server.store.load(q['id'][0]))
    if path=='/api/v2/draft':return server.manuscripts.get(q['id'][0])
    if path=='/api/v2/drafts':
        project_id=q.get('project_id',[None])[0]
        drafts=[]
        for f in sorted(server.manuscripts.root.glob('draft_*.json'),key=lambda p:p.stat().st_mtime,reverse=True):
            draft=json.loads(f.read_text(encoding='utf-8'))
            if project_id is None or draft.get('project_id')==project_id:
                drafts.append({k:draft.get(k) for k in ('id','status','title')} if 'summary' in q else draft)
        return drafts
    raise ValueError('未知 V2 接口')

def post(server,path,d):
    ms=server.manuscripts;store=server.store
    if path=='/api/v2/caption-review':
        from caption_review import apply
        return apply(store,d['id'],d)
    if path=='/api/v2/preview-edit':
        from preview_edits import edit
        return edit(store,d['id'],d)
    if path=='/api/v2/note-decision':
        from cue_review import decide
        return decide(store, d['id'], d)
    if path=='/api/v2/settings':return ms.configure(d)
    if path=='/api/v2/draft':return ms.save(d)
    if path=='/api/v2/ai':return ms.start(d)
    if path=='/api/v2/complete':
        with ms.lock:
            draft=ms.get(d['id'])
            if draft.get('status')!='pending_host':raise ValueError('稿件不在等待宿主处理状态')
            return ms.accept_result(draft,d['result'])
    if path=='/api/v2/adopt':return ms.apply(d)
    if path=='/api/v2/page-preview':
        text = d.get('text', '')
        if not isinstance(text,str) or len(text)>120000: raise ValueError('稿件最多支持 12 万字')
        return [page['text'] for page in balanced_pages(text)] if text.strip() else []
    if path=='/api/v2/create':
        pid=d.get('project_id')
        with ms.lock,LOCK:
            draft=ms.get(d['id'])
            if not pid and draft.get('created_project_id'):
                return store.load(draft['created_project_id'])
            p=store.load(pid) if pid else default_project(draft.get('title') or '新的口播项目')
            if pid and p['version']!=d.get('version'):raise Conflict('工程已更新，请重新打开导入面板后重试')
            if draft.get('kind')=='paginate' and draft.get('status') in ('review','adopted') and draft.get('pages'):
                if draft.get('input_hash')!=digest(draft['text']):raise ValueError('原稿已变化，请重新分析')
                pages=copy.deepcopy(draft['pages']);engine='AI 语义分析'
            else:pages=balanced_pages(draft['text']);engine='基础规则排页'
            if d.get('append'):
                for pg in pages:
                    pg['id']=uid('page');ids={s['id']:uid('sent') for s in pg.get('sentences',[])}
                    for s in pg.get('sentences',[]):s['id']=ids[s['id']]
                    for tag in pg.get('tags',[]):
                        tag['id']=uid('tag')
                        if tag.get('sentence_id') in ids:tag['sentence_id']=ids[tag['sentence_id']]
            p['pages']=(p['pages']+pages) if d.get('append') else pages
            p['source_text']=draft['text'];p['manuscript_id']=draft['id'];p['pagination_engine']=engine;p['approvals']={}
            if not d.get('append'):p['timeline']={'mode':'planned','clips':[],'tracks':{}}
            timeline.validate(p);store.save(p,label='稿件创建 / 更新项目')
            if not draft.get('project_id'):
                draft.update(project_id=p['id'],created_project_id=p['id']);write_json(ms.file(draft['id']),draft)
            return p
    if path=='/api/v2/align':
        with LOCK:
            p=store.load(d['id'])
            if not p.get('rough'):raise ValueError('请先完成粗剪或确认已粗剪')
            if p['version']!=d['version']:raise Conflict('项目已变化，请重载后校准')
            retain = bool(p['captions'] and p.get('migration', {}).get('edl_hash') == edl_digest(p['edl']))
            timeline.calibrate(p, preserve_captions=retain)
            timeline.validate(p);return store.save(p,label='时间线校准为实际录制')
    if path=='/api/v2/speech/start':return server.speech.start()
    if path=='/api/v2/speech/audio':return server.speech.audio(d)
    if path=='/api/v2/speech/stop':return server.speech.stop(d['id'])
    if path=='/api/v2/extract':
        import media
        return {'text':media.extract_document(d['path'])}
    raise ValueError('未知 V2 接口')
