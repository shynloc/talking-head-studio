"""Use only the active local workbench when calling handoff operations."""

from urllib.parse import urlencode, urlparse

from agent_tasks import agent_key
from launch import request_json


class AgentClient:
    def __init__(self, url, agent):
        address = urlparse(url)
        if (address.scheme != 'http' or address.hostname not in ('127.0.0.1', 'localhost')
                or address.username or address.password or address.path not in ('', '/')
                or address.query or address.fragment or not address.port):
            raise ValueError('请输入本机工作台地址，例如 http://127.0.0.1:8765。')
        self.url = 'http://127.0.0.1:' + str(address.port)
        self.agent = agent_key(agent)

    def _call(self, route, payload=None, query=None):
        token = request_json(self.url + '/api/bootstrap')['token']
        path = self.url + '/api/agents/' + route
        if query:
            path += '?' + urlencode(query)
        return request_json(path, payload, token, timeout=20 if route == 'bind' else 5)

    def list(self):
        return self._call('tasks', query={'agent': self.agent})

    def claim(self, task_id):
        return self._call('claim', {'id': task_id, 'agent': self.agent})

    def complete(self, task_id, receipt, result):
        return self._call('complete', {'id': task_id, 'agent': self.agent, 'receipt': receipt, 'result': result})

    def bind(self, project_id, thread_id, replace=False):
        if self.agent != 'codex':
            raise ValueError('此连接指令用于 Codex。请在工作台选择对应助手的原对话入口。')
        return self._call('bind', {'project_id': project_id, 'thread_id': thread_id, 'replace': replace})
