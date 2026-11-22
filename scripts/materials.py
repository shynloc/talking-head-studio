"""Media properties and provenance shared by the workbench and its editing packages."""
from functools import lru_cache
from pathlib import Path
import hashlib
import xml.etree.ElementTree as ET

from core import LOCK, ROOT, uid, now

HCS = ROOT / 'vendor/html-creator-studio-core'
GIF = ROOT / 'vendor/gif-factory/scripts/export_pack.py'
SPECS = {
    'html-creator-studio': (HCS/'shared/frame-styles.mjs', ['docx','pdf','pptx','frame'], ['text','rgba'], ['Chromium for animation']),
    'gif-factory': (GIF, ['png'], ['gif'], ['Pillow']),
}
IMAGES = {'png','jpg','jpeg','webp','gif','svg'}
VIDEO = {'mp4','mov','webm'}
AUDIO = {'wav','mp3','m4a','flac','ogg'}


@lru_cache(maxsize=1)
def components():
    result={}
    for name,(entry,inputs,outputs,requires) in SPECS.items():
        available=entry.is_file() and (name!='html-creator-studio' or (HCS/'scripts/extract_resume.py').is_file())
        result[name]={'available':available,'inputs':inputs,'outputs':outputs,'requires':requires,'network':False,
                      'version':hashlib.sha256(entry.read_bytes()).hexdigest() if available else None}
    return result


def properties(path):
    kind=path.suffix.lower()[1:]
    if kind=='svg':
        node=ET.parse(path).getroot()
        box=node.get('viewBox','').replace(',',' ').split()
        def size(key,index):
            try:return round(float(node.get(key,'').removesuffix('px')))
            except ValueError:return round(float(box[index])) if len(box)==4 else None
        return dict(width=size('width',2),height=size('height',3),duration=None,alpha_capable=True)
    if kind in IMAGES:
        from PIL import Image, ImageSequence
        with Image.open(path) as im:
            alpha='A' in im.getbands() or 'transparency' in im.info
            seconds=sum(frame.info.get('duration',0) for frame in ImageSequence.Iterator(im))/1000 if getattr(im,'is_animated',False) else None
            return dict(width=im.width,height=im.height,duration=seconds,alpha_capable=alpha)
    from media import probe
    meta=probe(path)
    return {k:meta.get(k) for k in ('width','height','duration','alpha_capable')}


def describe(path, producer):
    return {'component':producer,'component_version':components().get(producer,{}).get('version'),
            **properties(path)}


def add(store,pid,path,name,source,producer='import',parent=None):
    path=Path(path).resolve()
    kind=path.suffix.lower()[1:]
    if not path.is_file() or kind not in IMAGES|VIDEO|AUDIO:
        raise ValueError('请选择图片、动画、视频或音频文件。')
    item={'id':uid('asset'),'path':str(path),'type':kind,'name':name or path.stem,'source':source,'approved':False,
          **describe(path,producer)}
    if parent:item['source_asset_id']=parent
    with LOCK:
        project=store.load(pid)
        project['assets'].append(item)
        project['media'].append(dict(id=uid('file'),path=str(path),kind='asset',name=path.name,created=now()))
        store.save(project,label='加入素材')
    return item


def portable(item):
    result=dict(item)
    if 'alpha_capable' not in result and Path(result['path']).is_file():
        try:
            result.update(describe(Path(result['path']),result.get('component','import')))
        except (OSError, ValueError, RuntimeError, ET.ParseError):
            # An old unrecognised asset may still be opened in the original editor.
            pass
    return result
