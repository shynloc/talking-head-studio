from __future__ import annotations
import concurrent.futures, importlib.util, json, os, re, shutil, threading, urllib.request, zipfile
from pathlib import Path
from core import *
from agent_hosts import HOSTS
import materials
import media
import project_bundle

def doctor():
    tools={x:shutil.which(x) for x in ('ffmpeg','ffprobe','node')}
    modules={x:bool(importlib.util.find_spec(x)) for x in ('whisper','torch','playwright','PIL','numpy','pypdf','pptx')}
    cache=Path(os.environ.get('XDG_CACHE_HOME',str(Path.home()/'.cache')))/'whisper'
    return {'version':VERSION,'agent_hosts':HOSTS,'tools':tools,'modules':modules,'models':[p.stem for p in cache.glob('*.pt')],
        'llm_configured':bool(os.environ.get('STUDIO_LLM_URL') and os.environ.get('STUDIO_LLM_MODEL')),
        'components': materials.components(),
        'vendors': {key:spec['available'] for key,spec in materials.components().items()},
        'speech_follow':'Local streaming ASR with selected browser microphone; run setup_speech.py for models',
        'data_directory':'Local project directory; source footage is referenced, not bundled by default'}

class Jobs:
    def __init__(self,store):
        self.store=store;self.pool=concurrent.futures.ThreadPoolExecutor(max_workers=1);self.jobs={};self.lock=threading.Lock()
        self.logdir=store.root/'jobs';self.logdir.mkdir(exist_ok=True)
        for file in self.logdir.glob('*.json'):
            try:
                task=json.loads(file.read_text(encoding='utf-8'))
                if task['status'] in ('queued','running'):
                    task.update(status='interrupted',message='服务已重启。保留工程，可重新提交任务。');write_json(file,task)
                self.jobs[task['id']]=task
            except (ValueError,OSError): pass

    def submit(self,pid,action,args):
        self.store.load(pid)
        task={'id':uid('job'),'project_id':pid,'action':action,'status':'queued','progress':0,'message':'已排队','created':now()}
        with self.lock:
            if any(j['project_id']==pid and j['status'] in ('running','queued') for j in self.jobs.values()):
                raise ValueError('该工程已有任务进行中，请等待完成后再提交')
            self.jobs[task['id']]=task;write_json(self.logdir/(task['id']+'.json'),task)
        self.pool.submit(self.execute,task,args)
        return task

    def execute(self,task,args):
        def report(progress,message):
            with self.lock:
                task.update(progress=progress,message=message);write_json(self.logdir/(task['id']+'.json'),task)
        try:
            task['status']='running';report(.02,'正在准备')
            result=self.action(task['project_id'],task['action'],args,report)
            task.update(status='done',result=result);report(1,'已完成')
        except Exception as exc:
            task.update(status='error',error=str(exc));report(task['progress'],str(exc))

    def action(self,pid,action,args,report):
        store=self.store;p=store.load(pid);folder=store.folder(pid)
        if action == 'caption_proof':
            from caption_review import proof
            return proof(self, pid, args, report)
        if action == 'first_preview':
            from guided_preview import prepare
            return prepare(self, pid, args, report)
        if action in ('prepare_follow','prepare_transcription','prepare_video_tools'):
            from local_tools import prepare
            return prepare(action,store.root,report)
        if action in ('timeline_sample','timeline_final'):
            import timeline_render
            return timeline_render.render(store,pid,report,args.get('start',0),args.get('duration',10),action=='timeline_final')
        if action == 'confirm_timeline_final':
            import timeline_render
            with LOCK:
                p = store.load(pid)
                state = timeline_render.require_sample(p, args.get('sample_id'), args.get('hash'))
                p['approvals']['timeline'] = {'hash': state['hash'], 'sample_id': state['sample']['id'], 'at': now(), 'actor': 'user'}
                store.save(p, label='用户确认当前样片并导出成片')
            from caption_review import export_reviewed_copy
            reviewed = export_reviewed_copy(store,pid,state,report)
            return reviewed or timeline_render.render(store, pid, report, final=True)
        if action in ('editor_package', 'chatcut_package'):
            import editor_delivery
            target = 'chatcut' if action == 'chatcut_package' else 'portable'
            return editor_delivery.package(store, pid, args, report, target)
        if action == 'jianying_reviewed_export':
            import jianying_export
            return jianying_export.export_reviewed(store, pid, args, report)
        if action=='approve_timeline':
            import timeline_render
            sig=timeline_render.signature(p)
            if not any(e['kind']=='timeline_sample' and e['hash']==sig for e in p['exports']):raise ValueError('请先生成当前时间线样片')
            p['approvals']['timeline']={'hash':sig,'at':now(),'actor':'user'};store.save(p,label='用户确认时间线样片');return {'ok':True}
        if action=='jianying_export':
            import jianying_export
            return jianying_export.export(store,pid,report)
        if action=='note_preview':
            from cue_review import preview
            return preview(store,pid,args,report)
        if action=='import_media':
            item = media.import_media(store,pid,args['path'],subtitle_path=args.get('subtitle_path'))
            mode = args.get('use_as')
            if mode in ('ready','captions') and item.get('video'):
                media.render_rough(store,pid,report,skip=True)
                project = store.load(pid)
                if bool(project['settings'].get('caption_only')) != (mode == 'captions'):
                    project['settings']['caption_only'] = mode == 'captions'
                    store.save(project,label='选择字幕与画面模式')
                return dict(item, ready_for_captions=True)
            return item
        if action=='relink_source':
            original=source(p);path=Path(args['path']).resolve()
            if not original:raise ValueError('工程尚无原片，请先导入')
            meta=media.probe(path)
            if abs(meta['duration']-original['duration'])>.08 or (meta['width'],meta['height'])!=(original['width'],original['height']):
                raise ValueError('新文件的时长或画幅与原片不符，不能直接复用剪点；请使用导入新视频')
            original['path']=str(path);original['name']=path.name;original['external']=False
            if p.get('rough'):
                if p['rough']['media_id']==original['id']:p['rough']['path']=str(path)
                elif not Path(p['rough']['path']).is_file():p['previous_rough']=p['rough'];p['rough']=None
            p['approvals']={};store.save(p,label='重新关联原片，保留稿件和剪点');return {'ok':True}
        if action=='import_document':
            text=media.extract_document(args['path']);pages=script_pages(text,args.get('mode','original'))
            store.patch(pid,{'source_text':text,'pages':pages,'approvals':{}},'文档导入与排页');return {'pages':len(pages)}
        if action=='script':
            text=args.get('text') or ''.join(s['text'] for s in p['transcript'])
            if not text.strip(): raise ValueError('请先输入文字、导入文档或完成音视频转写')
            pages=script_pages(text,args.get('mode','original'))
            store.patch(pid,{'source_text':text,'pages':pages,'script_mode':args.get('mode','original'),'approvals':{}},'生成口播页面')
            return {'pages':len(pages),'engine':'保留原文／规则口语化'}
        if action=='rewrite':
            text=args.get('text') or '\n'.join(pg['text'] for pg in p['pages'])
            endpoint=os.environ.get('STUDIO_LLM_URL');model=os.environ.get('STUDIO_LLM_MODEL')
            task={'id':uid('task'),'kind':'rewrite','status':'pending','created':now(),'source':text,
                'instruction':args.get('instruction','保留事实，改写为自然易讲的中文口播。不要虚构经历、数据或引用。'),
                'target_seconds':p['settings']['target_seconds'],'project_version':p['version']}
            if not endpoint or not model:
                p['tasks'].append(task);store.save(p,label='生成宿主 AI 改稿任务');write_json(folder/'agent-tasks'/f"{task['id']}.json",task)
                return {'mode':'host_task','message':'已生成任务，请在 Codex 中说：处理当前口播工程的待办改稿。原稿保留不变。','task_id':task['id']}
            if not args.get('allow_network'): raise ValueError('调用已配置的模型服务会发送本次稿件，请确认允许联网改稿')
            if not endpoint.startswith(('https://','http://127.0.0.1:','http://localhost:')):
                raise ValueError('模型地址应使用 HTTPS 或本机服务')
            report(.2,'调用已配置的模型服务进行改稿')
            payload={'model':model,'messages':[{'role':'system','content':'你是中文口播编辑。只返回口播稿正文，保留事实。'},
                {'role':'user','content':task['instruction']+f"\n目标时长约 {task['target_seconds']} 秒。\n原稿：\n"+text}],'temperature':.5}
            headers={'Content-Type':'application/json'}
            if os.environ.get('STUDIO_LLM_KEY'):headers['Authorization']='Bearer '+os.environ['STUDIO_LLM_KEY']
            req=urllib.request.Request(endpoint,data=json.dumps(payload).encode(),headers=headers,method='POST')
            with urllib.request.urlopen(req,timeout=180) as response:result=json.load(response)
            output=result['choices'][0]['message']['content']
            task.update(status='draft_ready',result=output);p=store.load(pid);p['tasks'].append(task);store.save(p,label='AI 改稿草案待采用')
            return {'task_id':task['id'],'mode':'draft_ready'}
        if action=='apply_task':
            t=next(t for t in p['tasks'] if t['id']==args['task_id'])
            if not t.get('result'):raise ValueError('任务尚无返回稿件')
            p['pages']=script_pages(t['result']);t['status']='applied';p['approvals'].pop('script',None);store.save(p,label='采用改稿草案');return {'ok':True}
        if action == 'prepare_rough':
            self.action(pid, 'analyze_cuts', {}, lambda n, msg: report(n * .45, msg))
            return self.action(pid, 'render_rough', {}, lambda n, msg: report(.45 + n * .55, msg))
        if action in ('auto_captions', 'captions_from_file'):
            first = 'transcribe' if action == 'auto_captions' else 'import_transcript'
            self.action(pid, first, args, lambda n, msg: report(n * .85, msg))
            return self.action(pid, 'plan', {}, lambda n, msg: report(.85 + n * .15, msg))
        if action=='transcribe':
            return media.transcribe(store,pid,report,args.get('model',p['settings']['model']),bool(args.get('allow_download')))
        if action=='import_transcript':
            from subtitle_input import read_segments
            segments = read_segments(args['path'], source(p).get('duration',float('inf')))
            p['transcript']=segments
            for output in ('final','timeline'):
                p['approvals'].pop(output,None)
            store.save(p,label='导入已有字幕时间轴')
            return {'segments':len(segments)}
        if action=='proxy':return media.make_proxy(store,pid,report)
        if action=='inspect_frames':return media.inspect_frames(store,pid,report)
        if action=='analyze_cuts':
            work=folder/'analysis'/uid('cuts');work.mkdir(parents=True)
            result=media.rough_candidates(p,work,report);store.patch(pid,result,'粗剪候选分析');return {'cuts':len(result['edl']),'repeats':len(result['repeat_suggestions'])}
        if action=='render_rough':return media.render_rough(store,pid,report)
        if action=='skip_rough':return media.render_rough(store,pid,report,skip=True)
        if action=='approve_rough':
            if not rough_current(p):raise ValueError('请先输出当前剪辑清单对应的粗剪')
            p['approvals']['rough']={'at':now(),'hash':digest(p['rough'])};store.save(p,label='用户确认粗剪');return {'ok':True}
        if action=='plan':
            if not rough_current(p) or not p['approvals'].get('rough'):raise ValueError('请先确认粗剪，或选择已粗剪输入')
            if not p['transcript']:raise ValueError('请先转写视频，才能制作实际语音字幕')
            p['captions']=build_captions(p);p['scenes']=scene_plan(p);p['approvals'].pop('final',None)
            import timeline
            timeline.calibrate(p)
            # Replace generated suggestions by identity; keep the last edited legacy
            # duplicate and leave unrelated user-created clips alone.
            ids={sc['id'] for sc in p['scenes'] if not sc.get('tag_id')}
            old={c['id']:c for c in p['timeline']['clips'] if c['id'] in ids or c.get('generated_by')=='scene_plan'}
            p['timeline']['clips']=[c for c in p['timeline']['clips'] if c['id'] not in old]
            from timeline_render import caption_map
            mapped={c['id']:c for c in reversed(caption_map(p))}
            for sc in p['scenes']:
                if not sc.get('tag_id'):
                    cap=mapped.get(sc.get('caption_id'))
                    defaults={'name':sc['title'],'kind':sc['kind'],'start':cap['start'] if cap else sc['start'],'duration':max(.1,(cap['end']-cap['start']) if cap else sc['end']-sc['start']),'enabled':sc.get('enabled',True),'asset_id':sc.get('asset_id','')}
                    clip=old.get(sc['id'])
                    if clip:
                        baseline=clip.get('generated_defaults',{})
                        for key,value in defaults.items():
                            if key in baseline and clip.get(key)==baseline[key]:clip[key]=value
                    else:clip={'id':sc['id'],'track':'title','anchor':'absolute',**defaults}
                    clip.update(generated_by='scene_plan',generated_defaults=defaults);p['timeline']['clips'].append(clip)
            timeline.validate(p)
            store.save(p,label='生成字幕与精剪建议');return {'captions':len(p['captions']),'scenes':len(p['scenes'])}
        if action=='sample':return media.render_final(store,pid,report,True,args.get('start',0),args.get('duration',10))
        if action=='approve_final':
            validate_plan(p);signature=plan_hash(p)
            if not any(e['kind']=='sample' and e['hash']==signature for e in p['exports']):raise ValueError('请先生成当前方案的代表样片，再确认')
            p['approvals']['final']={'at':now(),'hash':signature,'scope':'当前字幕、动画方案和样片','actor':'user'}
            store.save(p,label='用户确认精剪方案与样片');return {'ok':True}
        if action=='final':return media.render_final(store,pid,report,False)
        if action=='add_asset':
            return materials.add(store,pid,args['path'],args.get('name'),args.get('source','用户提供'))
        if action=='gif':return media.gif_factory(store,pid,args['asset_id'],args.get('text','重点'),args.get('motion','pulse'),report)
        if action=='prompt_export':
            work=folder/'exports'/uid('prompt');work.mkdir(parents=True)
            out=media.export_prompt(p,work);store.register(pid,out,'deliverable')
            archive=work/'口播提词器.zip'
            with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
                for file in work.rglob('*'):
                    if file.is_file() and file!=archive:z.write(file,file.relative_to(work).as_posix())
            return store.register(pid,archive,'deliverable')
        if action=='package':
            return project_bundle.export_bundle(store, p, report, include_source=args.get('include_source') is True)
        if action=='restore':
            version=int(args['version']);rev=folder/'revisions'/f'{version:06}.json'
            if not rev.is_file():raise ValueError('没有这个历史版本')
            old=json.loads(rev.read_text(encoding='utf-8'));old['approvals']={};old['version']=p['version']
            store.save(old,p['version'],label=f'恢复版本 {version}');return {'ok':True}
        if action=='import_project':
            return project_bundle.import_bundle(store, args['path'])
        raise ValueError('未知任务：'+action)
