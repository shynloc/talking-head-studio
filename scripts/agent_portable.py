"""Portable text handoffs. Live credentials and chat destinations stay local."""

import math
import json

from agent_hosts import AGENTS
from core import digest, now, uid, write_json


def task_paths(store):
    yield from (store.root / 'agent-tasks').glob('handoff_*.json')
    yield from store.root.glob('project_*/agent-tasks/handoff_*.json')


def export_tasks(store, project_id):
    tasks = []
    for path in task_paths(store):
        task = json.loads(path.read_text(encoding='utf-8'))
        if (task['project_id'] != project_id or task.get('kind') in ('motion', 'production')
                or task.get('request_id', '').startswith('chatcut-')
                or task['status'] not in ('waiting', 'claimed', 'ready')):
            continue
        row = {
            key: task[key] for key in ('agent', 'instruction', 'included', 'context', 'created')
        }
        if task['status'] == 'ready':
            row['result'] = task['result']
        tasks.append(row)
    return {'tasks': tasks}


def _text(value, limit=120000):
    if not isinstance(value, str) or len(value) > limit:
        raise ValueError('工程包内有无效的待办文字。')
    return value


def _context(raw, included):
    if not isinstance(raw, dict):
        raise ValueError('工程包内有无效的待办资料。')
    context = {'title': _text(raw.get('title', ''))}
    for group in included:
        rows = raw.get(group)
        if not isinstance(rows, list) or any(not isinstance(row, dict) for row in rows):
            raise ValueError('工程包内有无效的待办资料。')
        if group == 'pages':
            context[group] = [{key: _text(row.get(key, '')) for key in ('title', 'text', 'notes')} for row in rows]
        else:
            captions = []
            for row in rows:
                start, end = row.get('start'), row.get('end')
                if (any(type(v) not in (int, float) or not math.isfinite(v) for v in (start, end))
                        or not 0 <= start <= end):
                    raise ValueError('工程包内有无效的待办字幕时间。')
                captions.append({'start': start, 'end': end, 'text': _text(row.get('text', ''))})
            context[group] = captions
    return context


def import_tasks(snapshot, project, staging):
    rows = snapshot.get('tasks')
    if not isinstance(rows, list):
        raise ValueError('工程包内的待办清单格式不正确。')
    for row in rows:
        if not isinstance(row, dict) or not isinstance(row.get('agent'), str) or row['agent'] not in AGENTS:
            raise ValueError('工程包内有无法识别的助手。')
        included = row.get('included')
        if not isinstance(included, list) or any(name not in ('pages', 'captions') for name in included):
            raise ValueError('工程包内有无效的待办资料范围。')
        instruction = _text(row.get('instruction'), 4000)
        result = _text(row['result']) if 'result' in row else None
        if not instruction.strip() or (result is not None and not result.strip()):
            raise ValueError('工程包内的待办内容为空。')
        context = _context(row.get('context'), included)
        task = {
            'id': uid('handoff'), 'project_id': project['id'], 'project_title': project['title'],
            'project_version': project['version'], 'included': included, 'context': context,
            'context_hash': digest(context), 'agent': row['agent'], 'instruction': instruction,
            'created': _text(row.get('created', ''), 80) or now(), 'updated': now(),
            'status': 'waiting' if result is None else 'ready', 'delivery': 'manual',
        }
        if result is None:
            task['needs_handoff'] = True
        else:
            task['result'] = result
        write_json(staging / 'agent-tasks' / (task['id'] + '.json'), task)
    return len(rows)
