"""Install or update the separately discoverable Codex Skill."""
import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path
from urllib.error import HTTPError

from core import VERSION
from deployment import check_paths, replace_code
from install_app import runtime_python
from launch import instance_record, open_browser, port_in_use, request_json, running_instance, stop_instance
from runtime import configure_tool_path, default_app_dir, default_data_dir


def default_skill_dir():
    codex = Path(os.environ.get('CODEX_HOME') or Path.home() / '.codex').expanduser()
    return codex / 'skills' / 'talking-head-studio'


def stop_legacy_windows(data, target, record):
    """V2.0.2 on Windows has no shutdown endpoint."""
    if os.name != 'nt':
        raise RuntimeError('请先停止正在运行的旧版服务，再更新 Skill。')
    url = record['url']
    pid = int(record['pid'])
    query = f'(Get-CimInstance Win32_Process -Filter "ProcessId={pid}").CommandLine | ConvertTo-Json -Compress'
    ps = ['powershell.exe', '-NoProfile', '-NonInteractive', '-Command']
    raw = subprocess.check_output(ps + [query], encoding='utf-8', errors='replace').strip()
    command = (json.loads(raw) if raw else '') or ''
    command = command.replace('\\', '/').casefold()
    if not all(value in command for value in ((target / 'scripts/server.py').as_posix().casefold(),
                                               '--data', data.as_posix().casefold())):
        raise RuntimeError('旧服务属于其他安装位置，请从原入口关闭。')
    for project in request_json(url + '/api/bootstrap')['projects']:
        jobs = request_json(url + '/api/jobs?id=' + project['id'])
        if any(job['status'] in ('running', 'queued') for job in jobs):
            raise RuntimeError('旧版还有媒体任务，请等它处理完再更新。')
    try:
        drafts = request_json(url + '/api/v2/drafts')
    except HTTPError as error:
        if error.code != 404:
            raise
        drafts = []
    if any(draft['status'] == 'running' for draft in drafts):
        raise RuntimeError('旧版还有 AI 稿件在处理，请稍候。')
    subprocess.run(ps + [f'Stop-Process -Id {pid} -ErrorAction Stop'], check=True)
    deadline = time.monotonic() + 8
    port = int(url.rsplit(':', 1)[1])
    while port_in_use(port):
        if time.monotonic() >= deadline:
            raise RuntimeError('旧服务还在退出，请稍候再更新。')
        time.sleep(.15)


def install(target, data, port, no_browser, no_launch):
    check_paths(target, data)
    if target.name != 'talking-head-studio':
        raise ValueError('Skill 安装目录的末级名称需要是 talking-head-studio。')
    if target.exists() and not (target / 'SKILL.md').is_file():
        raise ValueError('此目录已有其他内容，请选择 Skill 安装目录。')
    active = running_instance(data)
    record = instance_record(data)
    legacy = record and not record.get('id') and port_in_use(int(record['url'].rsplit(':', 1)[1]))
    own = bool(active and Path(active['code_root']).resolve() == target)
    old_port = int(active['url'].rsplit(':', 1)[1]) if own else None
    if not active and legacy and not no_launch:
        old_port = int(record['url'].rsplit(':', 1)[1])
    app_python = runtime_python(default_app_dir())
    python = app_python if app_python.is_file() else Path(sys.executable)
    url = active['url'] if active and not own else ''

    def stop():
        if own:
            stop_instance(data, target)
        elif legacy and not no_launch:
            stop_legacy_windows(data, target, record)

    def launch(use_port):
        result = subprocess.run(
            [str(python), '-X', 'utf8', str(target / 'scripts/launch.py'),
             '--data', str(data), '--port', str(use_port), '--no-browser'],
            capture_output=True, text=True, encoding='utf-8',
        )
        if result.returncode:
            raise RuntimeError(result.stderr.strip() or 'Skill 中的工作台启动失败。')
        return result.stdout.strip()

    def start():
        nonlocal url
        if not no_launch and not url:
            url = launch(port if port is not None else old_port or 8765)

    backup = replace_code(target, data / 'install-backups', lambda staged: None, stop, start,
                          lambda: launch(old_port) if own else None)
    if backup:
        print(f'旧版 Skill 备份：{backup}')
    if url and not no_launch and not no_browser:
        open_browser(url)
    print(f'已安装 Skill {VERSION}：{target}')
    if url:
        print(f'当前工作台：{url}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--target', type=Path, default=default_skill_dir())
    parser.add_argument('--data', type=Path, default=default_data_dir())
    parser.add_argument('--port', type=int)
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--no-launch', action='store_true')
    args = parser.parse_args()
    if args.port is not None and not 0 <= args.port <= 65535:
        parser.error('端口必须在 0–65535 之间。')
    configure_tool_path()
    try:
        install(args.target.expanduser().resolve(), args.data.expanduser().resolve(),
                args.port, args.no_browser, args.no_launch)
    except (ValueError, OSError, RuntimeError, subprocess.CalledProcessError) as exc:
        parser.exit(1, f'Skill 安装未完成：{exc}\n')


if __name__ == '__main__':
    main()
