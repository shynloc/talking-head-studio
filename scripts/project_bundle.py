"""Portable ZIP format and compatibility reader for the original project ZIP."""

import copy
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

from core import Store, source, uid


FORMAT = 'talking-head-studio'
VERSION = 1
METADATA_LIMIT = 64 * 1024**2


def _clear_previews(project):
    project.update(approvals={}, exports=[], qa={}, history=[])
    for key in ('previous_rough', 'proxy_id', 'layout_sheet_id'):
        project.pop(key, None)


def _link(item, path=''):
    item['path'] = path
    item['external'] = not path


def _write_media(archive, item, destination, copied, label):
    path = Path(item.get('path') or '.')
    if not path.is_file():
        raise ValueError(f'{label}文件不存在，请先重新关联或重新生成。')
    identity = path.resolve()
    if identity not in copied:
        suffix = path.suffix.lower()
        suffix = suffix if re.fullmatch(r'\.[a-z0-9]{1,12}', suffix) else '.bin'
        copied[identity] = destination + suffix
        archive.write(path, copied[identity], compress_type=zipfile.ZIP_STORED)
    _link(item, copied[identity])


def export_bundle(store, project, report, include_source=False):
    snapshot = copy.deepcopy(project)
    _clear_previews(snapshot)
    primary = source(snapshot)
    with_source = bool(primary and include_source)
    rough = snapshot.get('rough')
    suffix = '-portable' if with_source else ''
    out = store.folder(project['id']) / 'exports' / f"studio-project-{project['version']}{suffix}.zip"
    out.parent.mkdir(exist_ok=True)
    report(.1, '打包工程、素材与原片' if with_source else '打包工程与素材')
    copied = {}
    with tempfile.TemporaryDirectory(dir=out.parent) as tmp:
        staged = Path(tmp) / 'project.zip'
        with zipfile.ZipFile(staged, 'w', zipfile.ZIP_DEFLATED) as archive:
            for i, asset in enumerate(snapshot['assets']):
                _write_media(archive, asset, f'assets/{i:04d}', copied, asset['name'])
            if primary:
                if with_source:
                    _write_media(archive, primary, 'media/source', copied, '原片')
                else:
                    _link(primary)
            if rough:
                if with_source:
                    _write_media(archive, rough, 'media/rough', copied, '粗剪')
                else:
                    _link(rough)

            media = []
            for item in snapshot['media']:
                if item is primary:
                    media.append(item)
                    continue
                packed_path = copied.get(Path(item['path']).resolve())
                if packed_path and item['kind'] in ('asset', 'rough'):
                    _link(item, packed_path)
                    media.append(item)
            snapshot['media'] = media
            archive.writestr('bundle.json', json.dumps({
                'format': FORMAT, 'version': VERSION, 'source_included': with_source,
            }))
            archive.writestr('project.json', json.dumps(snapshot, ensure_ascii=False, indent=2))
            readme = '工程含稿件、字幕、轨道与素材。'
            readme += '当前原片随包携带。' if with_source else '请在目标工作台重新关联原片。'
            archive.writestr('说明.txt', readme)

            latest = next((item for item in reversed(project['media']) if item['kind'] == 'final'), None)
            if latest and Path(latest['path']).is_file():
                parent = Path(latest['path']).parent
                for file in parent.rglob('*'):
                    if file.is_file() and file.suffix.lower() not in ('.mp4', '.mov', '.wav', '.log'):
                        archive.write(file, 'render-source/' + file.relative_to(parent).as_posix())
        staged.replace(out)
    return store.register(project['id'], out, 'deliverable')


def _members(archive):
    files = {}
    seen = set()
    for info in archive.infolist():
        name = info.filename.removesuffix('/')
        path = PurePosixPath(name)
        key = name.casefold()
        if (not path.parts or path.is_absolute() or path.as_posix() != name
                or any(part.endswith(('.', ' ')) for part in path.parts)
                or '\\' in name or ':' in name or key in seen):
            raise ValueError('工程包内有非法或重复路径。')
        seen.add(key)
        if not info.is_dir():
            files[name] = info
    return files


def _read_metadata(archive, files, name):
    if name not in files or files[name].file_size > METADATA_LIMIT:
        raise ValueError(f'工程包缺少有效的 {name}。')
    data = json.loads(archive.read(files[name]))
    if not isinstance(data, dict):
        raise ValueError(f'工程包内 {name} 格式不正确。')
    return data


def _path_ids(project):
    items = list(project.get('assets', []))
    items.extend(project.get('timeline', {}).get('clips', []))
    for page in project.get('pages', []):
        items.append(page)
        items.extend(page.get('tags', []))
    for item in items:
        if not re.fullmatch(r'[A-Za-z0-9_-]+', str(item.get('id', ''))):
            raise ValueError('工程包内有无效的素材或时间线编号。')


def import_bundle(store, path):
    with zipfile.ZipFile(path) as archive:
        files = _members(archive)
        manifest = _read_metadata(archive, files, 'bundle.json') if 'bundle.json' in files else None
        if manifest is not None and (manifest.get('format'), manifest.get('version')) != (FORMAT, VERSION):
            raise ValueError('不支持的工程包格式。')
        project = _read_metadata(archive, files, 'project.json')
        if project.get('schema_version') not in (1, 2):
            raise ValueError('不支持的工程版本。')
        _path_ids(project)
        old_id = project['id']
        project.update(id=uid('project'), version=0)
        _clear_previews(project)
        folder = store.folder(project['id'])
        needed = {}

        def bind(item, prefixes):
            name = item.get('path') or ''
            if name not in files or not name.startswith(prefixes):
                raise ValueError('工程包缺少引用的媒体文件，或其中的媒体路径不合法。')
            needed[name] = files[name]
            _link(item, str(folder / name))

        for asset in project['assets']:
            bind(asset, ('assets/',))
        for item in project['media']:
            if item.get('external'):
                _link(item)
            else:
                bind(item, ('assets/', 'media/') if manifest else ('assets/',))
        if project.get('rough'):
            if manifest and not project['rough'].get('external'):
                bind(project['rough'], ('assets/', 'media/'))
            else:
                _link(project['rough'])

        if sum(info.file_size for info in needed.values()) > shutil.disk_usage(store.root).free:
            raise ValueError('剩余磁盘空间不足，无法解包工程。')
        with tempfile.TemporaryDirectory(prefix='.import-', dir=store.root) as tmp:
            staging_store = Store(tmp)
            staging = staging_store.folder(project['id'])
            for name, info in needed.items():
                dest = staging / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as stream, dest.open('wb') as out:
                    shutil.copyfileobj(stream, out, length=1024**2)
            staging_store.save(project, label='导入工程')
            staging.replace(folder)
    return {'project_id': project['id'], 'original_id': old_id}
