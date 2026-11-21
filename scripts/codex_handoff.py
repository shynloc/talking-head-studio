"""Link a specific local Codex thread and submit via its native queue."""

import json
import queue
import re
import shutil
import subprocess
import threading
import time
from pathlib import Path


def windows_background():
    return {'creationflags': getattr(subprocess, 'CREATE_NO_WINDOW', 0)}


class CodexHandoff:
    def __init__(self, binary=None, env=None):
        self.binary = binary or shutil.which('codex')
        self.env = env

    def available(self):
        return bool(self.binary)

    def verify(self, thread_id):
        if not isinstance(thread_id, str) or not re.fullmatch(
                r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', thread_id, re.I):
            raise ValueError('请从要连接的本机 Codex 对话执行连接指令。')
        if not self.binary:
            raise ValueError('这台电脑的工作台没有找到 Codex 命令。可先用任务卡。')

        with subprocess.Popen([self.binary, 'app-server', '--listen', 'stdio://'],
                              stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                              text=True, encoding='utf-8', errors='replace', env=self.env,
                              **windows_background()) as server:
            messages = queue.Queue()

            def read():
                for line in server.stdout:
                    try:
                        messages.put(json.loads(line))
                    except json.JSONDecodeError:
                        continue
                messages.put(None)

            threading.Thread(target=read, daemon=True).start()

            def send(message):
                server.stdin.write(json.dumps(message) + '\n')
                server.stdin.flush()

            def rpc(number, method, params):
                send({'id': number, 'method': method, 'params': params})
                deadline = time.monotonic() + 8
                while time.monotonic() < deadline:
                    message = messages.get(timeout=max(.01, deadline - time.monotonic()))
                    if message is None:
                        break
                    if message.get('id') == number and 'method' not in message:
                        if 'result' in message:
                            return message['result']
                        break
                raise ValueError('本机 Codex 无法验证此对话。请确认正在使用原来的账号和项目。')

            try:
                rpc(1, 'initialize', {'clientInfo': {'name': 'talking-head-studio', 'version': '0.1'}})
                send({'method': 'initialized'})
                reply = rpc(2, 'thread/read', {'threadId': thread_id, 'includeTurns': False})
                thread = reply['thread']
                if thread.get('id') != thread_id or not thread.get('cwd'):
                    raise ValueError('Codex 返回了不同的对话，工作台未连接。')
                return {'thread_id': thread_id, 'cwd': thread['cwd']}
            except (KeyError, OSError, queue.Empty) as exc:
                raise ValueError('无法验证原 Codex 对话，可在该对话粘贴任务卡继续。') from exc
            finally:
                if server.poll() is None:
                    server.terminate()

    def queue(self, binding, card):
        try:
            checked = self.verify(binding['thread_id'])
        except (OSError, ValueError):
            return 'manual'
        directory = Path(binding['cwd'])
        if checked != binding or not directory.is_dir():
            return 'manual'
        try:
            result = subprocess.run([self.binary, 'queue', '--thread', binding['thread_id'],
                                     '--message', card, '--resume'], cwd=directory, env=self.env,
                                    stdin=subprocess.DEVNULL, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=True, encoding='utf-8', errors='replace', timeout=25,
                                    **windows_background())
        except subprocess.TimeoutExpired:
            return 'unconfirmed'
        # The native CLI may queue successfully even when activating the thread fails.
        return 'queued' if result.returncode == 0 else 'manual'
