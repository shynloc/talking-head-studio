import argparse,json,sys,time,urllib.request,zipfile,subprocess
from pathlib import Path

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--url',default='http://127.0.0.1:8765');ap.add_argument('--project',required=True);ap.add_argument('--out',required=True);args=ap.parse_args();out=Path(args.out).resolve();out.mkdir(parents=True,exist_ok=True)
    token=json.load(urllib.request.urlopen(args.url+'/api/bootstrap'))['token'];pid=args.project;checks=[]
    def api(path,data=None):
        req=urllib.request.Request(args.url+path,data=json.dumps(data).encode() if data else None,headers={'Content-Type':'application/json','X-Studio-Token':token})
        with urllib.request.urlopen(req,timeout=60) as r:return json.load(r)
    def action(name,params=None,project=None):
        target=project or pid;j=api('/api/action',{'project_id':target,'action':name,'args':params or {}})
        for _ in range(900):
            state=next(x for x in api('/api/jobs?id='+target) if x['id']==j['id'])
            if state['status']=='error':raise RuntimeError(name+': '+state['error'])
            if state['status']=='done':print(name,'PASS',flush=True);return state.get('result')
            time.sleep(.5)
        raise TimeoutError(name)
    new=api('/api/new',{'title':'文档与 AI 桥接验收'})['id']
    docx=out/'input.docx'
    with zipfile.ZipFile(docx,'w') as z:z.writestr('word/document.xml','<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>先连接设备。然后打开工作台。</w:t></w:r></w:p></w:body></w:document>')
    action('import_document',{'path':str(docx)},new);p=api('/api/project?id='+new);assert '先连接设备' in p['pages'][0]['text'];checks.append('HCS DOCX extraction')
    task=action('rewrite',{'instruction':'改成自然口播'},new);assert task['mode']=='host_task'
    api('/api/complete-task',{'project_id':new,'task_id':task['task_id'],'text':'先把设备连接好。接着打开口播工作台。'})
    action('apply_task',{'task_id':task['task_id']},new);assert '先把设备' in api('/api/project?id='+new)['pages'][0]['text'];checks.append('host-agent draft round trip')
    p=api('/api/project?id='+pid);src=next(m for m in p['media'] if m['id']==p['source_id'])
    action('relink_source',{'path':src['path']});action('approve_rough')
    video=action('add_asset',{'path':src['path'],'name':'全屏演示测试片'})
    p=api('/api/project?id='+pid);p['scenes']=[{'id':'scene_full','kind':'demo','title':'演示片段测试','start':.2,'end':2.6,'enabled':True,'fullscreen':True,'asset_id':video['id'],'steps':[],'note':'测试时显式允许全屏覆盖'}]
    api('/api/save',p);action('sample',{'start':0,'duration':3});action('approve_final');action('final');checks.append('fullscreen video B-roll with preserved output ratio')
    p=api('/api/project?id='+pid);page=p['pages'][0];page['type']='demo';page['media_id']=video['id'];api('/api/save',p)
    prompt=action('prompt_export');p=api('/api/project?id='+pid);zip_path=next(m['path'] for m in p['media'] if m['id']==prompt['id'])
    with zipfile.ZipFile(zip_path) as z:assert z.testzip() is None and any(n.startswith('media/') for n in z.namelist())
    checks.append('portable prompter video companion files')
    packaged=action('package');p=api('/api/project?id='+pid);path=next(m['path'] for m in p['media'] if m['id']==packaged['id']);imported=action('import_project',{'path':path})
    clone=api('/api/project?id='+imported['project_id']);assert clone['pages'][0]['text']==p['pages'][0]['text'];assert Path(clone['assets'][0]['path']).exists();checks.append('project ZIP round trip and assets')
    r=urllib.request.Request(args.url+'/file/'+pid+'/'+src['id'],headers={'Range':'bytes=0-31'})
    with urllib.request.urlopen(r) as response:assert response.status==206 and len(response.read())==32
    checks.append('video byte-range streaming')
    summary={'status':'PASS','checks':checks,'microphone_live_test':False,'cloud_llm_live_test':False}
    (out/'extended-results.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(summary))

if __name__=='__main__':main()
