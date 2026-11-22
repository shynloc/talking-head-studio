"""Build portable, individually editable media from a reviewed timeline."""
import csv
import shutil
import zipfile
from pathlib import Path

import materials
from core import file_digest, source, uid, write_json
import media
import timeline
import timeline_render as render


GUIDE = """# 在其他软件里继续剪

1. 解压整个文件夹。先播放「预览.mp4」，对照一下效果。
2. 把 media/主画面.mp4 放在最下面的视频轨，保留它的声音。想重剪主画面时，用 sources 里的原素材，参照「摆放时间.csv」里的起点和素材起点。
3. 导入「字幕.srt」，就能在支持 SRT 的软件里改文字和时间。字幕的字体、位置需要在剪辑软件里设置。
4. 把 media 中的 MOV 动画放到主画面上方。它们使用原视频画幅和透明背景，原样放置时无需缩放或挪动。把声音文件放到音频轨。
5. 按「摆放时间.csv」对齐每个片段。音量栏为倍率，1 代表原音量。层级数字越大，画面越靠上。

动画可以移动、缩放和裁短。动画里的文字、颜色和关键帧已经渲染在片段中，要改这些内容请回工作台。
原素材一起保存。自动压低背景乐、字幕样式需要在目标软件中重设。
「时间线.json」供支持自动组装或 Agent 的工具读取。只导入整个 MP4 会把画面和字幕合在一个片段里。
"""

CHATCUT_GUIDE = """# 用 ChatCut 继续剪

在当前 Agent 对话中粘贴「交给 ChatCut.txt」的内容。需要安装并启动 ChatCut 桌面版，并连接当前 Agent。
如果 Agent 不能使用 ChatCut 的本地工具，可以按「打开素材包.md」在编辑器里手动摆放素材。
"""


def package(store, pid, args, report, target='portable'):
    project = store.load(pid)
    state = render.require_sample(project, args.get('sample_id'), args.get('hash'))
    work = store.folder(pid) / 'exports' / uid(target)
    work.mkdir(parents=True)
    root = work / '口播剪辑素材'
    build(project, state, root, work / 'render', report)

    if target == 'chatcut':
        (root / 'ChatCut使用说明.md').write_text(CHATCUT_GUIDE, encoding='utf-8')
        instruction = (
            '请用 ChatCut 桌面版的本地工具继续这个口播项目。读取同目录的「时间线.json」和「打开素材包.md」。\n'
            '创建独立项目。用清单里的画幅，帧率可用 24、25、30、50、60；遇到其他值时选最接近的值并告诉我。'
            '按所用帧率对齐时间线的起止两端，再相减得到片段长度。导入清单引用的本机素材，跳过云端转写。\n'
            '用 main 的原素材逐段组装主画面及原声，保留素材截取点、顺序和音量。'
            '按 layer 从小到大将 visual 的透明 MOV 放到上方，各占一轨，使用整个画布的尺寸及位置。'
            '用 audio 记录放独立声音并设置音量和淡入淡出。用「字幕.srt」导入可编辑字幕（无字幕时跳过）。'
            '先对照「预览.mp4」检查时间、透明度和字幕。样片可能只是项目的一小段，按 sample.start 对照。\n'
            '保存后告诉我 ChatCut 项目名和 ID，以及需要补设的字幕样式或背景乐避让。'
            '暂留在可编辑的本机项目，等我选择是否导出。若本地工具不可用，请在待办说明原因并保留素材包。'
        )
        (root / '交给 ChatCut.txt').write_text(instruction, encoding='utf-8')
    report(.94, '整理预览、字幕和可以继续编辑的素材')
    archive = work / ('ChatCut 剪辑素材.zip' if target == 'chatcut' else '通用剪辑素材.zip')
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_STORED) as bundle:
        for path in sorted(root.rglob('*')):
            if path.is_file():
                bundle.write(path, path.relative_to(work).as_posix())
    render.require_sample(store.load(pid), state['sample']['id'], state['hash'])
    item = store.register(pid, archive, 'deliverable')
    item.update(sample_id=state['sample']['id'], timeline_hash=state['hash'])
    if target == 'chatcut':
        item['instruction'] = f'请读取本机文件「{root / "交给 ChatCut.txt"}」并执行。'
    return item


def build(project, state, root, work, report):
    """Create the same intermediate tracks and placement data for every editor."""
    root.mkdir(parents=True)
    work.mkdir(parents=True)
    for folder in ('media', 'sources'):
        (root / folder).mkdir()
    tl = timeline.validate_output(project)
    original = source(project)
    width, height = original['width'], original['height']
    fps = original.get('fps') or 25
    duration = state['duration']
    files = {item['id']: item for item in project['media'] + project['assets']}
    sample = files[state['sample']['id']]
    shutil.copy2(sample['path'], root / '预览.mp4')
    base = render.render_base(project, tl, work, width, height, fps, 0, duration, report)
    shutil.copy2(base, root / 'media' / '主画面.mp4')

    copied = {}

    def copy_source(item_id):
        if not item_id:
            return None
        item = files[item_id]
        path = Path(item['path'])
        if not path.is_file():
            raise ValueError(f'缺少素材「{item["name"]}」，请重新关联后导出。')
        if item_id not in copied:
            name = f'sources/{len(copied) + 1:03d}{path.suffix.lower()}'
            shutil.copy2(path, root / name)
            copied[item_id] = name
        return copied[item_id]

    def placement(clip, path, role, **fields):
        return {
            'id': clip['id'], 'name': clip['name'], 'role': role, 'track': clip['track'],
            'path': path, 'start': clip['start'], 'duration': clip['duration'],
            'source_in': clip.get('source_in', 0), **fields,
        }

    scenes, audio = render.layers(project, tl, 0, duration)
    if any(clip['start'] + clip['duration'] > duration + .05 for clip in scenes + audio):
        raise ValueError('辅助素材超出主画面末尾，请调整长度。')
    placements = []
    for clip in tl['clips']:
        if clip['track'] == 'main':
            path = copy_source(clip.get('asset_id') or clip.get('source_id'))
            volume = 0 if tl['tracks'].get('voice', {}).get('muted') else clip.get('volume', 1)
            placements.append(placement(clip, path, 'main', volume=volume))
    for index, clip in enumerate(scenes, 1):
        stage = work / f'visual-{index:03d}'
        stage.mkdir()
        overlay_project = {**project, 'v2_overlay': True, 'scenes': [clip]}
        media.create_overlay(overlay_project, stage, width, height, fps)
        progress = .14 + .65 * (index - 1) / len(scenes)

        def layer_report(local, message):
            report(progress + .65 * local / len(scenes), f'制作「{clip["name"]}」的透明素材 · {message}')

        take = media.render_overlay(stage, width, height, fps, clip['start'], clip['duration'], layer_report)
        path = f'media/动画-{index:03d}.mov'
        media.run(['ffmpeg', '-v', 'error', '-i', take, '-an', '-c:v', 'prores_ks', '-profile:v', '4444',
                   '-pix_fmt', 'yuva444p10le', '-y', root / path], stage / 'prores.log')
        placed = placement(clip, path, 'visual', layer=clip['layer'], kind=clip['kind'],
                           original=copy_source(clip.get('asset_id')), volume=0)
        placed['component']='html-creator-studio'
        placed['component_version']=materials.components()['html-creator-studio']['version']
        placed['alpha_capable']=True
        placed['source_in'] = 0
        placements.append(placed)
    for clip in audio:
        path = copy_source(clip['asset_id'])
        volume = clip.get('volume', .15 if clip['track'] == 'music' else 1)
        placements.append(placement(clip, path, 'audio', volume=volume, fade=clip.get('fade', .2)))

    captions = [] if tl['tracks'].get('caption', {}).get('muted') else render.caption_map(project)
    media.subtitles({**project, 'captions': captions}, root, width, height)
    (root / 'captions.srt').rename(root / '字幕.srt')
    (root / 'captions.ass').rename(root / '字幕参考.ass')
    with (root / '摆放时间.csv').open('w', encoding='utf-8-sig', newline='') as handle:
        writer = csv.writer(handle)
        writer.writerow(('名称', '轨道', '文件', '起点（秒）', '时长（秒）', '素材起点（秒）', '层级', '音量倍率'))
        for clip in placements:
            # Prevent editors such as Excel from treating creator-entered text as a formula.
            name = clip['name']
            if name.lstrip().startswith(('=', '-', '+', '@')) or name.startswith(('\t', '\r', '\n')):
                name = "'" + name
            writer.writerow((name, clip['track'], clip['path'], clip['start'], clip['duration'],
                             clip['source_in'], clip.get('layer', ''), clip['volume']))
    manifest = {
        'version': 1, 'project': project['title'], 'timeline_hash': state['hash'],
        'width': width, 'height': height, 'fps': fps, 'duration': duration, 'clips': placements,
        'assets': [{**{key:item.get(key) for key in ('id','type','name','source','source_asset_id','component','component_version','width','height','duration','alpha_capable')},
                    'path':copied[item['id']]} for item in map(materials.portable,(asset for asset in project['assets'] if asset['id'] in copied))],
        'base': 'media/主画面.mp4', 'subtitles': '字幕.srt',
        'caption_settings': {key: project['settings'][key] for key in ('caption_y', 'caption_size')},
        'sample': {'path': '预览.mp4', 'start': state['sample']['start'],
                   'duration': state['sample']['duration'], 'sha256': file_digest(root / '预览.mp4')},
    }
    write_json(root / '时间线.json', manifest)
    (root / '打开素材包.md').write_text(GUIDE, encoding='utf-8')
    return manifest
