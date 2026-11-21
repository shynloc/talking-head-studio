from __future__ import annotations
import concurrent.futures, copy, importlib.util, json, os, re, shutil, threading, urllib.request, zipfile
from pathlib import Path
from core import *
import media

def doctor():
    tools={x:shutil.which(x) for x in ('ffmpeg','ffprobe','node')}
    modules={x:bool(importlib.util.find_spec(x)) for x in ('whisper','torch','playwright','PIL','numpy','pypdf','pptx')}
    cache=Path(os.environ.get('XDG_CACHE_HOME',str(Path.home()/'.cache')))/'whisper'
    return {'version':VERSION,'tools':tools,'modules':modules,'models':[p.stem for p in cache.glob('*.pt')],
        'llm_configured':bool(os.environ.get('STUDIO_LLM_URL') and os.environ.get('STUDIO_LLM_MODEL')),
        'vendors': {
            'html-creator-studio': all((ROOT / 'vendor/html-creator-studio' / file).is_file()
                                       for file in ('scripts/extract_resume.py', 'shared/frame-styles.mjs')),
            'gif-factory': (ROOT / 'vendor/gif-factory/scripts/export_pack.py').is_file(),
        },
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
        if action in ('timeline_sample','timeline_final'):
            import timeline_render
            return timeline_render.render(store,pid,report,args.get('start',0),args.get('duration',10),action=='timeline_final')
        if action == 'confirm_timeline_final':
            import timeline_render
            with LOCK:
                p = store.load(pid)
                state = timeline_render.review_state(p)
                sample = state.get('sample') or {}
                if state['state'] != 'ready' or not sample or sample['id'] != args.get('sample_id') or state['hash'] != args.get('hash'):
                    raise ValueError('当前样片已变化，请重新试看并确认。')
                p['approvals']['timeline'] = {'hash': state['hash'], 'sample_id': sample['id'], 'at': now(), 'actor': 'user'}
                store.save(p, label='用户确认当前样片并导出成片')
            return timeline_render.render(store, pid, report, final=True)
        if action=='approve_timeline':
            import timeline_render
            sig=timeline_render.signature(p)
            if not any(e['kind']=='timeline_sample' and e['hash']==sig for e in p['exports']):raise ValueError('请先生成当前时间线样片')
            p['approvals']['timeline']={'hash':sig,'at':now(),'actor':'user'};store.save(p,label='用户确认时间线样片');return {'ok':True}
        if action=='jianying_export':
            import jianying_export
            return jianying_export.export(store,pid,report)
        if action=='import_media':
            return media.import_media(store,pid,args['path'])
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
        if action=='transcribe':
            return media.transcribe(store,pid,report,args.get('model',p['settings']['model']),bool(args.get('allow_download')))
        if action=='import_transcript':
            path=Path(args['path']);text=path.read_text(encoding='utf-8-sig')
            if path.suffix.lower()=='.json':
                raw=json.loads(text);rows=raw.get('segments',[]) if isinstance(raw,dict) else raw
            else:
                rows=[]
                pattern=r'(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})\s*-->\s*(\d{1,2}):(\d{2}):(\d{2})[,.](\d{3})[^\n]*\n(.*?)(?=\n\s*\n|\Z)'
                for match in re.finditer(pattern,text,re.S):
                    values=[int(v) for v in match.groups()[:8]]
                    a=values[0]*3600+values[1]*60+values[2]+values[3]/1000
                    b=values[4]*3600+values[5]*60+values[6]+values[7]/1000
                    rows.append({'start':a,'end':b,'text':match[9].strip(),'words':[]})
            if not rows:raise ValueError('未读到有效字幕；支持 Whisper JSON、SRT、带完整时间的 VTT')
            duration=source(p).get('duration',float('inf'));segments=[]
            for s in rows:
                if not 0<=float(s['start'])<float(s['end'])<=duration+.1:raise ValueError('字幕时间超出当前原片')
                segments.append({'id':uid('seg'),'start':float(s['start']),'end':float(s['end']),'text':str(s['text']),'words':s.get('words',[])})
            p['transcript']=segments;p['approvals'].pop('final',None);store.save(p,label='导入已有字幕时间轴');return {'segments':len(segments)}
        if action=='proxy':return media.make_proxy(store,pid,report)
        if action=='inspect_frames':return media.inspect_frames(store,pid,report)
        if action=='analyze_cuts':
            work=folder/'analysis'/uid('cuts');work.mkdir(parents=True)
            result=media.rough_candidates(p,work,report);store.patch(pid,result,'粗剪候选分析');return {'cuts':len(result['edl']),'repeats':len(result['repeat_suggestions'])}
        if action=='render_rough':return media.render_rough(store,pid,report)
        if action=='skip_rough':return media.render_rough(store,pid,report,skip=True)
        if action=='approve_rough':
            if not p['rough'] or p['rough']['edl_hash']!=digest(p['edl']):raise ValueError('请先输出当前剪辑清单对应的粗剪')
            p['approvals']['rough']={'at':now(),'hash':digest(p['rough'])};store.save(p,label='用户确认粗剪');return {'ok':True}
        if action=='plan':
            if not p['rough'] or not p['approvals'].get('rough'):raise ValueError('请先确认粗剪，或选择已粗剪输入')
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
            path=Path(args['path']).resolve()
            if not path.is_file() or path.suffix.lower() not in ('.png','.jpg','.jpeg','.webp','.gif','.svg','.mp4','.mov','.webm','.wav','.mp3','.m4a','.flac','.ogg'):
                raise ValueError('请导入图片、GIF 或视频素材')
            item={'id':uid('asset'),'name':args.get('name') or path.stem,'path':str(path),'type':path.suffix[1:],
                'source':args.get('source','用户提供'),'approved':False}
            p['assets'].append(item);store.save(p,label='导入素材');store.register(pid,path,'asset');return item
        if action=='gif':return media.gif_factory(store,pid,args['asset_id'],args.get('text','重点'),args.get('motion','pulse'),report)
        if action=='prompt_export':
            work=folder/'exports'/uid('prompt');work.mkdir(parents=True)
            out=media.export_prompt(p,work);store.register(pid,out,'deliverable')
            archive=work/'口播提词器.zip'
            with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED) as z:
                for file in work.rglob('*'):
                    if file.is_file() and file!=archive:z.write(file,file.relative_to(work).as_posix())
            return store.register(pid,archive,'deliverable')
        if action=='package':return self.package(p,report)
        if action=='restore':
            version=int(args['version']);rev=folder/'revisions'/f'{version:06}.json'
            if not rev.is_file():raise ValueError('没有这个历史版本')
            old=json.loads(rev.read_text(encoding='utf-8'));old['approvals']={};old['version']=p['version']
            store.save(old,p['version'],label=f'恢复版本 {version}');return {'ok':True}
        if action=='import_project':
            return self.import_package(args['path'])
        raise ValueError('未知任务：'+action)

    def package(self,p,report):
        report(.1,'打包可编辑工程、素材和最近输出')
        folder=self.store.folder(p['id']);out=folder/'exports'/f"studio-project-{p['version']}.zip";out.parent.mkdir(exist_ok=True)
        snapshot=copy.deepcopy(p);snapshot['approvals']={};copied={}
        with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
            for asset in snapshot['assets']:
                path=Path(asset['path']);target='assets/'+asset['id']+path.suffix
                z.write(path,target);copied[str(path)]=target;asset['path']=target
            # Original videos stay external; generated previews are optional and excluded to keep projects portable.
            for m in snapshot['media']:
                if m['kind']=='source':m['external']=True
                elif m['path'] in copied:m['path']=copied[m['path']]
                else:m['external']=True
            if snapshot.get('rough'):snapshot['rough']['external']=True
            z.writestr('project.json',json.dumps(snapshot,ensure_ascii=False,indent=2))
            z.writestr('说明.txt','工程包含稿件、页面、字幕、时间映射和素材。原视频及大型渲染文件采用外部引用，换电脑后需重新指定源视频。')
            latest=next((m for m in reversed(p['media']) if m['kind']=='final'),None)
            if latest:
                parent=Path(latest['path']).parent
                for item in parent.rglob('*'):
                    if item.is_file() and item.suffix.lower() not in ('.mp4','.mov','.wav','.log'):
                        z.write(item,'render-source/'+str(item.relative_to(parent)).replace('\\','/'))
        return self.store.register(p['id'],out,'deliverable')

    def import_package(self,path):
        with zipfile.ZipFile(path) as z:
            raw=json.loads(z.read('project.json'))
            if raw.get('schema_version') not in (1,2):raise ValueError('不支持的工程版本')
            old_id=raw['id'];raw['id']=uid('project');raw['version']=0;raw['approvals']={};raw['history']=[]
            folder=self.store.folder(raw['id']);folder.mkdir()
            for info in z.infolist():
                dest=(folder/info.filename).resolve()
                if not dest.is_relative_to(folder.resolve()):raise ValueError('压缩包含非法路径')
                if info.file_size>2*1024**3:raise ValueError('单文件过大')
                if info.filename.startswith('assets/') and not info.is_dir():
                    dest.parent.mkdir(parents=True,exist_ok=True);dest.write_bytes(z.read(info))
            for a in raw['assets']:
                target=(folder/a['path']).resolve()
                if not target.is_relative_to(folder.resolve()) or not target.is_file():raise ValueError('工程素材路径不合法或缺失')
                a['path']=str(target)
            for m in raw['media']:
                if not m.get('external'):m['path']=str((folder/m['path']).resolve())
            self.store.save(raw,label='导入工程');return {'project_id':raw['id'],'original_id':old_id}
