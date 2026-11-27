"""Build a versioned Skill ZIP from the committed release tree, or verify one."""

import argparse
import ast
import hashlib
import io
import json
import stat
import subprocess
import zipfile
from pathlib import Path, PurePosixPath

from core import ROOT, VERSION, file_digest
from deployment import PACKAGE_DIRS, PACKAGE_FILES


NAME = 'talking-head-studio'
MANIFEST = 'PACKAGE-MANIFEST.json'


def safe_file(name):
    path = PurePosixPath(name)
    return (path.as_posix() == name and '\\' not in name and ':' not in name and
            len(path.parts) > 1 and path.parts[0] == NAME and
            all(part not in ('.', '..') and not part.endswith((' ', '.')) for part in path.parts))


def verify(path):
    with zipfile.ZipFile(path) as bundle:
        entries = bundle.infolist()
        contents = {entry.filename: entry for entry in entries}
        if len({entry.filename.casefold() for entry in entries}) != len(entries) or any(
            not safe_file(entry.filename) or stat.S_IFMT(entry.external_attr >> 16) != stat.S_IFREG
            for entry in entries
        ):
            raise ValueError('压缩包包含重复路径或非普通文件。')
        raw = bundle.read(f'{NAME}/{MANIFEST}')
        result = json.loads(raw)
        records = {f'{NAME}/{file["path"]}': file for file in result['files']}
        if set(contents) != {*records, f'{NAME}/{MANIFEST}'} or len(records) != len(result['files']):
            raise ValueError('压缩包的文件清单不一致。')
        for name, file in records.items():
            entry = contents[name]
            if (entry.file_size != file['bytes'] or
                    hashlib.sha256(bundle.read(entry)).hexdigest() != file['sha256']):
                raise ValueError(f'文件校验失败：{name}')
        for script in ('install_macos.command', 'launch_macos.command'):
            if not contents[f'{NAME}/{script}'].external_attr >> 16 & stat.S_IXUSR:
                raise ValueError(f'macOS 入口缺少执行权限：{script}')
        return result


def build(output):
    revision = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip()
    # Keep shared asset bytes independent of the builder's Git line-ending settings.
    tracked = subprocess.check_output([
        'git', '-c', 'core.autocrlf=false', '-c', 'core.eol=lf',
        'archive', '--format=zip', revision, '--', *PACKAGE_DIRS, *PACKAGE_FILES,
    ], cwd=ROOT)
    with zipfile.ZipFile(io.BytesIO(tracked)) as source:
        module = ast.parse(source.read('scripts/core.py'))
        revision_version = next(ast.literal_eval(node.value) for node in module.body if isinstance(node, ast.Assign)
                                and any(isinstance(target, ast.Name) and target.id == 'VERSION' for target in node.targets))
        if revision_version != VERSION:
            raise ValueError('请先提交和当前版本号一致的源码。')
        files = []
        output.mkdir(parents=True, exist_ok=True)
        archive = output / f'{NAME}-v{VERSION}.zip'
        staging = archive.with_suffix('.zip.tmp')
        try:
            with zipfile.ZipFile(staging, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zip:
                for item in sorted(source.infolist(), key=lambda entry: entry.filename):
                    if item.is_dir():
                        continue
                    name = item.filename
                    data = source.read(item)
                    files.append({'path': name, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest()})
                    entry = zipfile.ZipInfo(f'{NAME}/{name}', date_time=item.date_time)
                    entry.create_system = 3
                    mode = 0o755 if name.endswith('.command') else 0o644
                    entry.external_attr = (stat.S_IFREG | mode) << 16
                    zip.writestr(entry, data, compress_type=zipfile.ZIP_DEFLATED, compresslevel=6)
                manifest = {'version': VERSION, 'revision': revision, 'files': files}
                entry = zipfile.ZipInfo(f'{NAME}/{MANIFEST}')
                entry.create_system = 3
                entry.external_attr = (stat.S_IFREG | 0o644) << 16
                zip.writestr(entry, json.dumps(manifest, ensure_ascii=False, indent=2),
                             compress_type=zipfile.ZIP_DEFLATED)
            verify(staging)
            staging.replace(archive)
        finally:
            staging.unlink(missing_ok=True)
    (output / f'{NAME}-v{VERSION}.sha256').write_text(
        f'{file_digest(archive)}  {archive.name}\n', encoding='ascii')
    return archive


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--output', type=Path)
    mode.add_argument('--verify', type=Path)
    args = parser.parse_args()
    if args.output:
        print(build(args.output.resolve()))
    else:
        manifest = verify(args.verify)
        print(f'v{manifest["version"]} {manifest["revision"]} · {len(manifest["files"])} files')


if __name__ == '__main__':
    main()
