"""Portable ZIP format and compatibility reader for the original project ZIP."""

import copy
import hashlib
import json
import re
import shutil
import tempfile
import zipfile
from pathlib import Path, PurePosixPath

import agent_portable
import materials
from core import Conflict, LOCK, Store, edl_digest, file_digest, rough_current, source, uid


FORMAT = 'talking-head-studio'
VERSION = 2
METADATA_LIMIT = 64 * 1024**2
CHUNK = 1024**2


def _clear_previews(project):
    project.update(approvals={}, exports=[], qa={}, history=[])
    for key in ('previous_rough', 'proxy_id', 'layout_sheet_id'):
        project.pop(key, None)


def _link(item, path=''):
    item['path'] = path
    item['external'] = not path


def _copy_digest(stream, out):
    digest = hashlib.sha256()
    size = 0
    while block := stream.read(CHUNK):
        out.write(block)
        digest.update(block)
        size += len(block)
    return {'size': size, 'sha256': digest.hexdigest()}


def _write_media(archive, item, destination, copied, files, label):
    path = Path(item.get('path') or '.')
    if not path.is_file():
        raise ValueError(f'{label}文件不存在，请先重新关联或重新生成。')
    identity = path.resolve()
    if identity not in copied:
        suffix = path.suffix.lower()
        suffix = suffix if re.fullmatch(r'\.[a-z0-9]{1,12}', suffix) else '.bin'
        name = copied[identity] = destination + suffix
        entry = zipfile.ZipInfo.from_file(path, name)
        with path.open('rb') as stream, archive.open(entry, 'w', force_zip64=True) as out:
            files[name] = _copy_digest(stream, out)
    name = copied[identity]
    _link(item, name)
    return files[name]['sha256']


def export_bundle(store, project, report, include_source=False, include_tasks=False):
    snapshot = copy.deepcopy(project)
    snapshot["assets"] = [materials.portable(item) for item in snapshot["assets"]]
    _clear_previews(snapshot)
    snapshot.pop('migration', None)
    primary = source(snapshot)
    with_source = bool(primary and include_source)
    rough = snapshot.get('rough')
    suffix = '-portable' if with_source else ''
    out = store.folder(project['id']) / 'exports' / f"studio-project-{project['version']}{suffix}.zip"
    out.parent.mkdir(exist_ok=True)
    report(.1, '打包工程、素材与原片' if with_source else '打包工程与素材')
    copied, checksums = {}, {}
    reviewed = bool(rough_current(project) and project['approvals'].get('rough'))
    if not reviewed and primary and not primary.get('path'):
        reviewed = bool(project.get('migration', {}).get('rough_reviewed'))
    with tempfile.TemporaryDirectory(dir=out.parent) as tmp:
        staged = Path(tmp) / 'project.zip'
        with zipfile.ZipFile(staged, 'w', zipfile.ZIP_DEFLATED) as archive:
            for i, asset in enumerate(snapshot['assets']):
                _write_media(archive, asset, f'assets/{i:04d}', copied, checksums, asset['name'])
            if primary:
                expected = primary.get('sha256')
                if with_source:
                    fingerprint = _write_media(archive, primary, 'media/source', copied, checksums, '原片')
                else:
                    original = Path(primary.get('path') or '.')
                    fingerprint = file_digest(original) if original.is_file() else expected
                    _link(primary)
                if expected and expected != fingerprint:
                    raise ValueError('原片内容已变化，请重新关联原片后再打包。')
                if fingerprint:
                    primary['sha256'] = fingerprint
            if rough:
                if with_source:
                    _write_media(archive, rough, 'media/rough', copied, checksums, '粗剪')
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
            task_snapshot = agent_portable.export_tasks(store, project['id']) if include_tasks else None
            if task_snapshot is not None:
                task_data = json.dumps(task_snapshot, ensure_ascii=False).encode('utf-8')
                if len(task_data) > METADATA_LIMIT:
                    raise ValueError('随包待办资料过大，请先导出工程文件。')
                archive.writestr('agent-tasks.json', task_data)
            archive.writestr('bundle.json', json.dumps({
                'format': FORMAT, 'version': VERSION, 'source_included': with_source,
                'files': checksums, 'rough_reviewed': reviewed,
                'agent_tasks': task_snapshot is not None,
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
    try:
        package = zipfile.ZipFile(path)
    except zipfile.BadZipFile as error:
        raise ValueError('工程 ZIP 不完整或已损坏，请重新获取文件。') from error
    with package as archive:
        files = _members(archive)
        manifest = _read_metadata(archive, files, 'bundle.json') if 'bundle.json' in files else None
        if manifest is not None and (manifest.get('format') != FORMAT or manifest.get('version') not in (1, VERSION)):
            raise ValueError('不支持的工程包格式。')
        project = _read_metadata(archive, files, 'project.json')
        if project.get('schema_version') not in (1, 2):
            raise ValueError('不支持的工程版本。')
        _path_ids(project)
        old_id = project['id']
        project.update(id=uid('project'), version=0)
        _clear_previews(project)
        project.pop('example', None)
        reviewed = bool(manifest and manifest.get('version') == VERSION and manifest.get('rough_reviewed') is True)
        project['migration'] = {'rough_reviewed': reviewed, 'edl_hash': edl_digest(project.get('edl', []))}
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

        primary = source(project)
        hashes = None
        task_snapshot = None
        if manifest and manifest.get('version') == VERSION:
            hashes = manifest.get('files')
            if not isinstance(hashes, dict) or set(hashes) != set(needed):
                raise ValueError('工程包的媒体清单与实际引用不一致。')
            for name, info in needed.items():
                record = hashes[name]
                if (not isinstance(record, dict) or record.get('size') != info.file_size
                        or not re.fullmatch('[0-9a-f]{64}', str(record.get('sha256', '')))):
                    raise ValueError('工程包的媒体校验信息有误。')
            if primary:
                fingerprint = primary.get('sha256')
                if fingerprint and not re.fullmatch('[0-9a-f]{64}', str(fingerprint)):
                    raise ValueError('工程包的原片校验信息有误。')
                if primary.get('path') and (not fingerprint or not any(
                        Path(primary['path']) == folder / name and record['sha256'] == fingerprint
                        for name, record in hashes.items())):
                    raise ValueError('工程包的原片校验信息与媒体清单不一致。')
            if manifest.get('agent_tasks') is True:
                task_snapshot = _read_metadata(archive, files, 'agent-tasks.json')
        elif primary:
            primary.pop('sha256', None)

        if reviewed and primary and primary.get('path') and (project.get('rough') or {}).get('path') and rough_current(project):
            project['approvals']['rough'] = {'kind': 'migrated'}

        if sum(info.file_size for info in needed.values()) > shutil.disk_usage(store.root).free:
            raise ValueError('剩余磁盘空间不足，无法解包工程。')
        from timeline import validate
        validate(project)
        task_count = 0
        with tempfile.TemporaryDirectory(prefix='.import-', dir=store.root) as tmp:
            staging_store = Store(tmp)
            staging = staging_store.folder(project['id'])
            for name, info in needed.items():
                dest = staging / name
                dest.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as stream, dest.open('wb') as out:
                    if hashes is None:
                        shutil.copyfileobj(stream, out, length=CHUNK)
                    elif _copy_digest(stream, out) != hashes[name]:
                        raise ValueError(f'工程包中的媒体校验失败：{name}')
            if task_snapshot is not None:
                task_count = agent_portable.import_tasks(task_snapshot, project, staging)
            staging_store.save(project, label='导入工程')
            staging.replace(folder)
    return {'project_id': project['id'], 'original_id': old_id, 'agent_tasks': task_count}


def relink_recording(store, pid, path, report):
    import media

    project = store.load(pid)
    original = source(project)
    if not original:
        raise ValueError('工程尚无原片，请先导入。')
    path = Path(path).resolve()
    if not path.is_file():
        raise ValueError('找不到所选文件。')
    fingerprint = original.get('sha256')
    if fingerprint:
        report(.08, '核对原片内容')
        if file_digest(path) != fingerprint:
            raise ValueError('这不是工程包中的原片。请选择打包时使用的文件。')
    meta = media.probe(path)
    if (abs(meta['duration'] - original['duration']) > .08
            or (meta['width'], meta['height']) != (original['width'], original['height'])):
        raise ValueError('新文件的时长或画幅与原片不符，请选择原片。')

    with LOCK:
        project = store.load(pid)
        if source(project) != original:
            raise Conflict('原片已变化，请重新选择。')
        source(project).update(path=str(path), name=path.name, external=False)
        rough = project.get('rough')
        relinking_migration = bool(project.get('migration') and not original.get('path'))
        restore_rough = relinking_migration and rough_current(project)
        if rough:
            if rough['media_id'] == original['id']:
                rough['path'] = str(path)
            elif not Path(rough.get('path') or '.').is_file():
                project['previous_rough'], project['rough'] = rough, None
        project['approvals'] = {}
        store.save(project, label='重新关联原片，保留稿件和剪点')
    if restore_rough and not project.get('rough'):
        media.render_rough(store, pid, report)
    if restore_rough and fingerprint and project['migration']['rough_reviewed']:
        with LOCK:
            latest = store.load(pid)
            if (source(latest)['path'] == str(path) and latest['edl'] == project['edl']
                    and rough_current(latest)):
                latest['approvals']['rough'] = {'kind': 'migrated'}
                store.save(latest, label='恢复已确认的剪点')
    latest = store.load(pid)
    return {'ok': True, 'next_stage': 3 if relinking_migration and rough_current(latest) else 2}
