"""Host-agent bridge. Works with the running workbench API, never invents approvals."""
from agent_hosts import AGENTS
import argparse,json,os,urllib.request,time,sys
from pathlib import Path
from agent_client import AgentClient


def handoff_command(args):
    client = AgentClient(args.url, getattr(args, 'agent', 'codex'))
    if args.command == 'agent-motion-desk':
        return client.motion_desk(os.environ.get('CODEX_THREAD_ID', ''))
    if args.command == 'agent-deliver':
        from sample_tool import deliver
        return deliver(args)
    if args.command == 'agent-config':
        return {'mcpServers':{'talking-head-studio':{'command':sys.executable,
            'args':['-X','utf8',str(Path(__file__).with_name('agent_mcp.py').resolve()),'--agent',args.agent,'--url',args.url]}}}
    if args.command == 'agent-list':
        return client.list()
    if args.command == 'agent-claim':
        return client.claim(args.id)
    if args.command == 'agent-complete':
        return client.complete(args.id, args.receipt, Path(args.file).read_text(encoding='utf-8-sig'))
    return client.bind(args.project, os.environ.get('CODEX_THREAD_ID', ''), args.replace)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--url',default='http://127.0.0.1:8765')
    sub=p.add_subparsers(dest='command',required=True)
    sub.add_parser('status')
    new=sub.add_parser('new',help='新建已选择画面主次的工程');new.add_argument('title');new.add_argument('--composition',required=True,choices=('presenter','demo','mixed'))
    sub.add_parser('drafts')
    draft=sub.add_parser('draft');draft.add_argument('id')
    complete=sub.add_parser('complete-draft');complete.add_argument('id');complete.add_argument('--file',required=True)
    get=sub.add_parser('project');get.add_argument('id');get.add_argument('--out')
    action=sub.add_parser('action');action.add_argument('id');action.add_argument('name');action.add_argument('--args-file');action.add_argument('--wait',action='store_true')
    composition=sub.add_parser('composition',help='保存工程画面主次，沿用其他设置')
    composition.add_argument('id');composition.add_argument('mode',choices=('presenter','demo','mixed'))
    composition.add_argument('--presenter-style',choices=('window','green'),help='普通小窗或绿幕去背')
    segment=sub.add_parser('segment-composition',help='为指定页面或时间线画面设置主次')
    segment.add_argument('id')
    segment.add_argument('target',help='页面或画面片段的 ID')
    segment.add_argument('mode',choices=('presenter','demo','auto'),help='auto 恢复跟随整片')
    segment.add_argument('--suggest',action='store_true',help='保存 AI 的片段建议，用户指定优先')
    patch=sub.add_parser('edit');patch.add_argument('id');patch.add_argument('--file',required=True)
    tasks=sub.add_parser('tasks');tasks.add_argument('id')
    finish=sub.add_parser('complete-task');finish.add_argument('id');finish.add_argument('task');finish.add_argument('--text-file',required=True)
    sub.add_parser('agent-motion-desk')
    sub.add_parser('agent-config').add_argument('--agent', choices=tuple(AGENTS), required=True)
    sub.add_parser('agent-list').add_argument('--agent', choices=tuple(AGENTS), required=True)
    claim=sub.add_parser('agent-claim');claim.add_argument('id');claim.add_argument('--agent', choices=tuple(AGENTS), required=True)
    claim.add_argument('--ascii-json', action='store_true', help='输出 ASCII JSON，兼容旧版 PowerShell 管道')
    result=sub.add_parser('agent-complete');result.add_argument('id');result.add_argument('--agent', choices=tuple(AGENTS), required=True)
    result.add_argument('--receipt', required=True);result.add_argument('--file', required=True)
    delivery=sub.add_parser('agent-deliver');delivery.add_argument('task');delivery.add_argument('--agent',choices=('workbuddy','codex'),required=True)
    delivery.add_argument('--receipt',required=True);delivery.add_argument('--media',type=Path,required=True);delivery.add_argument('--source',type=Path,action='append',default=[])
    bind=sub.add_parser('agent-bind');bind.add_argument('project');bind.add_argument('--replace', action='store_true')
    args=p.parse_args()
    if args.command.startswith('agent-'):
        try:
            result=handoff_command(args)
        except urllib.error.HTTPError as exc:
            raise SystemExit(json.loads(exc.read()).get('error', str(exc))) from None
        except (OSError, ValueError) as exc:
            raise SystemExit(str(exc)) from None
        print(json.dumps(result,ensure_ascii=getattr(args,'ascii_json',False),indent=2))
        return
    token=''
    def req(path,data=None):
        request=urllib.request.Request(args.url+path,data=json.dumps(data,ensure_ascii=False).encode() if data is not None else None,
            headers={'Content-Type':'application/json',**({'X-Studio-Token':token} if token else {})})
        with urllib.request.urlopen(request,timeout=60) as response:return json.load(response)
    boot=req('/api/bootstrap');token=boot['token']
    if args.command=='status':result={k:v for k,v in boot.items() if k!='token'}
    elif args.command=='new':
        result=req('/api/new',{'title':args.title,'composition':args.composition})
    elif args.command=='drafts':result=req('/api/v2/drafts')
    elif args.command=='draft':result=req('/api/v2/draft?id='+args.id)
    elif args.command=='complete-draft':
        d=req('/api/v2/draft?id='+args.id);text=Path(args.file).read_text(encoding='utf-8');result=req('/api/v2/complete',{'id':args.id,'result':json.loads(text) if d['kind']=='paginate' else text})
    elif args.command=='project':
        result=req('/api/project?id='+args.id)
        if args.out:Path(args.out).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8');result={'saved':str(Path(args.out).resolve())}
    elif args.command=='tasks':
        project=req('/api/project?id='+args.id);result={'tasks':project['tasks'],'feedback':project['feedback']}
    elif args.command=='complete-task':
        result=req('/api/complete-task',{'project_id':args.id,'task_id':args.task,'text':Path(args.text_file).read_text(encoding='utf-8')})
    elif args.command=='composition':
        project=req('/api/project?id='+args.id)
        settings={**project['settings'], 'composition':args.mode}
        if args.presenter_style:
            settings['presenter_style']=args.presenter_style
        saved=req('/api/save',{'id':args.id,'version':project['version'],'settings':settings})
        result={'id':args.id,'composition':saved['settings']['composition'],'version':saved['version']}
    elif args.command=='segment-composition':
        project=req('/api/project?id='+args.id)
        if any(page['id']==args.target for page in project['pages']):
            if args.suggest:
                raise SystemExit('自动建议作用于具体画面片段，请选择其片段 ID。')
            settings=project['settings']
            overrides=settings.setdefault('page_compositions',{})
            patch={'settings':settings}
            field=args.target
        else:
            clip=next((c for c in project['timeline']['clips'] if c['id']==args.target and c['track'] in ('pip','sticker','title')),None)
            if clip is None:
                raise SystemExit('找不到指定的页面或画面片段。')
            overrides=clip
            field='suggested_composition' if args.suggest else 'composition'
            patch={'timeline':project['timeline']}
        if args.mode=='auto':
            overrides.pop(field,None)
        else:
            overrides[field]=args.mode
        saved=req('/api/save',{'id':args.id,'version':project['version'],**patch})
        result={'id':args.id,'target':args.target,'composition':args.mode,'version':saved['version']}
    elif args.command=='edit':
        current=req('/api/project?id='+args.id);patch=json.loads(Path(args.file).read_text(encoding='utf-8'))
        for k in ('title','pages','settings','edl','captions','scenes','feedback','recording_log','timeline'):
            if k in patch:current[k]=patch[k]
        result=req('/api/save',current)
    elif args.command=='action':
        if args.name in ('approve_rough','approve_final','approve_timeline','confirm_timeline_final'):
            raise SystemExit('请让用户在工作台确认，或使用已有明确确认的记录；此通用 CLI 不代替用户审批。')
        params=json.loads(Path(args.args_file).read_text(encoding='utf-8')) if args.args_file else {}
        result=req('/api/action',{'project_id':args.id,'action':args.name,'args':params})
        if args.wait:
            job_id=result['id']
            while result['status'] in ('running','queued'):
                time.sleep(1);result=next(j for j in req('/api/jobs?id='+args.id) if j['id']==job_id)
            if result['status']!='done':print(json.dumps(result,ensure_ascii=False));raise SystemExit(1)
    print(json.dumps(result,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
