"""Project-bound chat destinations. Only the creator chooses when to open a chat."""
from urllib.parse import urlsplit
from uuid import UUID
from core import write_json
import json
import re


HOSTS = {
    'codex': {'name':'Codex', 'cli':'codex'},
    'workbuddy': {'name':'WorkBuddy'},
    'claude-code': {'name':'Claude Code', 'cli':'claude'},
    'claude-desktop': {'name':'Claude 客户端', 'home':'https://claude.ai/new', 'host':'claude.ai', 'prefix':'chat'},
    'chatgpt': {'name':'ChatGPT', 'home':'https://chatgpt.com/', 'host':'chatgpt.com', 'prefix':'c', 'cloud':True},
    'grok': {'name':'Grok Bot', 'home':'https://grok.com/', 'host':'grok.com', 'prefix':'c', 'cloud':True},
    'trae': {'name':'TRAE'},
    'traework': {'name':'TraeWork'},
    'other': {'name':'其他助手', 'cloud':True},
}
AGENTS = {key: host['name'] for key, host in HOSTS.items()}


def destination(value, agent):
    config = HOSTS[agent]
    if not isinstance(value,str) or len(value)>2048:raise ValueError('请填写有效的原对话地址。')
    value = value.strip()
    if not value:
        return ''
    if agent == 'claude-code':
        try:
            return str(UUID(value))
        except ValueError:
            raise ValueError('请填写原 Claude Code 会话的完整 ID。') from None
    link = urlsplit(value)
    if (not config.get('host') or link.scheme != 'https' or link.netloc != config['host']
            or not re.fullmatch('/' + config['prefix'] + '/[a-zA-Z0-9_-]{4,150}/?', link.path)):
        raise ValueError('请粘贴这个助手中原对话的地址。分享链接和首页不能定位原对话。')
    return 'https://' + config['host'] + link.path.rstrip('/')


def project_destination(tasks, pid, agent, new_value=None):
    tasks.store.load(pid)
    path = tasks.store.folder(pid) / 'local-chat-links.json'
    with tasks.lock:
        values = json.loads(path.read_text(encoding='utf-8')) if path.is_file() else {}
        if new_value is not None:
            values[agent] = destination(new_value, agent)
            write_json(path, values)
        # These local links do not travel in a portable project.
        return values.get(agent, '')
