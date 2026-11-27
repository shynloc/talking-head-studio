"""A real migrated edit with an inactive handoff and fresh WorkBuddy MCP receipt."""

import argparse
import json
import subprocess
import time
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from zipfile import ZipFile

from playwright.sync_api import expect, sync_playwright

from agent_browser_test import mcp
from project_migration_browser_test import open_pack


def api_client(url):
    with urlopen(url+'/api/bootstrap') as response:
        token = json.load(response)['token']

    def request(route, values=None, expected=200):
        headers = {'X-Studio-Token':token,'Content-Type':'application/json'}
        data = json.dumps(values).encode('utf-8') if values is not None else None
        try:
            response = urlopen(Request(url+route,data=data,headers=headers),timeout=30)
        except HTTPError as error:
            response = error
        with response:
            assert response.code == expected, response.read().decode('utf-8')
            return json.load(response)
    return request


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source-url',required=True)
    parser.add_argument('--source-project',required=True)
    parser.add_argument('--target-url',required=True)
    parser.add_argument('--out',required=True,type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    origin = api_client(args.source_url)
    target = api_client(args.target_url)
    pid = args.source_project

    def task(agent, instruction):
        return origin('/api/agents/create',dict(project_id=pid,agent=agent,instruction=instruction,
                    request_id='migration-'+instruction,included=['captions']))

    pending = task('workbuddy','核对迁入后的字幕')
    assert pending['id'] == task('workbuddy','核对迁入后的字幕')['id']
    old = origin('/api/agents/claim',{'id':pending['id'],'agent':'workbuddy'})
    ready = task('codex','已有的口播建议')
    origin('/api/agents/complete-manually',{'id':ready['id'],'result':'迁移前保存的建议'})
    job = origin('/api/action',{'project_id':pid,'action':'package',
                 'args':{'include_source':True,'include_tasks':True}},expected=202)
    deadline = time.monotonic()+60
    while time.monotonic()<deadline:
        status = next(j for j in origin('/api/jobs?id='+pid) if j['id']==job['id'])
        if status['status'] not in ('queued','running'):
            break
        time.sleep(.2)
    assert status['status']=='done',status
    pack = Path(status['result']['path'])
    with ZipFile(pack) as archive:
        exported = archive.read('agent-tasks.json').decode('utf-8')
        assert old['receipt'] not in exported
        assert pending['id'] not in exported
        assert len(json.loads(exported)['tasks'])==2

    with sync_playwright() as pl:
        browser = pl.chromium.launch(channel='msedge',headless=True)
        page = browser.new_page()
        page.goto(args.target_url)
        open_pack(page,pack)
        fresh = page.wait_for_function('!homeMode && P?.id',timeout=90000).json_value()
        assert fresh!=pid
        assert not target('/api/agents/connection?project='+fresh)['codex_bound']
        rows = target('/api/agents/tasks?project='+fresh)
        pending_new = next(t for t in rows if t['instruction']==pending['instruction'])
        ready_new = next(t for t in rows if t['instruction']==ready['instruction'])
        assert target('/api/agents/task?id='+ready_new['id'])['result']=='迁移前保存的建议'
        target('/api/agents/claim',{'id':pending_new['id'],'agent':'workbuddy'},expected=409)
        page.locator('.project-menu summary').click()
        page.get_by_role('button',name='项目 AI 待办').click()
        page.get_by_role('button',name='核对迁入后的字幕',exact=False).click()
        expect(page.locator('.agent-task-status strong')).to_have_text('待重新交接')
        page.get_by_role('button',name='重新交接',exact=True).click()
        expect(page.locator('.agent-task-status strong')).to_have_text('等 AI 领取')
        page.get_by_role('button',name='复制任务卡',exact=True).click()
        expect(page.get_by_role('textbox',name='可复制内容')).to_contain_text(pending_new['id'])
        claim, = mcp(args.target_url,'workbuddy',[('studio_claim_task',{'id':pending_new['id']})])
        assert 'pages' not in claim['context'] and claim['context']['captions']
        target('/api/agents/complete',{'id':pending_new['id'],'agent':'workbuddy',
               'receipt':old['receipt'],'result':'迟到的旧凭证'},expected=409)
        expect(page.locator('.agent-task-status strong')).to_have_text('AI 已领取',timeout=9000)
        result = '建议保留口播术语，改正第一句错字。'
        mcp(args.target_url,'workbuddy',[('studio_complete_task',{'id':pending_new['id'],
            'receipt':claim['receipt'],'result':result})])
        expect(page.locator('.agent-task-status strong')).to_have_text('结果已返回',timeout=9000)
        expect(page.locator('.agent-result')).to_have_text(result)
        assert origin('/api/agents/task?id='+pending['id'])['status']=='claimed'
        page.locator('#close-dialog').click()
        page.locator('[data-workflow=edit-captions]').click()
        title = '这是迁移后改过的一句字幕。'
        field = page.locator('[data-caption][data-field="text"]').first
        field.fill(title)
        field.blur()
        page.wait_for_function("(text)=>api('/api/project?id='+P.id).then(p=>p.captions[0].text===text)",arg=title)
        page.locator('[data-workflow=finish]').click()
        expect(page.locator('#finish-confirm')).to_be_visible(timeout=120000)
        with page.expect_download(timeout=180000) as download:
            page.locator('#finish-confirm').click()
        video = args.out / '迁移后新版出片.mp4'
        download.value.save_as(video)
        subprocess.run(['ffmpeg','-nostdin','-v','error','-xerror','-i',str(video),'-f','null','-'],check=True)
    print(json.dumps({'project_id':fresh,'workbuddy_result':result,'video':video.name},ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()
