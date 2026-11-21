"""Exercise the workbench and real CLI/MCP processes against an isolated data directory."""

import argparse
import json
import subprocess
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


ROOT = Path(__file__).resolve().parents[1]


def mcp(url, agent, calls):
    messages = [{'jsonrpc': '2.0', 'id': 1, 'method': 'initialize',
                 'params': {'protocolVersion': '2025-06-18', 'clientInfo': {'name': 'qa', 'version': '1'}}},
                {'jsonrpc': '2.0', 'method': 'notifications/initialized'}]
    messages.extend({'jsonrpc': '2.0', 'id': index, 'method': 'tools/call',
                     'params': {'name': name, 'arguments': arguments}}
                    for index, (name, arguments) in enumerate(calls, 2))
    output = subprocess.check_output(
        [sys.executable, str(ROOT / 'scripts/agent_mcp.py'), '--agent', agent, '--url', url],
        input=''.join(json.dumps(item) + '\n' for item in messages).encode(), timeout=30,
    )
    items = [json.loads(line) for line in output.decode('utf-8').splitlines()]
    assert items[0]['result']['protocolVersion'] == '2025-06-18'
    assert all(not item['result'].get('isError') for item in items[1:]), items
    return [json.loads(item['result']['content'][0]['text']) for item in items[1:]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    checks, errors = [], []

    def cli(operation, *values):
        output = subprocess.check_output(
            [sys.executable, '-X', 'utf8', str(ROOT / 'scripts/studio.py'), '--url', args.url, operation, *values],
            timeout=30,
        )
        return json.loads(output.decode('utf-8'))

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1180, 'height': 780})
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(args.url)
        page.get_by_role('button', name='新建项目').click()
        page.locator('#page-text').fill('这是独立的测试口播稿。')
        page.locator('#agent-inbox').click()

        def create(agent, instruction):
            page.locator('#dialog [data-agent="compose"]').click()
            page.locator('#agent-choice').select_option(agent)
            page.locator('#agent-instruction').fill(instruction)
            page.get_by_role('button', name='存为待办').click()
            expect(page.locator('.agent-task-status strong')).to_have_text('等 AI 领取')
            return page.evaluate('agentView.id')

        task_id = create('workbuddy', '帮我把开头改得自然一点。')
        expect(page.locator('[data-agent="resume"]')).to_have_count(0)
        page.get_by_role('button', name='复制任务卡').click()
        expect(page.locator('#agent-copy-area')).to_contain_text('原来的 WorkBuddy 对话')
        assert '独立的测试口播稿' in page.locator('#agent-copy-area textarea').input_value()
        found, claim = mcp(args.url, 'workbuddy',
                           [('studio_list_tasks', {}), ('studio_claim_task', {'id': task_id})])
        assert any(item['id'] == task_id for item in found)
        assert claim['context']['pages'][0]['text'] == '这是独立的测试口播稿。'
        expect(page.locator('.agent-task-status strong')).to_have_text('AI 已领取', timeout=7000)
        result = '建议改成「今天想和你分享一个小技巧。」'
        mcp(args.url, 'workbuddy',
            [('studio_complete_task', {'id': task_id, 'receipt': claim['receipt'], 'result': result})])
        expect(page.locator('.agent-result')).to_have_text(result, timeout=7000)
        assert '这是独立的测试口播稿' in page.locator('#page-text').input_value()
        page.screenshot(path=str(args.out / '01-结果已回来.png'))
        checks.append('WorkBuddy-compatible stdio MCP claims a browser-created task and returns a visible suggestion')

        page.locator('#dialog [data-agent="list"]').click()
        task_id = create('codex', '帮我检查字幕里的专有名词。')
        expect(page.get_by_role('button', name='连接 Codex 原对话')).to_be_visible()
        expect(page.locator('[data-agent="resume"]')).to_have_count(0)
        claim = cli('agent-claim', task_id, '--agent', 'codex')
        suggestion = args.out / 'result.txt'
        suggestion.write_text('建议保持原稿的称呼。', encoding='utf-8')
        cli('agent-complete', task_id, '--agent', 'codex', '--receipt', claim['receipt'], '--file', str(suggestion))
        expect(page.locator('.agent-result')).to_have_text('建议保持原稿的称呼。', timeout=7000)
        checks.append('unlinked Codex keeps its task for manual pickup and the local CLI writes the result back')

        page.locator('#dialog [data-agent="list"]').click()
        task_id = create('workbuddy', '请给出一条手动协作建议。')
        page.get_by_role('button', name='粘贴 AI 的结果').click()
        page.locator('#agent-pasted-result').fill('手动保存的建议。')
        page.get_by_role('button', name='保存结果').click()
        expect(page.locator('.agent-result')).to_have_text('手动保存的建议。')
        page.reload()
        page.locator('#agent-inbox').click()
        page.locator(f'[data-task="{task_id}"]').click()
        expect(page.locator('.agent-result')).to_have_text('手动保存的建议。')
        checks.append('a user can paste a result from the original chat and reopen it after reload')
        browser.close()

    assert not errors, errors
    result = {'status': 'PASS', 'checks': checks}
    (args.out / 'results.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
