"""Loopback-only workbench server. Launch with python scripts/server.py."""
from __future__ import annotations
import argparse, json, mimetypes, os, re, secrets, shutil, sys, threading, urllib.parse, webbrowser
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from socketserver import TCPServer
from core import *
from jobs import Jobs,doctor
from ai_service import Manuscripts
from agent_tasks import AgentTasks
from codex_handoff import CodexHandoff
from runtime import configure_tool_path, data_lock, default_data_dir
from speech_live import LiveSpeech
import v2_api
import agent_api
import motion_package


class WorkbenchServer(ThreadingHTTPServer):
    request_queue_size = 64

    def server_bind(self):
        # The address is already a numeric loopback. HTTPServer's default
        # reverse hostname lookup can delay startup on a new network.
        TCPServer.server_bind(self)
        self.server_name, self.server_port = self.server_address

class Handler(BaseHTTPRequestHandler):
    server_version='TalkingHeadStudio/'+VERSION

    def log_message(self,fmt,*args):
        if '/api/jobs' not in str(args):super().log_message(fmt,*args)

    def valid_host(self):
        return self.headers.get('Host','') in (f'127.0.0.1:{self.server.server_port}',f'localhost:{self.server.server_port}')

    def respond(self,status,data):
        body=json.dumps(data,ensure_ascii=False).encode('utf-8');self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8');self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store');self.send_header('X-Content-Type-Options','nosniff');self.end_headers();self.wfile.write(body)

    def do_GET(self):
        if not self.valid_host():return self.respond(403,{'error':'仅允许本机访问'})
        url=urllib.parse.urlparse(self.path);path=url.path;query=urllib.parse.parse_qs(url.query)
        try:
            if path.startswith('/motion-download/'):
                name = path.removeprefix('/motion-download/')
                return self.send_file(motion_package.download(self.server.store.root, name), download=True)
            if path == '/api/motion/status':
                return self.respond(200, motion_package.status())
            if path.startswith('/api/agents/'):
                if self.headers.get('X-Studio-Token') != self.server.token:
                    return self.respond(403, {'error': '无效的本地会话'})
                return self.respond(200, agent_api.get(self.server, path, query))
            if path.startswith('/api/v2/'):return self.respond(200,v2_api.get(self.server,path,query))
            if path=='/prompter':
                p=self.server.store.load(query['id'][0]);p['start_page_id']=query.get('page',[''])[0];p['asset_urls']={a['id']:f"/asset/{p['id']}/{a['id']}" for a in p['assets']}
                body=(ROOT/'assets/workbench/prompter.html').read_text(encoding='utf-8').replace('__PROJECT__',json.dumps(p,ensure_ascii=False).replace('</','<\\/')).encode('utf-8')
                self.send_response(200);self.send_header('Content-Type','text/html; charset=utf-8');self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body);return
            if path=='/api/bootstrap':return self.respond(200,{'token':self.server.token,'projects':self.server.store.listing(),'doctor':doctor()})
            if path=='/api/instance':return self.respond(200,{'id':self.server.instance_id})
            if path=='/api/project':
                p = self.server.store.load(query['id'][0])
                from cue_review import summaries
                return self.respond(200, dict(p, rough_current=rough_current(p), cue_notes=summaries(p)))
            if path=='/api/jobs':
                with self.server.jobs.lock:result=[dict(j) for j in self.server.jobs.jobs.values() if j['project_id']==query.get('id',[''])[0]]
                return self.respond(200,result[-40:])
            if path.startswith('/draft-file/'):
                base=self.server.store.root/'manuscripts/uploads';target=(base/urllib.parse.unquote(path[len('/draft-file/'):])).resolve()
                if not target.is_relative_to(base.resolve()) or target.suffix.lower() not in ('.png','.jpg','.jpeg','.gif','.webp'):return self.respond(403,{'error':'不支持的稿件附件'})
                return self.send_file(target)
            if path.startswith('/file/'):
                _,_,pid,fid=path.split('/');p=self.server.store.load(pid);item=next(m for m in p['media'] if m['id']==fid)
                return self.send_file(Path(item['path']),download=query.get('download')==['1'])
            if path.startswith('/asset/'):
                _,_,pid,aid=path.split('/');p=self.server.store.load(pid);item=next(a for a in p['assets'] if a['id']==aid)
                return self.send_file(Path(item['path']))
            rel='index.html' if path=='/' else urllib.parse.unquote(path[1:])
            base=ROOT/'assets/workbench';target=(base/rel).resolve()
            if not target.is_relative_to(base.resolve()):return self.respond(403,{'error':'非法路径'})
            return self.send_file(target)
        except (ValueError,KeyError,StopIteration,FileNotFoundError) as e:self.respond(404,{'error':str(e) or '文件不存在'})
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass

    def do_POST(self):
        if not self.valid_host() or self.headers.get('X-Studio-Token')!=self.server.token:
            return self.respond(403,{'error':'无效的本地会话'})
        origin=self.headers.get('Origin')
        if origin and origin not in (f'http://127.0.0.1:{self.server.server_port}',f'http://localhost:{self.server.server_port}'):
            return self.respond(403,{'error':'跨站请求已拒绝'})
        with self.server.lifecycle:
            if self.server.stopping:
                return self.respond(409, {'error': '工作台正在停止。'})
            self.server.active_posts += 1
        try:
            return self.handle_post()
        finally:
            with self.server.lifecycle:
                self.server.active_posts -= 1

    def handle_post(self):
        try:
            if self.path == '/api/motion/export':
                return self.respond(200, motion_package.export(self.server.store.root, self.rfile, int(self.headers.get('Content-Length', 0))))
            if self.path.startswith('/api/upload?'):return self.upload()
            length=int(self.headers.get('Content-Length',0))
            if length>16*1024*1024:raise ValueError('请求过大')
            data=json.loads(self.rfile.read(length) or b'{}');store=self.server.store
            if self.path.startswith('/api/agents/'):
                return self.respond(200, agent_api.post(self.server, self.path, data))
            if self.path == '/api/shutdown':
                return self.shutdown_instance(data)
            if self.path.startswith('/api/v2/'):return self.respond(200,v2_api.post(self.server,self.path,data))
            if self.path=='/api/new':
                p=default_project(data.get('title','新的口播项目'));return self.respond(200,store.save(p,label='新建工程'))
            if self.path=='/api/save':
                p = store.edit(data['id'], data)
                return self.respond(200, dict(p, rough_current=rough_current(p)))
            if self.path=='/api/complete-task':
                with LOCK:
                    p=store.load(data['project_id']);task=next(t for t in p['tasks'] if t['id']==data['task_id'])
                    task.update(result=data['text'],status='draft_ready',completed=now());store.save(p,label='宿主 AI 返回改稿草案')
                return self.respond(200,{'status':'draft_ready','task_id':task['id']})
            if self.path=='/api/action':return self.respond(202,self.server.jobs.submit(data['project_id'],data['action'],data.get('args',{})))
            return self.respond(404,{'error':'未知接口'})
        except Conflict as e:self.respond(409,{'error':str(e)})
        except Exception as e:self.respond(400,{'error':str(e)})

    def shutdown_instance(self, data):
        server = self.server
        if data.get('id') != server.instance_id:
            return self.respond(409, {'error': '工作台实例已变化，请重试。'})
        with server.lifecycle, server.jobs.lock, server.manuscripts.lock:
            jobs = server.jobs.jobs.values()
            drafts = v2_api.get(server, '/api/v2/drafts', {})
            if (server.active_posts != 1 or server.agent_tasks.has_dispatches() or any(j['status'] in ('running', 'queued') for j in jobs)
                    or any(d['status'] == 'running' for d in drafts)):
                return self.respond(409, {'error': '工作台还有文件或任务正在处理，请完成后重试。'})
            server.stopping = True
        try:
            return self.respond(200, {'stopping': True})
        finally:
            threading.Thread(target=server.shutdown, daemon=True).start()

    def upload(self):
        params=urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query);pid=params.get('project',[''])[0]
        name=Path(params.get('name',['upload.bin'])[0]).name
        size=int(self.headers.get('Content-Length',0))
        if size<=0 or size>20*1024**3:raise ValueError('文件为空或超过 20 GB')
        folder=(self.server.store.folder(pid) if pid else self.server.store.root/'manuscripts')/'uploads';folder.mkdir(exist_ok=True)
        target=folder/(uid('upload')+'-'+re.sub(r'[<>:"/\\|?*]','_',name))
        try:
            with target.open('wb') as fh:
                left=size
                while left:
                    chunk=self.rfile.read(min(left,1024*1024))
                    if not chunk:raise ValueError('上传中断')
                    fh.write(chunk);left-=len(chunk)
        except Exception:
            target.unlink(missing_ok=True);raise
        return self.respond(200,{'path':str(target),'name':name,'url':'/draft-file/'+urllib.parse.quote(target.name) if not pid else ''})

    def send_file(self,path,download=False):
        if not path.is_file():return self.respond(404,{'error':'文件不存在；外部引用可能已移动'})
        total=path.stat().st_size;start,end=0,total-1;status=200
        rang=self.headers.get('Range','')
        if rang:
            match=re.fullmatch(r'bytes=(\d*)-(\d*)',rang)
            if not match:return self.respond(416,{'error':'无效的范围'})
            if match[1]:start=int(match[1]);end=min(total-1,int(match[2])) if match[2] else total-1
            else:start=max(0,total-int(match[2] or 0))
            if start> end or start>=total:return self.respond(416,{'error':'范围超出文件'})
            status=206
        self.send_response(status);self.send_header('Content-Type',mimetypes.guess_type(path.name)[0] or 'application/octet-stream')
        self.send_header('Accept-Ranges','bytes');self.send_header('Content-Length',str(max(0,end-start+1)));self.send_header('X-Content-Type-Options','nosniff')
        if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{total}')
        if download:self.send_header('Content-Disposition',"attachment; filename*=UTF-8''"+urllib.parse.quote(path.name))
        if path.suffix.lower() in ('.html','.svg') and not path.is_relative_to(ROOT/'assets/workbench'):
            self.send_header('Content-Security-Policy',"sandbox allow-scripts; default-src 'self' data: blob: 'unsafe-inline'")
        self.end_headers()
        try:
            with path.open('rb') as fh:
                fh.seek(start);remaining=end-start+1
                while remaining>0:
                    block=fh.read(min(1024*1024,remaining))
                    if not block:break
                    self.wfile.write(block);remaining-=len(block)
        except (BrokenPipeError,ConnectionResetError,ConnectionAbortedError):pass

def serve(data, port, open_page):
    store = Store(data)
    with data_lock(store.root), WorkbenchServer(('127.0.0.1', port), Handler) as server:
        demo = ROOT / 'assets/demo-project.json'
        if not store.listing() and demo.is_file():
            template = json.loads(demo.read_text(encoding='utf-8'))
            initial = default_project(template['title'])
            initial['pages'] = template['pages']
            initial['example'] = True
            store.save(initial, label='创建可编辑示例工程')
        server.store = store
        server.jobs = Jobs(store)
        server.token = secrets.token_urlsafe(32)
        server.instance_id = secrets.token_urlsafe(16)
        server.manuscripts = Manuscripts(store)
        server.agent_tasks = AgentTasks(store, CodexHandoff())
        server.speech = LiveSpeech(store.root)
        server.lifecycle = threading.Lock()
        server.stopping = False
        server.active_posts = 0
        url = f'http://127.0.0.1:{server.server_port}'
        record = store.root / 'server.json'
        write_json(record, {'url': url, 'pid': os.getpid(), 'started': now(),
                            'id': server.instance_id, 'code_root': str(ROOT)})
        print('Talking Head Studio ' + url, flush=True)
        try:
            if open_page:
                webbrowser.open(url)
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.jobs.pool.shutdown(wait=True)
            server.manuscripts.pool.shutdown(wait=True)
            server.agent_tasks.pool.shutdown(wait=True)
            record.unlink(missing_ok=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--data', type=Path, default=default_data_dir())
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--open', action='store_true')
    parser.add_argument('--doctor', action='store_true')
    args = parser.parse_args()
    configure_tool_path()
    if args.doctor:
        print(json.dumps(doctor(), ensure_ascii=False, indent=2))
        return
    try:
        serve(args.data.expanduser(), args.port, args.open)
    except (OSError, RuntimeError) as exc:
        parser.exit(1, f'{exc}\n')

if __name__=='__main__':main()
