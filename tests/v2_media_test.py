import sys,json,copy,argparse
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from core import *
import media,timeline,timeline_render,jianying_export,project_bundle
from PIL import Image,ImageDraw

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--out',required=True);a=ap.parse_args();out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=True);store=Store(out/'projects');checks=[]
 def report(n,s):print(round(n*100),s,flush=True)
 src=out/'source.mp4';media.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=360x640:r=12:d=4','-f','lavfi','-i','sine=frequency=330:sample_rate=48000:duration=4','-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest','-y',src])
 wav=out/'music.wav';media.run(['ffmpeg','-v','error','-f','lavfi','-i','sine=frequency=660:sample_rate=48000:duration=8','-y',wav])
 im=Image.new('RGBA',(200,200),(0,0,0,0));d=ImageDraw.Draw(im);d.rounded_rectangle((15,30,185,170),radius=30,fill='#f29849');d.ellipse((60,60,140,140),fill='#002fa7');png=out/'sticker.png';im.save(png)
 p=default_project('V2 多轨合成验收');p['pages']=[page('连接设备。开始演示。',title='演示')];store.save(p);media.import_media(store,p['id'],str(src));p=store.load(p['id']);p['edl']=[{'id':'test_cut','start':0,'end':4,'keep':True,'protected':False,'reason':'test fixture'}];p['transcript']=[{'id':'seg','start':0,'end':4,'text':'连接设备。开始演示。','words':[]}];store.save(p)
 media.render_rough(store,p['id'],report,skip=True);checks.append('rough render and mapping')
 p=store.load(p['id']);p['captions']=build_captions(p);p['assets']=[{'id':'sticker','name':'透明贴纸','path':str(png),'type':'png'},{'id':'music','name':'测试音乐','path':str(wav),'type':'wav'}];timeline.calibrate(p)
 tl=p['timeline'];tl['clips'].append({'id':'overlay-a','track':'sticker','kind':'sticker','name':'透明贴纸','start':.3,'duration':2.2,'asset_id':'sticker','x':.04,'y':.04,'width':.22,'height':.15,'enabled':True,'anchor':'absolute'})
 tl['clips'].append({'id':'overlay-b','track':'title','kind':'flow','name':'连接流程','steps':['设备','电脑'],'start':.4,'duration':2.1,'asset_id':'','x':.3,'y':.04,'width':.65,'height':.19,'enabled':True,'anchor':'absolute'})
 tl['clips'].append({'id':'music-1','track':'music','name':'背景乐','start':0,'duration':4,'asset_id':'music','volume':.08,'fade':.2,'enabled':True,'anchor':'absolute'})
 store.save(p);sample=timeline_render.render(store,p['id'],report,0,3);assert Path(sample['path']).exists();checks.append('concurrent transparent sticker and flow animation, captions, music')
 p=store.load(p['id']);p['approvals']['timeline']={'hash':timeline_render.signature(p),'actor':'isolated_test_fixture'};store.save(p);final=timeline_render.render(store,p['id'],report,final=True);info=media.probe(final['path']);assert (info['width'],info['height'])==(360,640);assert abs(info['duration']-4)<.13;checks.append('full timeline output keeps ratio and duration')
 media.run(['ffmpeg','-v','error','-ss','1','-i',final['path'],'-frames:v','1','-y',out/'multi-track-frame.png']);checks.append('full decode and representative frame extracted')
 p=store.load(p['id']);p['timeline']['clips'][-1]['volume']=.12;store.save(p)
 try:timeline_render.render(store,p['id'],report,final=True);raise AssertionError('approval must invalidate')
 except ValueError as e:assert '确认' in str(e)
 checks.append('timeline change invalidates final approval')
 gift=media.gif_factory(store,p['id'],'sticker','重点','pulse',report);assert Path(gift['path']).suffix=='.gif';checks.append('GIF Factory actual export')
 p=store.load(p['id']);p['timeline']['clips'].append({'id':'extra-main','track':'main','name':'插入展示','duration':1,'start':4,'asset_id':'sticker','anchor':'absolute'});store.save(p);extra=timeline_render.render(store,p['id'],report,3,2);assert abs(media.probe(extra['path'])['duration']-2)<.13;checks.append('main-track extra image insert renders without blank gap')
 item=jianying_export.export(store,p['id'],report);assert Path(item['path']).is_file();checks.append('Jianying native draft generated, editor compatibility separate')
 document=json.loads((Path(sample['path']).parent/'timeline.json').read_text(encoding='utf-8'));assert document['engine'].startswith('HCS frame-styles');checks.append('embedded HCS drives transparent animation')
 original=store.load(p['id']);archive=project_bundle.export_bundle(store,original,report,include_source=True)
 destination=Store(out/'另一台电脑')
 for local_media in (src,png,wav):local_media.replace(out/('旧位置-'+local_media.name))
 migrated=destination.load(project_bundle.import_bundle(destination,archive['path'])['project_id'])
 assert migrated['timeline']==original['timeline'] and migrated['captions']==original['captions'] and not migrated['approvals']
 assert Path(source(migrated)['path']).is_relative_to(destination.folder(migrated['id']))
 sample_moved=timeline_render.render(destination,migrated['id'],report,0,3)
 props=media.probe(sample_moved['path']);assert (props['width'],props['height'])==(360,640) and abs(props['duration']-3)<.12 and props['audio']
 checks.append('portable ZIP opens and renders from a separate directory after the original files move')
 (out/'results.json').write_text(json.dumps({'status':'PASS','checks':checks,'project_id':p['id'],'final':final['path'],'sample':sample['path'],'jianying':item['path']},ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps({'status':'PASS','checks':len(checks),'project':p['id']}))
if __name__=='__main__':main()
