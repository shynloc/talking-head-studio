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
from core import ROOT, VERSION
from package_release import verify


def run(*args, env=None):
    subprocess.run([str(arg) for arg in args], check=True, env=env)


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
        self.env = dict(os.environ, PLAYWRIGHT_BROWSERS_PATH=str(root.parent / '浏览器'))

    def deploy(self, source, reuse_settings=False):
        if os.name == 'nt':
            entry = ['cmd.exe', '/d', '/c', source / '安装工作台.cmd']
        else:
            entry = [source / 'install_macos.command']
        args = [] if reuse_settings else ['--data', self.data, '--port', '0']
        run(*entry, '--target', self.app, '--shortcut-dir', self.menu, '--no-browser', *args, env=self.env)
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
            assert control(self.data)[1]('/api/instance')['code_root'] == str(self.app)
        else:
            script = ("[Console]::OutputEncoding=[Text.UTF8Encoding]::new($false);"
                      "$s=(New-Object -ComObject WScript.Shell).CreateShortcut($env:STUDIO_VERIFY_LNK);"
                      "@{python=$s.TargetPath;arguments=$s.Arguments}|ConvertTo-Json -Compress")
            env = dict(os.environ, STUDIO_VERIFY_LNK=str(self.menu / '口播导演工作台.lnk'))
            result = json.loads(subprocess.check_output(
                ['powershell.exe', '-NoProfile', '-Command', script], env=env, encoding='utf-8'))
            assert Path(result['python']) == self.python and str(self.data) in result['arguments']


def expand(bundle, folder):
    folder.mkdir(parents=True, exist_ok=False)
    if sys.platform == 'darwin':
        run('ditto', '-x', '-k', bundle, folder)
    else:
        with ZipFile(bundle) as archive:
            archive.extractall(folder)


def prove_import(fixture, api, archive, name):
    with ZipFile(archive) as package:
        original = json.loads(package.read('project.json'))
    new_id = complete(api, original['id'] if (fixture.data / original['id']).is_dir() else
                      api('/api/new', {'title': '导入验收工位'})['id'],
                      'import_project', {'path': str(archive)})['project_id']
    new = api('/api/project?id=' + new_id)
    assert new_id != original['id'] and new['title'] == original['title']
    assert new['pages'] == original['pages'] and new['timeline'] == original['timeline']
    assert new['captions'] == original['captions'] and not new['approvals']
    recording = next(item for item in new['media'] if item['id'] == new['source_id'])
    assert Path(recording['path']).is_relative_to(fixture.data / new_id)
    preview = complete(api, new_id, 'timeline_sample', {'start': 1.75, 'duration': 2.5})
    run('ffmpeg', '-v', 'error', '-i', preview['path'], '-f', 'null', '-')
    print(f'{name}: imported project and decoded preview from packaged media', flush=True)
    return preview['path']


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
    archive = args.out / 'portable-project.zip'
    run(fresh.python, '-X', 'utf8', ROOT / 'tests/three_stage_test.py',
        '--url', control(fresh.data)[0], '--out', stage, '--speech-one', voices[0], '--speech-two', voices[1],
        '--portable-out', archive, '--skip-jianying', *([] if args.whisper else ['--timed-fixture']), env=fresh.env)
    bundle = prove_import(fresh, api, archive, 'same-platform')
    return {'source_project': str(archive), 'migrated_preview': bundle,
            'three_stage': json.loads((stage / 'results.json').read_text(encoding='utf-8'))}


def old_checkout(folder):
    folder.mkdir()
    code = subprocess.check_output(['git', 'archive', '--format=zip', 'ea96162'], cwd=ROOT)
    import io
    with ZipFile(io.BytesIO(code)) as archive:
        archive.extractall(folder)
    if sys.platform == 'darwin':
        (folder / 'install_macos.command').chmod(0o755)
    return folder


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--bundle', required=True, type=Path)
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
        assert api('/api/instance')['code_root'] == str(fresh.app)
        assert (fresh.app / '.studio-install').read_text(encoding='utf-8').strip() == VERSION
        assert (fresh.app / 'PACKAGE-MANIFEST.json').is_file()
        skill = args.out / '独立 Codex' / 'skills' / 'talking-head-studio'
        skill_env = dict(fresh.env, CODEX_HOME=str(skill.parent.parent))
        command = [fresh.python, '-X', 'utf8', source / 'scripts/install.py', '--data', fresh.data, '--no-launch']
        run(*command, env=skill_env)
        assert (skill / 'SKILL.md').read_bytes() == (source / 'SKILL.md').read_bytes()
        run(*command, env=skill_env)
        assert list((fresh.data / 'install-backups').glob('*/SKILL.md'))
        assert api('/api/instance')['code_root'] == str(fresh.app)
        report.update(fresh_install=True, native_launcher=True, skill_registration_upgrade=True)
        if args.migrate:
            report['cross_platform_preview'] = prove_import(fresh, api, args.migrate.resolve(), 'cross-platform')
        else:
            report.update(stage_run(args, fresh, api))
        if args.upgrade:
            old_source = old_checkout(args.out / '旧版本源码')
            url, before = old.deploy(old_source)
            fixture = before('/api/new', {'title': '升级后还在的口播'})
            complete(before, fixture['id'], 'script', {'text': '请保留这段稿件。'})
            pages = before('/api/project?id=' + fixture['id'])['pages']
            (old.app / 'scripts/v34-only.txt').write_text('old', encoding='utf-8')
            new_url, after = old.deploy(source)
            assert new_url == url and after('/api/project?id=' + fixture['id'])['pages'] == pages
            assert (old.app / '.studio-install').read_text(encoding='utf-8').strip() == VERSION
            assert not (old.app / 'scripts/v34-only.txt').exists()
            assert list((old.app.parent / 'backups').glob('*/scripts/v34-only.txt'))
            old.assert_shortcut()
            report['upgrade_from_v34'] = True
        (args.out / 'results.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    finally:
        fresh.stop()
        if args.upgrade:
            old.stop()


if __name__ == '__main__':
    main()
