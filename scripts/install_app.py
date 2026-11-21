"""Install the standalone workbench for the current Windows or macOS user."""

import argparse
import os
import plistlib
import shlex
import subprocess
import sys
from pathlib import Path

from core import ROOT, VERSION, write_json
from deployment import check_paths, replace_code, saved_settings
from launch import instance_record, open_browser, port_in_use, running_instance, stop_instance
from runtime import configure_tool_path, default_app_dir, default_data_dir


APP_NAME = '口播导演工作台'


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


def deploy(app, data, port, no_browser, skip_shortcut, entries):
    check_paths(app, data)
    marker = app / '.studio-install'
    if app.exists() and not marker.is_file():
        raise ValueError('目标目录已有其他文件，请选择新的安装目录。')
    previous = running_instance(data)
    legacy = instance_record(data)
    if previous and Path(previous['code_root']).resolve() != app:
        raise ValueError('这个项目目录正在被另一处工作台使用。请先从原入口停止它。')
    if legacy and not legacy.get('id') and port_in_use(int(legacy['url'].rsplit(':', 1)[1])):
        raise ValueError('请先从旧版 Skill 安装目录更新或停止旧服务。')
    old_port = int(previous['url'].rsplit(':', 1)[1]) if previous else None
    if port and port != old_port and port_in_use(port):
        raise ValueError(f'端口 {port} 已被占用，可用 --port 0 自动选择。')

    python = runtime_python(app)
    env = dict(os.environ, PLAYWRIGHT_SKIP_BROWSER_GC='1')

    def prepare(staged):
        if not python.is_file():
            subprocess.run([sys.executable, '-m', 'venv', str(python.parent.parent)], check=True)
        subprocess.run([str(python), '-X', 'utf8', str(staged / 'scripts/setup.py'), '--install', '--smoke'],
                       env=env, check=True)
        (staged / marker.name).write_text(VERSION + '\n', encoding='utf-8')
        write_json(staged / '.studio-deployment.json', {'data': str(data), 'port': port})

    def launch(which_port):
        command = [str(python), '-X', 'utf8', str(app / 'scripts/launch.py'),
                   '--data', str(data), '--port', str(which_port), '--no-browser']
        result = subprocess.run(command, check=False, capture_output=True, text=True, encoding='utf-8')
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or '工作台启动失败。')
        return result.stdout.strip()

    def start():
        nonlocal url
        url = launch(port or old_port or 0)

    def recover():
        if old_port and marker.is_file():
            launch(old_port)

    url = ''
    backup = replace_code(app, app.parent / 'backups', prepare,
                          lambda: stop_instance(data, app), start, recover)
    if backup:
        print(f'旧版应用备份：{backup}')

    if not skip_shortcut:
        entries.mkdir(parents=True, exist_ok=True)
        args = [str(python), '-X', 'utf8', str(app / 'scripts/launch.py'), '--data', str(data), '--port', str(port)]
        shortcut = windows_shortcut(entries, args, app) if os.name == 'nt' else mac_shortcut(entries, args, data)
        print(f'启动入口：{shortcut}')
    if not no_browser:
        open_browser(url)
    print(f'已安装：{app}\n项目数据：{data}\n应用 Python：{python}\n工作台地址：{url}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=Path, default=default_app_dir())
    parser.add_argument('--data', type=Path)
    parser.add_argument('--port', type=int)
    parser.add_argument('--shortcut-dir', type=Path)
    parser.add_argument('--no-shortcut', action='store_true')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    if os.name != 'nt' and sys.platform != 'darwin':
        parser.error('独立安装入口适用于 Windows 和 macOS。')
    if sys.version_info < (3, 10) or args.port is not None and not 0 <= args.port <= 65535:
        parser.error('请使用 Python 3.10 或更新版本，并指定有效端口。')
    configure_tool_path()
    try:
        entries = (args.shortcut_dir or shortcut_folder()).expanduser().resolve()
        app = args.target.expanduser().resolve()
        installed = saved_settings(app)
        data = args.data or (Path(installed['data']) if installed else default_data_dir())
        port = args.port if args.port is not None else installed.get('port', 8765)
        deploy(app, data.expanduser().resolve(), port, args.no_browser, args.no_shortcut, entries)
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f'安装未完成：{exc}\n')


if __name__ == '__main__':
    main()
