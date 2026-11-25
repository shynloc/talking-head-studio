"""Optional native draft generation; target-editor verification is reported separately."""
import json, shutil, time, zipfile
from pathlib import Path
from core import uid, source, write_json
import timeline, media


def export_reviewed(store, pid, args, report):
    """Convert the approved editing materials into independently editable native tracks."""
    import editor_delivery
    import timeline_render

    p = store.load(pid)
    state = timeline_render.require_sample(p, args.get('sample_id'), args.get('hash'))
    try:
        import pyJianYingDraft as draft
    except ImportError:
        raise ValueError('当前工作台还没装剪映导出组件。请先按 README 安装组件，或下载剪辑素材包。') from None
    work = store.folder(pid) / 'exports' / uid('jianying')
    work.mkdir(parents=True)
    pack = work / 'source'
    name = '口播工作台-' + work.name[-8:]
    manifest = editor_delivery.build(p, state, pack, work / 'render', report)
    width, height, fps = (manifest[key] for key in ('width', 'height', 'fps'))
    folder = work / name
    script = draft.DraftFolder(str(work)).create_draft(name, width, height, max(1, round(fps)))
    materials = folder / 'materials'
    materials.mkdir()
    refs = {}

    def asset(clip):
        path = clip['path']
        if path not in refs:
            original = pack / path
            target = materials / f'{len(refs) + 1:03d}{original.suffix}'
            shutil.copy2(original, target)
            refs[path] = target
        return str(refs[path])

    def interval(start, duration):
        return draft.trange(round(start * 1e6), round((start + duration) * 1e6) - round(start * 1e6))

    def track(kind, label):
        return script.append_track(draft.TrackSpec(kind, name=label))

    main = track(draft.TrackType.video, '口播和演示')
    visuals = sorted((clip for clip in manifest['clips'] if clip['role'] == 'visual'), key=lambda c: c['layer'])
    for clip in [c for c in manifest['clips'] if c['role'] == 'main'] + visuals:
        path = asset(clip)
        when = interval(clip['start'], clip['duration'])
        visual = clip['role'] == 'visual'
        dest = track(draft.TrackType.video, clip['name'] + ' ' + clip['id'][-6:]) if visual else main
        image = Path(path).suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp')
        source_range = None if image else draft.trange(round(clip['source_in'] * 1e6), when.duration)
        segment = draft.VideoSegment(path, when, source_timerange=source_range, volume=clip['volume'])
        script.add_segment(segment, dest)

    for clip in manifest['clips']:
        if clip['role'] != 'audio':
            continue
        when = interval(clip['start'], clip['duration'])
        seg = draft.AudioSegment(asset(clip), when,
                                 source_timerange=draft.trange(round(clip['source_in'] * 1e6), when.duration),
                                 volume=clip['volume'])
        fade = round(min(clip['fade'], clip['duration'] / 2) * 1e6)
        if fade:
            seg.add_fade(fade, fade)
        script.add_segment(seg, track(draft.TrackType.audio, clip['name'] + ' ' + clip['id'][-6:]))

    captions = [] if p['timeline']['tracks'].get('caption', {}).get('muted') else timeline_render.caption_map(p)
    caption_tracks = []
    for caption in captions:
        for lane in caption_tracks:
            if lane['end'] <= caption['start']:
                break
        else:
            lane = {'track': track(draft.TrackType.text, f'口播字幕 {len(caption_tracks) + 1}')}
            caption_tracks.append(lane)
        lane['end'] = caption['end']
        position = draft.ClipSettings(transform_y=1 - 2 * p['settings']['caption_y'])
        style = draft.TextStyle(size=6, color=(1, 1, 1), align=1, auto_wrapping=True)
        seg = draft.TextSegment(caption['text'], interval(caption['start'], caption['end'] - caption['start']),
                                style=style, clip_settings=position)
        script.add_segment(seg, lane['track'])

    script.save()
    content_path = folder / 'draft_content.json'
    content = json.loads(content_path.read_text(encoding='utf-8'))
    content.setdefault('path', '')
    write_json(content_path, content)
    for filename in ('draft_info.json', 'template-2.tmp'):
        shutil.copy2(content_path, folder / filename)
    stamp = int(time.time())
    (folder / 'draft_settings').write_text(
        f'[General]\ndraft_create_time={stamp}\ndraft_last_edit_time={stamp}\n'
        'real_edit_keys=1\nreal_edit_seconds=0\n', encoding='utf-8')
    media.run(['ffmpeg', '-v', 'error', '-i', pack / '预览.mp4', '-frames:v', '1',
               '-vf', 'scale=-2:256', '-y', folder / 'draft_cover.jpg'])
    info = folder / 'draft_meta_info.json'
    data = json.loads(info.read_text(encoding='utf-8'))
    data.update(draft_name=name, draft_fold_path=str(folder), draft_root_path=str(work),
                draft_cover='draft_cover.jpg', tm_duration=content['duration'])
    write_json(info, data)
    shutil.copy2(pack / '预览.mp4', folder / '预览.mp4')
    shutil.copy2(pack / '字幕.srt', folder / '字幕.srt')
    write_json(folder / 'studio-export-report.json', {
        'generator': 'pyJianYingDraft 0.3.1', 'timeline_hash': state['hash'],
        'sample': manifest['sample'], 'native_editor_verified': False,
        'editable': ['主画面剪点', '字幕文字与时间', '动效片段的位置、大小和时长', '音频时间与音量'],
        'baked': ['动效内部文字和关键帧'],
    })
    (folder / '打开草稿.md').write_text(
        '# 用剪映专业版继续剪\n\n'
        '1. 打开剪映的草稿设置，查看「草稿位置」，然后退出剪映。\n'
        '2. 将整个口播工作台草稿文件夹解压到该位置。运行其中的「重新关联路径.py」更新素材路径。\n'
        '3. 重新打开剪映，找到该草稿并进入。先播放「预览.mp4」做对照。\n\n'
        '在剪映中可分别剪主画面，改字幕，移动或修剪动效，调整声音。'
        '动效里的文字、颜色和动作已渲染。剪映的字幕样式和背景乐自动避让需重新调整。\n',
        encoding='utf-8',
    )
    (folder / '重新关联路径.py').write_text(RELINK, encoding='utf-8')
    out = work / '剪映草稿.zip'
    report(.94, '将草稿和素材放进同一个下载包')
    with zipfile.ZipFile(out, 'w', zipfile.ZIP_STORED) as archive:
        for path in sorted(folder.rglob('*')):
            if path.is_file():
                archive.write(path, path.relative_to(work).as_posix())
    timeline_render.require_sample(store.load(pid), state['sample']['id'], state['hash'])
    item = store.register(pid, out, 'deliverable')
    item.update(sample_id=state['sample']['id'], timeline_hash=state['hash'])
    return item

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
        if p['settings'].get('caption_only') and c['track'] not in ('main','voice','caption'):continue
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
    (folder/'重新关联路径.py').write_text(RELINK,encoding='utf-8')
    out=work/'剪映工程-实验性.zip'
    with zipfile.ZipFile(out,'w',zipfile.ZIP_DEFLATED) as z:
        for f in folder.rglob('*'):
            if f.is_file():z.write(f,f.relative_to(work))
    item=store.register(pid,out,'deliverable');item['message']='剪映草稿已生成；目标版本打开兼容性请先验证。';return item


RELINK = '''from pathlib import Path
import json
root=Path(__file__).resolve().parent
for name in ('draft_content.json','draft_meta_info.json','draft_info.json','template-2.tmp'):
 p=root/name
 if not p.is_file():continue
 d=json.loads(p.read_text(encoding='utf-8'))
 def walk(x):
  if isinstance(x,dict):
   for k,v in x.items():
    if isinstance(v,str) and k in ('path','file_Path'):
     candidate=root/'materials'/Path(v.replace('\\\\','/')).name
     if candidate.exists():x[k]=str(candidate)
    else:walk(v)
  elif isinstance(x,list):
   for v in x:walk(v)
 walk(d)
 if name=='draft_meta_info.json':d.update(draft_fold_path=str(root),draft_root_path=str(root.parent))
 p.write_text(json.dumps(d,ensure_ascii=False),encoding='utf-8')
print('素材路径已更新')
'''
