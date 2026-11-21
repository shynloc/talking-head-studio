"""Run against an ISOLATED server only. All approvals are synthetic test-fixture actions."""
import argparse,json,sys,time,urllib.request,urllib.error,zipfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import media
from core import normalized
from PIL import Image

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--url',required=True);ap.add_argument('--out',required=True);ap.add_argument('--speech-one',required=True);ap.add_argument('--speech-two',required=True);ap.add_argument('--timed-fixture',action='store_true');ap.add_argument('--portable-out',type=Path);ap.add_argument('--skip-jianying',action='store_true');a=ap.parse_args()
 out=Path(a.out).resolve();out.mkdir(parents=True,exist_ok=True)
 boot=json.load(urllib.request.urlopen(a.url+'/api/bootstrap'));token=boot['token'];checks=[]
 def api(path,data=None):
  req=urllib.request.Request(a.url+path,data=json.dumps(data,ensure_ascii=False).encode() if data is not None else None,headers={'Content-Type':'application/json','X-Studio-Token':token})
  return json.load(urllib.request.urlopen(req,timeout=60))
 def record(label):checks.append(label);print(label,flush=True)
 def job(pid,action,args=None,expect_error=None):
  task=api('/api/action',{'project_id':pid,'action':action,'args':args or {}});deadline=time.monotonic()+600
  while time.monotonic()<deadline:
   j=next(j for j in api('/api/jobs?id='+pid) if j['id']==task['id'])
   if j['status'] in ('done','error'):
    if expect_error:assert j['status']=='error' and expect_error in j.get('error',''),j;return j
    assert j['status']=='done',j;return j['result']
   time.sleep(.3)
  raise TimeoutError(action)
 def get(pid):return api('/api/project?id='+pid)
 def save(p):return api('/api/save',p)
 # Synthetic recording with an intentional two-second gap.
 audio=out/'narration-with-pause.wav'
 media.run(['ffmpeg','-v','error','-i',a.speech_one,'-f','lavfi','-t','2','-i','anullsrc=r=24000:cl=mono','-i',a.speech_two,'-filter_complex','[0:a]aresample=24000,aformat=channel_layouts=mono[a];[2:a]aresample=24000,aformat=channel_layouts=mono[b];[a][1:a][b]concat=n=3:v=0:a=1[out]','-map','[out]','-y',audio])
 duration=media.probe(audio)['duration'];video=out/'recording.mp4'
 media.run(['ffmpeg','-v','error','-f','lavfi','-i',f'color=c=0x403020:s=360x640:r=12:d={duration}','-i',audio,'-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest','-y',video])
 image=out/'presentation.png';Image.new('RGB',(360,640),'#f19a50').save(image)
 p=api('/api/new',{'title':'三阶段回归 · 合成测试素材'});pid=p['id']
 original='连接电脑，然后录制。';polished='先把设备连接到电脑。然后检查声音，再开始录制。'
 d=api('/api/v2/draft',{'project_id':pid,'title':'测试稿件','text':original});api('/api/v2/ai',{'id':d['id'],'kind':'rewrite'})
 d=api('/api/v2/complete',{'id':d['id'],'result':polished});assert d['text']==original
 d=api('/api/v2/adopt',{'id':d['id']});assert d['text']==polished
 api('/api/v2/ai',{'id':d['id'],'kind':'paginate'});api('/api/v2/complete',{'id':d['id'],'result':{'pages':[{'title':'连接','sentences':[0]},{'title':'录制','sentences':[1]}]}})
 p=api('/api/v2/create',{'id':d['id'],'project_id':pid,'version':p['version']})
 assert len(p['pages'])==2 and ''.join(pg['text'] for pg in p['pages'])==polished
 asset=job(pid,'add_asset',{'path':str(image)});p=get(pid)
 p['timeline']['clips'].append({'id':'showcase','track':'main','name':'成品展示','duration':2,'start':0,'before_page_id':p['pages'][0]['id'],'asset_id':asset['id'],'enabled':True});save(p)
 job(pid,'prompt_export');record('stage 1: independent draft, host rewrite, adoption, semantic pages, 2s showcase, portable prompter')
 # Actual Whisper, actual silence analysis and an actual rough-cut render.
 job(pid,'import_media',{'path':str(video)})
 if a.timed_fixture:
  boundary=media.probe(a.speech_one)['duration']
  lines=[{'start':0,'end':boundary,'text':'先把设备连接到电脑。'},
         {'start':boundary+2,'end':duration,'text':'然后检查声音，再开始录制。'}]
  fixture=out/'known-timestamps.json';fixture.write_text(json.dumps(lines,ensure_ascii=False),encoding='utf-8')
  job(pid,'import_transcript',{'path':str(fixture)})
  asr={'text':''.join(line['text'] for line in lines),'segments':len(lines),'engine':'timed fixture'}
 else:
  asr=job(pid,'transcribe',{'model':'medium','allow_download':False});assert asr['segments']>0
 job(pid,'analyze_cuts');p=get(pid);assert any(not c['keep'] for c in p['edl']),p['edl']
 job(pid,'render_rough');job(pid,'approve_rough');p=get(pid);rough_duration=p['rough']['duration'];assert rough_duration<duration
 record('stage 2: '+('import timed captions' if a.timed_fixture else 'real local Whisper')+', pause candidates, rough render, isolated-fixture approval')
 job(pid,'plan');p=get(pid);ids=[c['id'] for c in p['timeline']['clips']];job(pid,'plan');p=get(pid)
 assert normalized(''.join(c['text'] for c in p['captions']))==normalized(asr['text']),p['captions']
 assert ids==[c['id'] for c in p['timeline']['clips']]
 assert p['timeline']['clips'][0]['id']=='showcase';assert abs(p['timeline']['duration']-(rough_duration+2))<.1
 p['title']+=' · 可继续保存';save(p);record('A1/A2: repeated planning preserves IDs, insert and ordinary saving')
 # Muted subtitles: actual output has zero ASS dialogue events and no subtitle pixels.
 p=get(pid);p['timeline']['tracks']['caption']={'muted':True}
 for c in p['timeline']['clips']:
  if c['track']!='main':c['enabled']=False
 save(p);hidden=job(pid,'timeline_sample',{'start':2,'duration':1})
 hidden_ass=Path(hidden['path']).parent/'captions.ass';assert 'Dialogue:' not in hidden_ass.read_text(encoding='utf-8-sig')
 p=get(pid);p['timeline']['tracks']['caption']['muted']=False;save(p);visible=job(pid,'timeline_sample',{'start':2,'duration':1})
 assert 'Dialogue:' in (Path(visible['path']).parent/'captions.ass').read_text(encoding='utf-8-sig')
 for name,item in [('hidden',hidden),('visible',visible)]:media.run(['ffmpeg','-v','error','-ss','0.5','-i',item['path'],'-frames:v','1','-y',out/(name+'.png')])
 assert (out/'hidden.png').read_bytes()!=(out/'visible.png').read_bytes();record('A5: hidden captions absent from ASS and rendered frame; re-enable restores them')
 # No false disabled-main export success.
 p=get(pid);p['timeline']['clips'][0]['enabled']=False;save(p);job(pid,'timeline_sample',expect_error='主轨不支持禁用')
 p=get(pid);p['timeline']['clips'][0]['enabled']=True;save(p);record('A7: disabled legacy main clip blocks output; re-enabling repairs project')
 # Multiple visual layers, GIF factory and music remain covered by v2_media_test.
 job(pid,'timeline_sample',{'start':0,'duration':p['timeline']['duration']});job(pid,'approve_timeline');final=job(pid,'timeline_final')
 info=media.probe(final['path']);assert (info['width'],info['height'])==(360,640);assert abs(info['duration']-(rough_duration+2))<.12
 package=job(pid,'package',{'include_source':True});job(pid,'import_project',{'path':package['path']})
 if a.portable_out:
  import shutil
  shutil.copy2(package['path'],a.portable_out)
 record('stage 3: full sample, fixture approval, full final, ratio preservation, project package roundtrip')
 # Replacement source cannot reuse old footage, even before manual recalibration.
 blue=out/'replacement-blue.mp4';media.run(['ffmpeg','-v','error','-f','lavfi','-i',f'color=c=blue:s=360x640:r=12:d={duration}','-i',audio,'-c:v','libx264','-pix_fmt','yuv420p','-c:a','aac','-shortest','-y',blue])
 old_transcript=get(pid)['transcript'];job(pid,'import_media',{'path':str(blue)});job(pid,'timeline_sample',expect_error='原片已更换');job(pid,'skip_rough')
 transcript=out/'known-transcript.json';transcript.write_text(json.dumps(old_transcript,ensure_ascii=False),encoding='utf-8');job(pid,'import_transcript',{'path':str(transcript)})
 p=get(pid);api('/api/v2/align',{'id':pid,'version':p['version']});p=get(pid);assert p['timeline']['clips'][0]['id']=='showcase'
 # No stale source ID; frame from the speech section must be blue.
 assert {c['source_id'] for c in p['timeline']['clips'] if c.get('source_id')}=={p['source_id']}
 p['timeline']['tracks']['caption']['muted']=True;save(p);new=job(pid,'timeline_sample',{'start':2,'duration':1})
 media.run(['ffmpeg','-v','error','-ss','0.5','-i',new['path'],'-frames:v','1','-y',out/'replacement.png'])
 rgb=Image.open(out/'replacement.png').convert('RGB').getpixel((180,320));assert rgb[2]>200 and rgb[0]<30 and rgb[1]<30,rgb
 record('A3 + already-cut branch: replacement blocked, skip rough, recalibrate, export new blue footage with showcase retained')
 # Render JY draft; application compatibility stays explicitly unverified.
 if not a.skip_jianying:
  jy=job(pid,'jianying_export');assert Path(jy['path']).is_file();record('experimental Jianying draft generated; native editor not verified')
 (out/'results.json').write_text(json.dumps({'status':'PASS','checks':checks,'project_id':pid,'transcription':asr,'raw_duration':duration,'rough_duration':rough_duration,'final':final['path'],'final_duration':info['duration'],'ratio':[info['width'],info['height']],'approvals':'isolated synthetic fixtures only','native_editor_verified':False},ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'status':'PASS','checks':len(checks),'final':final['path']},ensure_ascii=False),flush=True)
if __name__=='__main__':main()
