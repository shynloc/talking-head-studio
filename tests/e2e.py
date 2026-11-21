"""Exercise actual HTTP jobs and actual FFmpeg/Whisper/GIF/HCS export. Requires --video."""
import argparse,json,time,urllib.request,sys
from pathlib import Path
from PIL import Image,ImageDraw

def main():
    a=argparse.ArgumentParser();a.add_argument('--url',default='http://127.0.0.1:8765');a.add_argument('--video',required=True);a.add_argument('--out',required=True);args=a.parse_args()
    root=Path(args.out).resolve();root.mkdir(parents=True,exist_ok=True);results=[]
    token=json.load(urllib.request.urlopen(args.url+'/api/bootstrap'))['token']
    def api(path,data=None):
        req=urllib.request.Request(args.url+path,data=json.dumps(data).encode() if data else None,headers={'Content-Type':'application/json','X-Studio-Token':token})
        with urllib.request.urlopen(req,timeout=60) as response:return json.load(response)
    p=api('/api/new',{'title':'验收工程 · 数据线口播'});pid=p['id']
    def action(name,params=None):
        job=api('/api/action',{'project_id':pid,'action':name,'args':params or {}});started=time.time()
        while time.time()-started<900:
            js=api('/api/jobs?id='+pid);j=next(x for x in js if x['id']==job['id'])
            if j['status']=='error':raise RuntimeError(name+': '+j['error'])
            if j['status']=='done':
                results.append({'action':name,'status':'PASS','seconds':round(time.time()-started,2),'result':j.get('result')});print(name,'PASS',flush=True);return j.get('result')
            time.sleep(.6)
        raise TimeoutError(name)
    action('script',{'text':'然后准备一根能够传输数据的 Type-C 接口的数据线。开发板亮了，不代表电脑能识别。'})
    action('import_media',{'path':str(Path(args.video).resolve())})
    action('transcribe',{'model':'medium'})
    action('analyze_cuts');p=api('/api/project?id='+pid)
    assert any(not r['keep'] for r in p['edl']),'Expected actual silence candidates'
    action('render_rough');action('approve_rough');action('plan')
    p=api('/api/project?id='+pid);assert p['captions'];assert p['rough']['duration']<next(x for x in p['media'] if x['id']==p['source_id'])['duration']
    png=root/'test-badge.png';im=Image.new('RGBA',(512,512));d=ImageDraw.Draw(im);d.rounded_rectangle((105,100,407,400),radius=70,fill='#67ebc3',outline='#e2fff1',width=8);d.polygon([(215,190),(320,250),(215,310)],fill='#163d35');im.save(png)
    asset=action('add_asset',{'path':str(png),'name':'测试透明播放徽章','source':'original geometric QA fixture'})
    gif=action('gif',{'asset_id':asset['id'],'text':'连接成功','motion':'pulse'})
    p=api('/api/project?id='+pid);p['scenes']=[{'id':'scene_test','kind':'sticker','title':'先确认数据线','start':.2,'end':min(3.5,p['rough']['duration']), 'enabled':True,'asset_id':gif['id'],'steps':[],'note':'验收测试场景'}]
    p['settings']['overlay_height']=.23;p['settings']['protected_rect']=[.05,.30,.9,.45]
    api('/api/save',p);action('sample',{'duration':4});action('approve_final');final=action('final');action('prompt_export');action('package')
    p=api('/api/project?id='+pid);assert p['qa']['decode']=='PASS';assert p['qa']['width']==270 and p['qa']['height']==360
    final_path=Path(next(m['path'] for m in p['media'] if m['id']==final['id']));(root/'final-path.txt').write_text(str(final_path),encoding='utf-8')
    (root/'e2e-results.json').write_text(json.dumps({'project_id':pid,'results':results,'qa':p['qa']},ensure_ascii=False,indent=2),encoding='utf-8')
    print('E2E PASS',pid,final_path,flush=True)

if __name__=='__main__':main()
