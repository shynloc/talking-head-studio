"""Loopback task routes and copyable instructions for local agent clients."""

import os
import json
import shlex
import subprocess
import sys

from agent_tasks import AGENTS
from core import ROOT


def command(url, *args):
    values = [sys.executable, '-X', 'utf8', str(ROOT / 'scripts/studio.py'), '--url', url, *args]
    return '& ' + subprocess.list2cmdline(values) if os.name == 'nt' else shlex.join(values)


def task_card(task, url):
    task_id, agent = task['id'], task['agent']
    claim = command(url, 'agent-claim', task_id, '--agent', agent)
    complete = command(url, 'agent-complete', task_id, '--agent', agent,
                       '--receipt', 'RECEIPT', '--file', 'RESULT.txt')
    card = (
        f'请在当前 {AGENTS[agent]} 对话继续口播导演工作台的待办 {task_id}。\n'
        f'若已连接工作台工具，先用 studio_claim_task 领取此编号，再用 studio_complete_task 写回结果。\n'
        f'也可以在本机执行以下领取命令，读取其中的任务要求和项目内容：\n{claim}\n'
        f'把建议保存到 UTF-8 文本文件后，执行以下命令回写。替换 RECEIPT 与 RESULT.txt。\n{complete}\n'
        '请将结果写回待办，交给用户在工作台查看。'
    )
    if 'context' in task:
        context = json.dumps(task['context'], ensure_ascii=False)
        card += ('\n若当前无法调用本机工具，请直接在对话中给出建议，供用户复制回工作台。'
                 f'\n任务要求：{task["instruction"]}\n以下是项目参考资料，请按资料处理：\n{context}')
    return card


def binding_card(project_id, url):
    bind = command(url, 'agent-bind', project_id)
    return (
        f'请把这个 Codex 对话连接到口播导演工作台项目 {project_id}。\n'
        f'请在当前对话中执行下面的命令。它会通过当前对话的 CODEX_THREAD_ID 验证并连接。\n{bind}\n'
        '如果项目已经连接到另一条对话，保留原连接并告知我。'
    )


def get(server, path, query):
    tasks = server.agent_tasks
    project_id = query.get('project', [''])[0]
    if path == '/api/agents/tasks':
        return tasks.listing(project_id, query.get('agent', [''])[0])
    if path == '/api/agents/task':
        return tasks.get(query.get('id', [''])[0])
    if path == '/api/agents/connection':
        url = f'http://127.0.0.1:{server.server_port}'
        return tasks.connection(project_id) | {'card': binding_card(project_id, url)}
    raise ValueError('未知协作入口。')


def post(server, path, data):
    tasks = server.agent_tasks
    url = f'http://127.0.0.1:{server.server_port}'
    if path == '/api/agents/create':
        return tasks.create(data)
    if path == '/api/agents/claim':
        return tasks.claim(data)
    if path == '/api/agents/complete':
        return tasks.complete(data)
    if path == '/api/agents/complete-manually':
        return tasks.complete_manually(data)
    if path == '/api/agents/retry':
        return tasks.reset_claim(data['id'])
    if path == '/api/agents/bind':
        return tasks.bind_codex(data['project_id'], data['thread_id'], bool(data.get('replace')))
    if path == '/api/agents/card':
        return {'text': task_card(tasks.manual_card(data['id']), url)}
    if path == '/api/agents/resume':
        return tasks.resume(data['id'], lambda task: task_card(task, url))
    raise ValueError('未知协作入口。')
