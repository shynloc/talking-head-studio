"""Install the standalone workbench for the current Windows or macOS user."""

import argparse
import os
import plistlib
import shlex
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from core import ROOT, VERSION, uid
from launch import instance_record, port_in_use, running_instance, stop_instance
from runtime import configure_tool_path, default_app_dir, default_data_dir


APP_NAME = '口播导演工作台'
APP_FILES = ('agents', 'assets', 'scripts', 'vendor', 'README.md', 'SKILL.md', 'requirements.txt')
IGNORE = shutil.ignore_patterns('__pycache__', '*.pyc', '.venv', '.git', '.env', '.env.*')


def runtime_python(app):
    folder = app.parent / 'runtime'
    name = 'Scripts/python.exe' if os.name == 'nt' else 'bin/python'
    return folder / name


def shortcut_folder():
    if os.name == 'nt':
        roaming = Path(os.environ.get('APPDATA') or Path.home() / 'AppData' / 'Roaming')
        return roaming / 'Microsoft/Windows/Start Menu/Programs'
    return Path.home() / 'Applications'


def windows_shortcut(folder, command, root):
    shortcut = folder / (APP_NAME + '.lnk')
    env = dict(os.environ, STUDIO_LINK=str(shortcut), STUDIO_EXECUTABLE=str(command[0]),
               STUDIO_ARGUMENTS=subprocess.list2cmdline(command[1:]), STUDIO_DIRECTORY=str(root))
    script = (
        '$ErrorActionPreference="Stop";'
        '$link=(New-Object -ComObject WScript.Shell).CreateShortcut($env:STUDIO_LINK);'
        '$link.TargetPath=$env:STUDIO_EXECUTABLE;'
        '$link.Arguments=$env:STUDIO_ARGUMENTS;'
        '$link.WorkingDirectory=$env:STUDIO_DIRECTORY;'
        '$link.Save()'
    )
    subprocess.run(['powershell.exe', '-NoProfile', '-NonInteractive', '-Command', script], env=env, check=True)
    return shortcut


def mac_shortcut(folder, command, data):
    app = folder / (APP_NAME + '.app')
    contents = app / 'Contents'
    launcher = contents / 'MacOS/TalkingHeadStudio'
    launcher.parent.mkdir(parents=True, exist_ok=True)
    with (contents / 'Info.plist').open('wb') as file:
        plistlib.dump({
            'CFBundleExecutable': launcher.name,
            'CFBundleIdentifier': 'com.talkingheadstudio.workbench',
            'CFBundleName': APP_NAME,
            'CFBundleDisplayName': APP_NAME,
            'CFBundlePackageType': 'APPL',
            'CFBundleShortVersionString': VERSION,
            'CFBundleVersion': VERSION,
        }, file)
    log = shlex.quote(str(data / 'launcher.log'))
    launcher.write_text(f'#!/bin/sh\nexec {shlex.join(command)} >> {log} 2>&1\n', encoding='utf-8', newline='\n')
    launcher.chmod(0o755)
    return app


def move_app(source, target):
    deadline = time.monotonic() + 4
    while True:
        try:
            source.replace(target)
            return
        except OSError as exc:
            if getattr(exc, 'winerror', None) not in (5, 32) or time.monotonic() >= deadline:
                raise
            time.sleep(.15)


def deploy(app, data, port, no_browser, skip_shortcut, entries):
    if app == ROOT or app in ROOT.parents or ROOT in app.parents:
        raise ValueError('请把应用安装到源码目录之外。')
    if app == data or app in data.parents or data in app.parents:
        raise ValueError('应用目录与项目数据目录需要分别指定。')
    marker = app / '.studio-install'
    if app.exists() and not marker.is_file():
        raise ValueError('目标目录中已有其他文件，请选择新的安装目录。')
    active = running_instance(data)
    legacy = instance_record(data)
    if active and Path(active['code_root']).resolve() != app:
        raise ValueError('还有其他工作台正在使用此数据目录，请先停止它或指定不同的 --data。')
    if legacy and not legacy.get('id') and port_in_use(int(legacy['url'].rsplit(':', 1)[1])):
        raise ValueError('此数据目录正在运行旧版工作台，请先停止旧版或指定不同的 --data。')
    if (not active or int(active['url'].rsplit(':', 1)[1]) != port) and port and port_in_use(port):
        raise ValueError(f'端口 {port} 已被占用，请指定不同的 --port。')

    app.parent.mkdir(parents=True, exist_ok=True)
    data.mkdir(parents=True, exist_ok=True)
    python = runtime_python(app)
    if not python.is_file():
        subprocess.run([sys.executable, '-m', 'venv', str(python.parent.parent)], check=True)
    env = dict(os.environ, PLAYWRIGHT_SKIP_BROWSER_GC='1')
    subprocess.run([str(python), '-X', 'utf8', str(ROOT / 'scripts/setup.py'), '--install', '--smoke'],
                   env=env, check=True)
    command = [str(python), '-X', 'utf8', str(app / 'scripts/launch.py'), '--data', str(data), '--port', str(port)]
    with tempfile.TemporaryDirectory(prefix='.studio-install-', dir=app.parent) as tmp:
        staged = Path(tmp) / 'app'
        staged.mkdir()
        for entry in APP_FILES:
            source = ROOT / entry
            if source.is_dir():
                shutil.copytree(source, staged / entry, ignore=IGNORE)
            else:
                shutil.copy2(source, staged / entry)
        for entry in (*ROOT.glob('*.cmd'), *ROOT.glob('*.command')):
            shutil.copy2(entry, staged / entry.name)
        (staged / marker.name).write_text(VERSION + '\n', encoding='utf-8')
        stop_instance(data, app)
        active_backup = None
        if app.exists():
            backups = app.parent / 'backups'
            backups.mkdir(exist_ok=True)
            active_backup = backups / uid('studio')
            move_app(app, active_backup)
        try:
            move_app(staged, app)
        except OSError:
            if active_backup:
                move_app(active_backup, app)
            raise
        if active_backup:
            print(f'旧版应用备份：{active_backup}')

    if not skip_shortcut:
        entries.mkdir(parents=True, exist_ok=True)
        shortcut = windows_shortcut(entries, command, app) if os.name == 'nt' else mac_shortcut(entries, command, data)
        print(f'启动入口：{shortcut}')
    subprocess.run(command + (['--no-browser'] if no_browser else []), check=True)
    print(f'已安装：{app}\n项目数据：{data}\n应用 Python：{python}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=Path, default=default_app_dir())
    parser.add_argument('--data', type=Path, default=default_data_dir())
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--shortcut-dir', type=Path)
    parser.add_argument('--no-shortcut', action='store_true')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    if os.name != 'nt' and sys.platform != 'darwin':
        parser.error('独立安装入口适用于 Windows 和 macOS。')
    if sys.version_info < (3, 10) or not 0 <= args.port <= 65535:
        parser.error('请使用 Python 3.10 或更新版本，并指定有效端口。')
    configure_tool_path()
    try:
        entries = (args.shortcut_dir or shortcut_folder()).expanduser().resolve()
        deploy(args.target.expanduser().resolve(), args.data.expanduser().resolve(),
               args.port, args.no_browser, args.no_shortcut, entries)
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f'安装未完成：{exc}\n')


if __name__ == '__main__':
    main()
