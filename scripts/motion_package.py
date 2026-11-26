"""Turn reviewed browser canvas frames into a portable overlay pack, entirely on loopback."""
import json
import re
import shutil
import struct
import subprocess
import tempfile
import uuid
import zipfile
from pathlib import Path

from runtime import refresh_installed_tools

FPS = 25
SIZE = (960, 360)
MAX_BYTES = 512 * 1024 * 1024
MAX_HEADER = 32 * 1024 * 1024
GUIDE = """解压整个素材包。把「透明动画」里的 MOV 拖到剪辑软件中，放在人物视频上方的轨道。
在素材对应的口播原句处对齐起点，再根据人物和字幕的位置移动、缩放。
MOV 是带 Alpha 的 Apple ProRes 4444，无声，960 × 360，25 fps。序号与原句对照表一致。
想多停一会儿，可用同名透明 PNG 定格。回到「只做口播素材」，选择「打开已有搭配」，导入「素材搭配.json」可以修改文字、图片、动作和时长，再次导出。
"""


def status():
    refresh_installed_tools()
    return {'ready': bool(shutil.which('ffmpeg')), 'fps': FPS, 'size': SIZE}


def download(data, name):
    if not re.fullmatch('[0-9a-f]{32}', name):
        raise ValueError('没有找到这个素材包。')
    return data / 'motion-packs' / name / '口播透明素材包.zip'


class Packet:
    def __init__(self, stream, size):
        if not 0 < size <= MAX_BYTES:
            raise ValueError('素材包为空或超过 512 MB，请分批导出。')
        self.stream = stream
        self.remaining = size

    def read(self, count):
        if count > self.remaining:
            raise ValueError('素材帧不完整，请重新导出。')
        raw = self.stream.read(count)
        if len(raw) != count:
            raise ValueError('素材上传中断，请重新导出。')
        self.remaining -= count
        return raw

    def block(self, limit):
        size = int.from_bytes(self.read(4), 'big')
        if not 0 < size <= limit:
            raise ValueError('素材数据长度异常。')
        return self.read(size)


def validate(manifest):
    if not isinstance(manifest, dict) or manifest.get('format') != 'talking-head-motion/1':
        raise ValueError('无法识别的素材搭配。')
    items = manifest.get('items')
    if not isinstance(items, list) or not 1 <= len(items) <= 64:
        raise ValueError('每包可导出 1 至 64 款已选动画。')
    for item in items:
        if not isinstance(item, dict) or not isinstance(item.get('quote'), str) or not item['quote'].strip():
            raise ValueError('每款素材都需要对应的口播原句。')
        if not isinstance(item.get('title'), str) or not isinstance(item.get('ids'), list) or not item['ids']:
            raise ValueError('请为每款素材选好效果。')
        seconds = item.get('seconds')
        if type(seconds) is not int or not 1 <= seconds <= 12:
            raise ValueError('片段时长应为 1 到 12 秒。')
        if type(item.get('poster')) is not int or not 0 <= item['poster'] < seconds * FPS:
            raise ValueError('请重新查看定格帧。')
    return items


def encode(packet, item, folder, archive, stem):
    count = item['seconds'] * FPS
    sequence, movie = folder / 'frames.bin', folder / 'overlay.mov'
    with sequence.open('wb') as frames:
        for index in range(count):
            png = packet.block(2 * 1024 * 1024)
            if (len(png) < 45 or png[:8] != b'\x89PNG\r\n\x1a\n' or png[12:16] != b'IHDR'
                    or struct.unpack('>II', png[16:24]) != SIZE or png[-8:-4] != b'IEND'):
                raise ValueError('预览帧损坏或尺寸不正确，请重试。')
            frames.write(png)
            if index == item['poster']:
                archive.writestr('透明定格/' + stem + '.png', png)
    encoded = subprocess.run(
        ['ffmpeg', '-hide_banner', '-loglevel', 'error', '-xerror', '-y', '-f', 'image2pipe',
         '-framerate', str(FPS), '-c:v', 'png', '-i', str(sequence), '-frames:v', str(count),
         '-an', '-c:v', 'prores_ks', '-profile:v', '4', '-pix_fmt', 'yuva444p10le',
         '-alpha_bits', '16', '-threads', '4', str(movie)],
        stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, timeout=180
    )
    if encoded.returncode:
        raise ValueError('透明 MOV 编码失败。请检查 FFmpeg 是否包含 prores_ks 编码器，并确认磁盘空间足够。')
    archive.write(movie, '透明动画/' + stem + '.mov')


def export(data, stream, size):
    if not status()['ready']:
        raise ValueError('导出需要 FFmpeg，请在工作台设置中安装媒体工具后重试。')
    packet = Packet(stream, size)
    manifest = json.loads(packet.block(MAX_HEADER))
    items = validate(manifest)
    pack_id = uuid.uuid4().hex
    dest = download(data, pack_id)
    dest.parent.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=dest.parent.parent, prefix='.render-') as temp:
        folder = Path(temp)
        partial = folder / 'pack.zip'
        lines = []
        with zipfile.ZipFile(partial, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=2) as archive:
            for index, item in enumerate(items, 1):
                name = re.sub(r'[<>:"/\\|?*\x00-\x1f]', '', item['title'])[:28].strip(' .') or '口播素材'
                stem = f'{index:02d}-{name}'
                encode(packet, item, folder, archive, stem)
                lines.append(f"{stem}（{item['seconds']} 秒）\n{item['quote']}\n")
            if packet.remaining:
                raise ValueError('收到的帧数与搭配不一致，请重试。')
            archive.writestr('原句对照.txt', '\n'.join(lines))
            archive.writestr('使用说明.txt', GUIDE)
            archive.writestr('素材搭配.json', json.dumps(manifest, ensure_ascii=False, indent=2))
        dest.parent.mkdir()
        try:
            partial.replace(dest)
        except OSError:
            dest.parent.rmdir()
            raise
    return {'url': '/motion-download/' + pack_id, 'count': len(items)}
