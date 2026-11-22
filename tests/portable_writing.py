"""Exercise the writing path and an offline prompter without optional video tools."""
import json
import platform
import sys
import subprocess
import tempfile
import time
from pathlib import Path
from urllib.request import Request, urlopen

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from launch import running_instance,stop_instance

with tempfile.TemporaryDirectory() as tmp:
    folder=Path(tmp)
    service=subprocess.Popen([sys.executable,'-X','utf8',str(Path(__file__).resolve().parents[1]/'scripts/server.py'),
                              '--data',str(folder),'--port','0'],stdout=subprocess.DEVNULL)
    for _ in range(100):
        record=running_instance(folder)
        if record:break
        if service.poll() is not None:raise RuntimeError('工作台启动失败')
        time.sleep(.1)
    if not record:
        service.terminate();service.wait();raise TimeoutError('工作台启动超时')
    url=record['url']
    try:
        token=json.load(urlopen(url+'/api/bootstrap'))['token']
        def post(path,payload):
            return json.load(urlopen(Request(url+path,json.dumps(payload).encode(),
                {'Content-Type':'application/json','X-Studio-Token':token}),timeout=30))
        draft=post('/api/v2/draft',{'title':'口播','text':'先读这一句。然后继续。'})
        project=post('/api/v2/create',{'id':draft['id']})
        assert '先读这一句。' in project['pages'][0]['text']
        task=post('/api/action',{'project_id':project['id'],'action':'prompt_export','args':{}})
        for i in range(120):
            jobs=json.load(urlopen(url+'/api/jobs?id='+project['id']))
            latest=next(j for j in jobs if j['id']==task['id'])
            if latest['status'] not in ('running','queued'):break
            time.sleep(.25)
        assert latest['status']=='done' and Path(latest['result']['path']).is_file(),latest
        print(platform.system(),platform.machine(),'manuscript and offline prompter PASS')
    finally:
        stop_instance(folder)
        service.wait(timeout=12)
