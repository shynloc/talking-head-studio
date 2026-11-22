"""A local stdio MCP bridge exposing only workbench handoff operations."""

from agent_hosts import AGENTS
import argparse
import json
import sys
from urllib.error import HTTPError

from agent_client import AgentClient


def tool(name, description, fields):
    return {
        'name': name, 'description': description,
        'inputSchema': {'type': 'object', 'properties': {key: {'type': 'string'} for key in fields},
                        'required': list(fields), 'additionalProperties': False},
    }


TOOLS = [
    tool('studio_list_tasks', '查看分配给这个 Agent 的口播工作台待办。', ()),
    tool('studio_claim_task', '领取指定待办，读取用户要求和创建时的稿件、字幕，返回回写凭证。', ('id',)),
    tool('studio_complete_task', '用领取凭证把文字建议交回工作台，供用户检查。', ('id', 'receipt', 'result')),
]
VERSIONS = {'2024-11-05', '2025-03-26', '2025-06-18'}


def handle(client, message):
    if 'id' not in message:
        return None
    reply = {'jsonrpc': '2.0', 'id': message['id']}
    params = message.get('params', {})
    method = message.get('method')
    if method == 'initialize':
        requested = params.get('protocolVersion')
        reply['result'] = {'protocolVersion': requested if requested in VERSIONS else '2025-06-18',
                           'capabilities': {'tools': {}}, 'serverInfo': {'name': 'talking-head-studio', 'version': '0.1'}}
    elif method == 'ping':
        reply['result'] = {}
    elif method == 'tools/list':
        reply['result'] = {'tools': TOOLS}
    elif method == 'tools/call':
        functions = {'studio_list_tasks': client.list, 'studio_claim_task': lambda id: client.claim(id),
                     'studio_complete_task': lambda id, receipt, result: client.complete(id, receipt, result)}
        try:
            data = functions[params['name']](**params.get('arguments', {}))
            reply['result'] = {'content': [{'type': 'text', 'text': json.dumps(data, ensure_ascii=False)}]}
        except (HTTPError, OSError, ValueError, TypeError, KeyError) as exc:
            message = json.loads(exc.read()).get('error', str(exc)) if isinstance(exc, HTTPError) else str(exc)
            reply['result'] = {'isError': True, 'content': [{'type': 'text', 'text': message}]}
    else:
        reply['error'] = {'code': -32601, 'message': 'Method not found'}
    return reply


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--agent', choices=tuple(AGENTS), required=True)
    parser.add_argument('--url', default='http://127.0.0.1:8765')
    args = parser.parse_args()
    client = AgentClient(args.url, args.agent)
    sys.stdin.reconfigure(encoding='utf-8')
    sys.stdout.reconfigure(encoding='utf-8')
    for line in sys.stdin:
        try:
            message = json.loads(line)
            response = handle(client, message)
        except (ValueError, TypeError):
            response = {'jsonrpc': '2.0', 'id': None, 'error': {'code': -32700, 'message': 'Invalid message'}}
        if response is not None:
            print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == '__main__':
    main()
