"""Start, reuse, or stop the service for a particular project directory."""

import argparse
import json
import os
import re
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path

from core import ROOT
from runtime import configure_tool_path, default_data_dir


LOCAL_HTTP = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def request_json(url, payload=None, token=None):
    headers = {'X-Studio-Token': token, 'Content-Type': 'application/json'} if token else {}
    body = None if payload is None else json.dumps(payload).encode('utf-8')
    request = urllib.request.Request(url, data=body, headers=headers)
    with LOCAL_HTTP.open(request, timeout=2) as response:
        return json.load(response)


def instance_record(data):
    try:
        state = json.loads((data / 'server.json').read_text(encoding='utf-8'))
        if isinstance(state, dict) and re.fullmatch(r'http://127\.0\.0\.1:[0-9]{1,5}', state.get('url', '')):
            return state
    except (OSError, ValueError, TypeError):
        pass
    return {}


def running_instance(data):
    state = instance_record(data)
    if state.get('id'):
        try:
            live = request_json(state['url'] + '/api/instance')
            if live.get('id') == state['id']:
                return state
        except (OSError, ValueError):
            pass
    return None


def stop_instance(data, code_root=None):
    state = running_instance(data)
    if not state:
        return False
    if code_root and Path(state['code_root']).resolve() != code_root.resolve():
        raise RuntimeError('同一数据目录正由其他工作台版本使用，请先从原安装目录停止该实例。')
    url = state['url']
    try:
        token = request_json(url + '/api/bootstrap')['token']
        request_json(url + '/api/shutdown', {'id': state['id']}, token)
    except urllib.error.HTTPError as exc:
        message = json.loads(exc.read()).get('error', '工作台无法停止')
        raise RuntimeError(message) from exc
    deadline = time.monotonic() + 10
    while time.monotonic() < deadline:
        if not running_instance(data):
            return True
        time.sleep(.1)
    raise RuntimeError('工作台未能在等待时间内停止，请查看日志。')


def open_browser(url):
    if os.name == 'nt':
        for variable in ('PROGRAMFILES(X86)', 'PROGRAMFILES'):
            prefix = os.environ.get(variable)
            if not prefix:
                continue
            edge = Path(prefix) / 'Microsoft/Edge/Application/msedge.exe'
            if edge.is_file():
                subprocess.Popen([str(edge), '--new-window', url],
                                 stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                return
    webbrowser.open(url)


def port_in_use(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=.5):
            return True
    except OSError:
        return False


def start_instance(data, port):
    if state := running_instance(data):
        return state['url']
    legacy = instance_record(data)
    if legacy and not legacy.get('id') and port_in_use(int(legacy['url'].rsplit(':', 1)[1])):
        raise RuntimeError('此数据目录仍由旧版工作台使用，请先关闭旧服务或更换项目目录。')
    if port and port_in_use(port):
        raise RuntimeError(f'端口 {port} 已被其他服务使用，请用 --port 指定新的端口。')

    data.mkdir(parents=True, exist_ok=True)
    with (data / 'server.stdout.log').open('ab') as stdout, (data / 'server.stderr.log').open('ab') as stderr:
        process = subprocess.Popen(
            [sys.executable, '-X', 'utf8', '-u', str(ROOT / 'scripts/server.py'), '--data', str(data), '--port', str(port)],
            cwd=ROOT, stdout=stdout, stderr=stderr, stdin=subprocess.DEVNULL,
            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), start_new_session=os.name != 'nt',
        )
    end = time.monotonic() + 15
    while time.monotonic() < end:
        if state := running_instance(data):
            return state['url']
        if process.poll() is not None:
            break
        time.sleep(.15)
    raise RuntimeError(f'工作台启动失败，请检查 {data / "server.stderr.log"}')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data', type=Path, default=default_data_dir())
    parser.add_argument('--port', type=int, default=8765, help='0 表示由系统分配端口')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--stop', action='store_true')
    args = parser.parse_args()
    if not 0 <= args.port <= 65535:
        parser.error('端口必须在 0–65535 之间')
    configure_tool_path()
    try:
        data = args.data.expanduser().resolve()
        if args.stop:
            print('工作台已停止' if stop_instance(data) else '此项目目录没有可停止的工作台实例')
            return
        url = start_instance(data, args.port)
        if not args.no_browser:
            open_browser(url)
        print(url)
    except (OSError, RuntimeError) as exc:
        parser.exit(1, f'{exc}\n')


if __name__ == '__main__':
    main()
