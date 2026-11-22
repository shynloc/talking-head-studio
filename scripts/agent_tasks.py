"""Persistent project handoffs. Results are suggestions until a user applies them."""

import json
import re
import secrets
import threading
from concurrent.futures import ThreadPoolExecutor

from core import Conflict, digest, now, uid, write_json


from agent_hosts import AGENTS


def text_value(value, label, limit):
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise ValueError(f'{label}需要填写，最多 {limit} 个字符。')
    return value.strip()


def agent_key(value):
    if value not in AGENTS:
        raise ValueError('请选择列表中的助手。')
    return value


def project_context(project, included=None):
    context = {
        'title': project['title'],
        'pages': [{key: page.get(key, '') for key in ('title', 'text', 'notes')} for page in project['pages']],
        'captions': [{key: caption[key] for key in ('start', 'end', 'text')} for caption in project['captions']],
    }

    return context if included is None else {key:value for key,value in context.items() if key=='title' or key in included}


class AgentTasks:
    def __init__(self, store, codex):
        self.store = store
        self.root = store.root / 'agent-tasks'
        self.root.mkdir(exist_ok=True)
        self.lock = threading.RLock()
        self.pool = ThreadPoolExecutor(max_workers=1)
        self.codex = codex
        for path in self.root.glob('handoff_*.json'):
            task = json.loads(path.read_text(encoding='utf-8'))
            if task['delivery'] == 'sending':
                task['delivery'] = 'unconfirmed'
                self._save(task)

    def _path(self, task_id):
        if not isinstance(task_id, str) or not re.fullmatch(r'handoff_[0-9a-f]{12}', task_id):
            raise ValueError('无效的任务编号。')
        return self.root / (task_id + '.json')

    def _get(self, task_id):
        path = self._path(task_id)
        if not path.is_file():
            raise ValueError('找不到这个待办。')
        return json.loads(path.read_text(encoding='utf-8'))

    def _save(self, task):
        task['updated'] = now()
        write_json(self._path(task['id']), task)

    def _public(self, task, detail=True):
        public = {k: v for k, v in task.items() if k not in ('claim', 'context', 'binding', 'request_id', 'context_hash')}
        if not detail:
            public.pop('result', None)
        if detail and task['status'] == 'ready':
            try:
                project = self.store.load(task['project_id'])
                public['project_changed'] = digest(project_context(project,task.get('included'))) != task['context_hash']
            except FileNotFoundError:
                public['project_changed'] = True
        return public

    def listing(self, project_id='', agent=''):
        if agent:
            agent_key(agent)
        with self.lock:
            tasks = [json.loads(path.read_text(encoding='utf-8')) for path in self.root.glob('handoff_*.json')]
            return [self._public(task, detail=False) for task in sorted(tasks, key=lambda x: x['updated'], reverse=True)
                    if (not project_id or task['project_id'] == project_id) and (not agent or task['agent'] == agent)]

    def get(self, task_id):
        with self.lock:
            return self._public(self._get(task_id))

    def manual_card(self, task_id):
        with self.lock:
            task = self._get(task_id)
            return self._public(task) | {'context': task['context']}

    def _binding_path(self, project_id):
        self.store.folder(project_id)
        return self.root / (f'{project_id}-codex.json')

    def _binding(self, project_id):
        path = self._binding_path(project_id)
        return json.loads(path.read_text(encoding='utf-8')) if path.is_file() else None

    def connection(self, project_id):
        with self.lock:
            binding = self._binding(project_id)
            return {'codex_bound': bool(binding), 'codex_available': self.codex.available()}

    def bind_codex(self, project_id, thread_id, replace=False):
        self.store.load(project_id)
        binding = self.codex.verify(thread_id)
        with self.lock:
            old = self._binding(project_id)
            if old and old['thread_id'] != binding['thread_id'] and not replace:
                raise Conflict('这个项目已有原对话。确认换成当前对话后再重新连接。')
            write_json(self._binding_path(project_id), binding)
        return {'connected': True, 'agent': 'codex'}

    def create(self, data):
        project = self.store.load(data['project_id'])
        agent = agent_key(data.get('agent'))
        instruction = text_value(data.get('instruction'), '任务内容', 4000)
        request_id = text_value(data.get('request_id'), '提交编号', 80)
        with self.lock:
            for path in self.root.glob('handoff_*.json'):
                task = json.loads(path.read_text(encoding='utf-8'))
                if task['project_id'] == project['id'] and task.get('request_id') == request_id:
                    return self._public(task)
            included=data.get('included',['pages','captions'])
            if not isinstance(included,list) or any(k not in ('pages','captions') for k in included):
                raise ValueError('请选择要交给助手的稿件或字幕。')
            context = project_context(project,included)
            task = {
                'id': uid('handoff'), 'request_id': request_id, 'project_id': project['id'],
                'project_title': project['title'], 'project_version': project['version'],
                'included':included,'context': context, 'context_hash': digest(context), 'agent': agent,
                'instruction': instruction, 'status': 'waiting', 'delivery': 'manual', 'created': now(),
            }
            self._save(task)
            return self._public(task)

    def claim(self, data):
        agent = agent_key(data.get('agent'))
        with self.lock:
            task = self._get(data['id'])
            if task['agent'] != agent:
                raise Conflict(f"这条待办由 {AGENTS[task['agent']]} 领取。")
            if task['status'] != 'waiting':
                raise Conflict('这条待办已领取或已有结果。可在工作台查看。')
            receipt = secrets.token_urlsafe(24)
            task.update(status='claimed', claim=receipt)
            self._save(task)
            return self._public(task) | {'receipt': receipt, 'context': task['context']}

    def complete(self, data):
        agent = agent_key(data.get('agent'))
        result = text_value(data.get('result'), '处理结果', 120000)
        with self.lock:
            task = self._get(data['id'])
            receipt = data.get('receipt')
            claim = task.get('claim')
            if task['agent'] != agent or not claim or not isinstance(receipt, str) or not secrets.compare_digest(receipt, claim):
                raise Conflict('领取凭证已失效，请从工作台重新领取。')
            if task['status'] == 'ready' and task['result'] == result:
                return self._public(task)
            if task['status'] != 'claimed':
                raise Conflict('这条待办已有结果。')
            task.update(status='ready', result=result)
            self._save(task)
            return self._public(task)

    def complete_manually(self, data):
        result = text_value(data.get('result'), '处理结果', 120000)
        with self.lock:
            task = self._get(data['id'])
            if task['status'] == 'ready' or task['delivery'] == 'sending':
                raise Conflict('待办已有结果或正在投递，请刷新后查看。')
            task.pop('claim', None)
            task.update(status='ready', result=result, manual_result=True)
            self._save(task)
            return self._public(task)

    def reset_claim(self, task_id):
        with self.lock:
            task = self._get(task_id)
            if task['status'] != 'claimed' or task['delivery'] == 'sending':
                raise Conflict('当前待办不能重新领取。')
            task.pop('claim', None)
            task.update(status='waiting', delivery='manual')
            self._save(task)
            return self._public(task)

    def resume(self, task_id, make_card):
        with self.lock:
            task = self._get(task_id)
            if task['status'] != 'waiting' or task['delivery'] in ('sending', 'queued', 'unconfirmed', 'fallback'):
                return self._public(task)
            binding = self._binding(task['project_id']) if task['agent'] == 'codex' else None
            if not binding or not self.codex.available():
                return self._public(task)
            task['delivery'] = 'sending'
            self._save(task)
            self.pool.submit(self._dispatch, task_id, binding, make_card(task))
            return self._public(task)

    def has_dispatches(self):
        with self.lock:
            return any(json.loads(path.read_text(encoding='utf-8'))['delivery'] == 'sending'
                       for path in self.root.glob('handoff_*.json'))

    def _dispatch(self, task_id, binding, card):
        try:
            delivery = self.codex.queue(binding, card)
        except (OSError, ValueError, RuntimeError):
            delivery = 'unconfirmed'
        with self.lock:
            task = self._get(task_id)
            task['delivery'] = 'fallback' if delivery == 'manual' else delivery
            self._save(task)
