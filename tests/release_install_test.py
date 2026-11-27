"""Exercise the released ZIP as a new user and bring an existing workbench forward."""

import argparse
import json
import os
import platform
import plistlib
from pathlib import Path
import shutil
import subprocess
import sys
import time
from urllib.request import Request, urlopen
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from core import ROOT, VERSION, file_digest
from launch import running_instance
from media import probe
from package_release import verify
from project_migration_fixtures import write_legacy_lightweight


MIGRATION_PACKS = (
    ('full', 'portable-project.zip', 2, False),
    ('lightweight', 'lightweight-project.zip', 2, True),
    ('legacy', 'legacy-project.zip', 1, True),
)


def run(*args, env=None, cwd=None):
    subprocess.run([str(arg) for arg in args], check=True, env=env, cwd=cwd)


def control(data):
    def api(path, payload=None):
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
        with urlopen(Request(url + path, data=body, headers={
            'Content-Type': 'application/json', 'X-Studio-Token': token,
        }), timeout=20) as response:
            return json.load(response)

    url = json.loads((data / 'server.json').read_text(encoding='utf-8'))['url']
    token = ''
    token = api('/api/bootstrap')['token']
    return url, api


def complete(api, pid, action, args):
    task = api('/api/action', {'project_id': pid, 'action': action, 'args': args})
    for _ in range(2400):
        jobs = api('/api/jobs?id=' + pid)
        result = next(job for job in jobs if job['id'] == task['id'])
        if result['status'] == 'done':
            return result['result']
        assert result['status'] in ('running', 'queued'), result
        time.sleep(.25)
    raise TimeoutError(action)


class Fixture:
    def __init__(self, root):
        self.root = root
        self.app = root / '安装 应用' / 'talking-head-studio'
        self.data = root / "项目 '数据"
        self.menu = root / '应用入口'
        runtime = self.app.parent / 'runtime'
        self.python = runtime / ('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        self.env = dict(os.environ, PYTHONUTF8='1')
        self.env.setdefault('PLAYWRIGHT_BROWSERS_PATH', str(root.parent / '浏览器'))

    def deploy(self, source, reuse_settings=False, install_shortcut=True):
        if os.name == 'nt':
            entry = ['cmd.exe', '/d', '/c', '安装工作台.cmd']
        else:
            entry = [source / 'install_macos.command']
        args = [] if reuse_settings else ['--data', self.data, '--port', '0']
        if not install_shortcut:
            args.append('--no-shortcut')
        run(*entry, '--target', self.app, '--shortcut-dir', self.menu, '--no-browser', *args,
            env=self.env, cwd=source)
        return control(self.data)

    def stop(self):
        if self.python.is_file() and (self.app / 'scripts/launch.py').is_file():
            run(self.python, '-X', 'utf8', self.app / 'scripts/launch.py', '--data', self.data, '--stop', env=self.env)

    def assert_shortcut(self):
        if sys.platform == 'darwin':
            app = self.menu / '口播导演工作台.app'
            contents = app / 'Contents'
            info = plistlib.loads((contents / 'Info.plist').read_bytes())
            assert info['CFBundleShortVersionString'] == VERSION
            self.stop()
            run(contents / 'MacOS' / info['CFBundleExecutable'], env={**self.env, 'BROWSER': '/usr/bin/true'})
            assert Path(running_instance(self.data)['code_root']) == self.app
        else:
            from windows_link import read_link
            python, arguments = read_link(self.menu / '口播导演工作台.lnk')
            assert Path(python).resolve() == self.python.resolve(), (python, str(self.python))
            assert str(self.data) in arguments, arguments


def expand(bundle, folder):
    folder.mkdir(parents=True, exist_ok=False)
    if sys.platform == 'darwin':
        run('ditto', '-x', '-k', bundle, folder)
    else:
        with ZipFile(bundle) as archive:
            archive.extractall(folder)


def upload_project(fixture, api, archive):
    url = json.loads((fixture.data / 'server.json').read_text(encoding='utf-8'))['url']
    with archive.open('rb') as body:
        request = Request(url + '/api/projects/import', data=body, headers={
            'Content-Length': str(archive.stat().st_size), 'Content-Type': 'application/zip',
            'X-Studio-Token': api('/api/bootstrap')['token'],
        })
        with urlopen(request, timeout=60) as response:
            return json.load(response)


def prove_import(fixture, api, archive, name, original_recording=None):
    with ZipFile(archive) as package:
        original = json.loads(package.read('project.json'))
        manifest = json.loads(package.read('bundle.json')) if 'bundle.json' in package.namelist() else {}
    new_id = upload_project(fixture, api, archive)['project_id']
    path = '/api/project?id=' + new_id
    new = api(path)
    assert new_id != original['id'] and new['title'] == original['title']
    assert new['pages'] == original['pages'] and new['timeline'] == original['timeline']
    assert new['edl'] == original['edl'] and new['captions'] == original['captions']
    for asset in new['assets']:
        local_asset = Path(asset['path'])
        assert local_asset.is_relative_to(fixture.data / new_id) and local_asset.is_file()
    restored_rough = bool(manifest.get('version') == 2 and manifest.get('rough_reviewed'))
    recording = next(item for item in new['media'] if item['id'] == new['source_id'])
    if original_recording:
        assert not recording['path'] and not new['approvals']
        complete(api, new_id, 'relink_source', {'path': str(original_recording)})
        new = api(path)
        assert new['rough_current'] and new['captions'] == original['captions']
    else:
        local_recording = Path(recording['path'])
        assert local_recording.is_relative_to(fixture.data / new_id) and local_recording.is_file()
        if manifest.get('version') == 2:
            assert file_digest(local_recording) == recording['sha256']
    expected = {'rough': {'kind': 'migrated'}} if restored_rough else {}
    assert new['approvals'] == expected
    if not restored_rough:
        run('ffmpeg', '-v', 'error', '-xerror', '-i', new['rough']['path'], '-f', 'null', '-')
        complete(api, new_id, 'approve_rough', {})
    duration = original['timeline']['duration']
    preview = complete(api, new_id, 'timeline_sample', {'start': 0, 'duration': duration})
    complete(api, new_id, 'approve_timeline', {})
    final = complete(api, new_id, 'timeline_final', {})
    run('ffmpeg', '-v', 'error', '-xerror', '-i', final['path'], '-f', 'null', '-')
    output = probe(final['path'])
    assert output['video'] and output['audio'] and abs(output['duration'] - duration) < .15
    new = api(path)
    assert new['edl'] == original['edl'] and new['captions'] == original['captions']
    assert not any(job['action'] in ('transcribe', 'analyze_cuts') for job in api('/api/jobs?id=' + new_id))
    print(f'{name}: imported, preserved edits and decoded {output["duration"]:.2f}s of exported video', flush=True)
    return {'id': new_id, 'preview': preview['path'], 'final': final['path'], 'duration': output['duration'],
            'version': manifest.get('version'), 'source_relinked': bool(original_recording)}


def prove_migration_set(fixture, api, incoming):
    results = {}
    for name, filename, version, relink in MIGRATION_PACKS:
        recording = incoming / 'recording.mp4' if relink else None
        result = prove_import(fixture, api, incoming / filename, name, recording)
        assert result['version'] == version
        results[name] = result
    assert len({result['id'] for result in results.values()}) == len(MIGRATION_PACKS)
    return results


def stage_run(args, fresh, api):
    voices = [path.resolve() if path else None for path in (args.speech_one, args.speech_two)]
    if not all(voices):
        voices = [args.out / 'first.wav', args.out / 'second.wav']
        for frequency, file in zip((380, 440), voices):
            run('ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
                f'sine=frequency={frequency}:duration=3.5', '-y', file)
    if args.whisper:
        assert args.speech_one and args.speech_two
        run(fresh.python, fresh.app / 'scripts/setup.py', '--speech', env=fresh.env)
    stage = args.out / '三阶段'
    fixtures = args.out / 'migration-fixtures'
    fixtures.mkdir()
    archive = fixtures / 'portable-project.zip'
    lightweight = fixtures / 'lightweight-project.zip'
    run(fresh.python, '-X', 'utf8', ROOT / 'tests/three_stage_test.py',
        '--url', control(fresh.data)[0], '--out', stage, '--speech-one', voices[0], '--speech-two', voices[1],
        '--portable-out', archive, '--lightweight-out', lightweight,
        '--skip-jianying', *([] if args.whisper else ['--timed-fixture']), env=fresh.env)
    write_legacy_lightweight(lightweight, fixtures / 'legacy-project.zip')
    shutil.copy2(stage / 'recording.mp4', fixtures / 'recording.mp4')
    bundle = prove_import(fresh, api, archive, 'same-platform')
    return {'source_project': str(archive), 'migrated_preview': bundle['preview'],
            'three_stage': json.loads((stage / 'results.json').read_text(encoding='utf-8'))}


def old_checkout(folder):
    folder.mkdir()
    code = subprocess.check_output(['git', 'archive', '--format=zip', '898ef50'], cwd=ROOT)
    import io
    with ZipFile(io.BytesIO(code)) as archive:
        archive.extractall(folder)
    if sys.platform == 'darwin':
        (folder / 'install_macos.command').chmod(0o755)
    return folder


def seed_previous(fixture, source):
    if os.name == 'nt':
        url, before = fixture.deploy(source, install_shortcut=False)
        project = before('/api/new', {'title': '升级后还在的口播'})
        complete(before, project['id'], 'script', {'text': '请保留这段稿件。'})
        return url, before('/api/project?id=' + project['id'])
    shutil.copytree(source, fixture.app)
    (fixture.app / '.studio-install').write_text('3.8.0\n', encoding='utf-8')
    seed = (
        'import json,sys; sys.path.insert(0,sys.argv[1]); '
        'from core import Store,default_project,script_pages; '
        'project=default_project("升级后还在的口播"); project["pages"]=script_pages("请保留这段稿件。"); '
        'print(json.dumps(Store(sys.argv[2]).save(project),ensure_ascii=False))'
    )
    result = subprocess.check_output(
        [sys.executable, '-X', 'utf8', '-c', seed, str(fixture.app / 'scripts'), str(fixture.data)], encoding='utf-8')
    return None, json.loads(result)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', type=Path, default=ROOT / 'dist' / f'talking-head-studio-v{VERSION}.zip')
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--migrate', type=Path)
    parser.add_argument('--upgrade', action='store_true')
    parser.add_argument('--speech-one', type=Path)
    parser.add_argument('--speech-two', type=Path)
    parser.add_argument('--whisper', action='store_true')
    args = parser.parse_args()
    args.out = args.out.resolve()
    args.out.mkdir(parents=True, exist_ok=True)
    manifest = verify(args.bundle)
    assert manifest['version'] == VERSION
    expanded = args.out / '全新下载'
    expand(args.bundle.resolve(), expanded)
    source = expanded / 'talking-head-studio'
    fresh = Fixture(args.out / '新用户')
    old = Fixture(args.out / '升级用户')
    report = {'version': VERSION, 'revision': manifest['revision'],
              'system': platform.platform(), 'arch': platform.machine()}
    try:
        _, api = fresh.deploy(source)
        fresh.assert_shortcut()
        _, api = control(fresh.data)
        assert Path(running_instance(fresh.data)['code_root']) == fresh.app
        assert (fresh.app / '.studio-install').read_text(encoding='utf-8').strip() == VERSION
        assert (fresh.app / 'PACKAGE-MANIFEST.json').is_file()
        skill = args.out / '独立 Codex' / 'skills' / 'talking-head-studio'
        skill_env = dict(fresh.env, CODEX_HOME=str(skill.parent.parent))
        command = [fresh.python, '-X', 'utf8', source / 'scripts/install.py', '--data', fresh.data, '--no-launch']
        run(*command, env=skill_env)
        assert (skill / 'SKILL.md').read_bytes() == (source / 'SKILL.md').read_bytes()
        run(*command, env=skill_env)
        assert list((fresh.data / 'install-backups').glob('*/SKILL.md'))
        assert Path(running_instance(fresh.data)['code_root']) == fresh.app
        report.update(fresh_install=True, native_launcher=True, skill_registration_upgrade=True)
        if args.migrate:
            incoming = args.migrate.resolve()
            if incoming.is_dir():
                report['cross_platform_migration'] = prove_migration_set(fresh, api, incoming)
                report['cross_platform_preview'] = report['cross_platform_migration']['full']['preview']
            else:
                report['cross_platform_preview'] = prove_import(fresh, api, incoming, 'cross-platform')['preview']
        else:
            report.update(stage_run(args, fresh, api))
        if args.upgrade:
            old_source = old_checkout(args.out / '旧版本源码')
            old_url, fixture = seed_previous(old, old_source)
            pages = fixture['pages']
            (old.app / 'scripts/v34-only.txt').write_text('old', encoding='utf-8')
            new_url, after = old.deploy(source)
            assert old_url is None or new_url == old_url
            assert after('/api/project?id=' + fixture['id'])['pages'] == pages
            assert (old.app / '.studio-install').read_text(encoding='utf-8').strip() == VERSION
            assert not (old.app / 'scripts/v34-only.txt').exists()
            assert list((old.app.parent / 'backups').glob('*/scripts/v34-only.txt'))
            old.assert_shortcut()
            report['upgrade_from_v34'] = True
            if sys.platform == 'darwin':
                live_url = control(old.data)[0]
                reinstalled, _ = old.deploy(source, reuse_settings=True)
                assert reinstalled == live_url
                report['reinstall_with_active_service'] = True
        (args.out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    finally:
        fresh.stop()
        if args.upgrade:
            old.stop()


if __name__ == '__main__':
    main()
