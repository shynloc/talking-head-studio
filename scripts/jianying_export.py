"""Optional native draft generation; target-editor verification is reported separately."""
import json, shutil, zipfile
from pathlib import Path
from core import uid, source, write_json
import timeline, media

def export(store,pid,report):
    try:import pyJianYingDraft as draft
    except ImportError:raise ValueError('剪映适配器未安装，请运行 python -m pip install pyJianYingDraft==0.3.1')
    p=store.load(pid);tl=timeline.validate_output(p);meta=source(p);w,h=int(meta.get('width') or 1280),int(meta.get('height') or 720)
    work=store.folder(pid)/'exports'/uid('jianying');work.mkdir(parents=True);name='口播工作台-'+p['id'][-6:];folder=work/name
    script=draft.DraftFolder(str(work)).create_draft(name,w,h,round(meta.get('fps') or 25));assets={a['id']:a for a in p['assets']};files={m['id']:m for m in p['media']};copied={};warnings=[];refs={}
    def asset(path):
        path=Path(path)
        if str(path) not in copied:
            out=folder/'materials'/(str(len(copied))+'-'+path.name);out.parent.mkdir(exist_ok=True);shutil.copy2(path,out);copied[str(path)]=out
        return str(copied[str(path)])
    def track(kind,id):
        key=(kind,id)
        if key not in refs:refs[key]=script.append_track(draft.TrackSpec(kind,name=id))
        return refs[key]
    report(.1,'生成本地剪映草稿与素材清单')
    # Separate tracks per overlapping event preserve temporal placement in the native format.
    for c in sorted(tl['clips'],key=lambda c:(0 if c['track']=='main' else 1,c['start'])):
        if c.get('enabled') is False or tl['tracks'].get(c['track'],{}).get('muted'):continue
        if c.get('orphaned'):raise ValueError(c['name']+' 需要重新关联')
        path=assets.get(c.get('asset_id'),files.get(c.get('source_id'),{})).get('path');tr=draft.trange(round(c['start']*1e6),round(c['duration']*1e6))
        if c['track'] in ('music','sfx'):
            if not path:raise ValueError(c['name']+' 缺少音频素材')
            seg=draft.AudioSegment(asset(path),tr,source_timerange=draft.trange(round(c.get('source_in',0)*1e6),tr.duration),volume=c.get('volume',.15 if c['track']=='music' else 1));script.add_segment(seg,track(draft.TrackType.audio,c['id']));continue
        if path:
            clip=None
            if c['track']!='main' and not c.get('fullscreen'):
                x,y,cw,ch=[float(c.get(k,v)) for k,v in [('x',.06),('y',.04),('width',.35),('height',.2)]]
                clip=draft.ClipSettings(scale_x=cw,scale_y=ch,transform_x=(x+cw/2-.5)*2,transform_y=(.5-y-ch/2)*2)
            image=Path(path).suffix.lower() in ('.png','.jpg','.jpeg','.webp')
            if Path(path).suffix.lower() in ('.gif','.svg'):
                warnings.append(c['name']+'：GIF/SVG 请在剪映中检查动画与透明度')
            seg=draft.VideoSegment(asset(path),tr,source_timerange=None if image else draft.trange(round(c.get('source_in',0)*1e6),tr.duration),volume=c.get('volume',1 if c['track']=='main' else 0),clip_settings=clip)
            script.add_segment(seg,track(draft.TrackType.video,'主画面' if c['track']=='main' else c['id']))
        else:
            text=c['name']
            if c['track']=='main':
                pg=next((x for x in p['pages'] if x['id']==c.get('page_id')),{});text+='\n'+pg.get('text','待制作素材');warnings.append(c['name']+'：录制前文字占位')
            if c.get('kind')=='flow':text+='\n'+' → '.join(c.get('steps',[]));warnings.append(c['name']+'：流程动画降级为可编辑文字')
            seg=draft.TextSegment(text,tr,style=draft.TextStyle(size=7,color=(0,.18,.65),auto_wrapping=True),clip_settings=draft.ClipSettings(transform_y=.6 if c['track']!='main' else 0));script.add_segment(seg,track(draft.TrackType.text,c['id']))
    from timeline_render import caption_map
    for i,c in enumerate([] if tl['tracks'].get('caption',{}).get('muted') else caption_map(p)):
        tr=draft.trange(round(c['start']*1e6),round((c['end']-c['start'])*1e6));seg=draft.TextSegment(c['text'],tr,style=draft.TextStyle(size=6,color=(1,1,1),auto_wrapping=True),clip_settings=draft.ClipSettings(transform_y=-.66));script.add_segment(seg,track(draft.TrackType.text,'口播字幕'))
    script.save();meta_path=folder/'draft_meta_info.json';data=json.loads(meta_path.read_text(encoding='utf-8'));data.update(draft_name=name,draft_fold_path=str(folder),draft_root_path=str(work));write_json(meta_path,data)
    write_json(folder/'studio-export-report.json',{'generator':'pyJianYingDraft 0.3.1','native_editor_verified':False,'warnings':warnings,'source_project_id':pid,'note':'打开兼容性取决于剪映版本；首次使用请先检查轨道和素材，工作台保留完整源工程。'})
    (folder/'重新关联路径.py').write_text('''from pathlib import Path
import json
root=Path(__file__).resolve().parent
for name in ('draft_content.json','draft_meta_info.json'):
 p=root/name
 d=json.loads(p.read_text(encoding='utf-8'))
 def walk(x):
  if isinstance(x,dict):
   for k,v in x.items():
    if isinstance(v,str) and k in ('path','material_name'):
     candidate=root/'materials'/Path(v.replace('\\\\','/')).name
     if candidate.exists():x[k]=str(candidate)
    else:walk(v)
  elif isinstance(x,list):
   for v in x:walk(v)
 walk(d)
 if name=='draft_meta_info.json':d.update(draft_fold_path=str(root),draft_root_path=str(root.parent))
 p.write_text(json.dumps(d,ensure_ascii=False),encoding='utf-8')
print('素材路径已更新')
''',encoding='utf-8')
    out=work/'剪映工程-实验性.zip'
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for f in folder.rglob('*'):
            if f.is_file():z.write(f,f.relative_to(work))
    item=store.register(pid,out,'deliverable');item['message']='剪映草稿已生成；目标版本打开兼容性请先验证。';return item
