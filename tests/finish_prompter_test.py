"""Exercise the real guided export and responsive prompter on an isolated server."""
import argparse
import json
import subprocess
import time
from pathlib import Path
from urllib.request import Request, urlopen
from zipfile import ZipFile

from playwright.sync_api import sync_playwright


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', required=True)
    parser.add_argument('--out', required=True)
    args = parser.parse_args()
    output = Path(args.out).resolve()
    output.mkdir(parents=True, exist_ok=True)
    checks, errors = [], []

    def api(path, payload=None):
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
        headers = {'Content-Type': 'application/json'} if body is None else {
            'Content-Type': 'application/json', 'X-Studio-Token': token}
        with urlopen(Request(args.url + path, data=body, headers=headers), timeout=30) as response:
            return json.load(response)

    token = api('/api/bootstrap')['token']
    project = api('/api/new', {'title': '成片与提词回归 · 合成素材'})
    pid = project['id']
    project_path = '/api/project?id=' + pid

    def job(action, options=None, expect_error=False):
        result = api('/api/action', {'project_id': pid, 'action': action, 'args': options or {}})
        deadline = time.monotonic() + 90
        while time.monotonic() < deadline:
            current = next(j for j in api('/api/jobs?id=' + pid) if j['id'] == result['id'])
            if current['status'] not in ('queued', 'running'):
                assert current['status'] == ('error' if expect_error else 'done'), current
                return current
            time.sleep(.25)
        raise TimeoutError(action)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge', headless=True)
        viewport = {'width': 1200, 'height': 760}
        workbench = browser.new_page(viewport=viewport)
        workbench.on('pageerror', lambda error: errors.append(str(error)))
        def open_advanced_export():
            toggle = workbench.locator('[data-tl="collapse"]')
            toggle.wait_for()
            if toggle.get_attribute('aria-expanded') == 'false':
                toggle.click()
            workbench.locator('[data-tl="final"]').click()

        workbench.goto(args.url + '/#project=' + pid)
        open_advanced_export()
        assert workbench.locator('#finish-prepare').inner_text() == '导入录制视频'
        workbench.locator('#finish-panel').screenshot(path=str(output/'01-guide.png'))
        workbench.locator('#finish-prepare').click()
        workbench.wait_for_function("document.querySelector('#dialog-title').textContent.includes('导入')")
        workbench.locator('#close-dialog').click()
        checks.append('script-only project routes from export to import video')

        fixture = output / 'fixture.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','testsrc2=s=270x360:r=12:d=4',
                        '-f','lavfi','-i','sine=frequency=440:duration=4','-c:v','libx264','-pix_fmt','yuv420p',
                        '-c:a','aac','-shortest','-y',str(fixture)],check=True)
        job('import_media', {'path': str(fixture)})
        workbench.reload()
        open_advanced_export()
        assert workbench.locator('#finish-prepare').inner_text() == '去整理视频'
        workbench.locator('#close-dialog').click()
        job('skip_rough')
        workbench.reload()
        open_advanced_export()
        assert workbench.locator('#finish-prepare').inner_text() == '按这版视频继续'
        workbench.locator('#finish-prepare').click()
        workbench.locator('#finish-generate').wait_for()
        workbench.locator('#finish-range-options summary').click()
        workbench.locator('#finish-start').fill('0.5')
        workbench.locator('#finish-duration').fill('2')
        workbench.locator('#finish-generate').click()
        workbench.locator('#finish-confirm').wait_for(timeout=90000)
        workbench.wait_for_function("document.querySelector('.finish-video').readyState >= 2")
        sample = api('/api/v2/finish?id=' + pid)
        assert sample['sample']['start'] == .5 and abs(sample['sample']['duration']-2) < .12
        assert not api(project_path)['approvals'].get('timeline')
        workbench.locator('.finish-video').evaluate('(video) => video.play()')
        workbench.wait_for_function("document.querySelector('.finish-video').currentTime > .2")
        workbench.locator('.finish-video').evaluate('(video) => video.pause()')
        workbench.screenshot(path=str(output/'02-sample-review.png'))
        workbench.locator('#finish-confirm').click()
        workbench.get_by_text('下载完整成片', exact=True).wait_for(timeout=90000)
        final = api('/api/v2/finish?id=' + pid)
        assert final['final'] and final['approved'] and final['final']['duration'] > 3.8
        assert api(project_path)['approvals']['timeline']['sample_id'] == sample['sample']['id']
        checks.append('guided rough/align/sample, playback, explicit confirmation and real final encode')

        workbench.locator('#close-dialog').click()
        state = api(project_path)
        state['timeline']['tracks']['voice'] = {'muted': True}
        api('/api/save', state)
        assert not api('/api/v2/finish?id=' + pid)['sample']
        failure = job('confirm_timeline_final', {'sample_id':sample['sample']['id'], 'hash':sample['hash']},expect_error=True)
        assert '已变化' in failure['error']
        workbench.reload()
        workbench.locator('#workflow-guide').wait_for()
        workbench.locator('[data-stage="3"]').click()
        workbench.locator('[data-workflow="finish"]').click()
        workbench.locator('#finish-generate').wait_for()
        assert workbench.locator('#finish-confirm').count() == 0
        assert '旧版' in workbench.locator('#finish-panel').inner_text()
        checks.append('changed timeline hides old confirmation and stale API confirmation is rejected')

        workbench.locator('#close-dialog').click()
        workbench.locator('#package').click()
        assert not workbench.locator('#package-source').is_checked()
        workbench.locator('#package-source').check()
        workbench.locator('#package-go').click()
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            pack = next((job for job in api('/api/jobs?id=' + pid) if job['action'] == 'package'), None)
            if pack and pack['status'] not in ('running', 'queued'):
                break
            time.sleep(.2)
        assert pack and pack['status'] == 'done', pack
        with ZipFile(pack['result']['path']) as archive:
            assert json.loads(archive.read('bundle.json'))['source_included']
            assert 'media/source.mp4' in archive.namelist()
        checks.append('workbench can request a ZIP with the original video')

        state = api(project_path)
        paragraph = '先把设备连接到电脑，再检查音量和画面。然后打开工作台，确认提词可以完整显示。'
        state['pages'][0]['text'] = paragraph * 4
        state['pages'][0]['notes'] = '原视频参考 02:33'
        state['pages'].append({**state['pages'][0], 'id':'page_overflow', 'text':paragraph*100, 'sentences':[]})
        api('/api/save',state)
        prompt = browser.new_page(viewport=viewport)
        prompt.on('pageerror',lambda error: errors.append(str(error)))
        prompt.goto(args.url + '/prompter?id=' + pid)
        expect_fit = "$('viewport').clientHeight >= $('viewport').scrollHeight-1 && $('read-more').hidden"
        prompt.wait_for_function(expect_fit)
        assert prompt.locator('#page').bounding_box()['width'] > 1100
        prompt.locator('#font').evaluate("input=>{input.value=90;input.dispatchEvent(new Event('input'))}")
        prompt.wait_for_function(expect_fit)
        prompt.screenshot(path=str(output/'03-wide-prompter.png'))
        prompt.set_viewport_size({'width':390,'height':700})
        prompt.wait_for_function(expect_fit)
        assert prompt.evaluate('document.body.scrollWidth === innerWidth')
        prompt.locator('#prompt-timeline-toggle').click()
        prompt.wait_for_function(expect_fit)
        prompt.locator('#next-btn').click()
        prompt.locator('#read-more').wait_for()
        prompt.locator('#read-more').click()
        assert prompt.locator('#viewport').evaluate('(element)=>element.scrollTop') > 0
        prompt.locator('#scroll').click()
        before = prompt.locator('#viewport').evaluate('(element)=>element.scrollTop')
        prompt.wait_for_function("(before) => $('viewport').scrollTop > before", arg=before, timeout=2000)
        prompt.locator('#scroll').click()
        prompt.locator('#prev').click()
        prompt.wait_for_function(expect_fit)
        checks.append('desktop/mobile fit, compact timeline, overflow next screen and automatic scrolling')

        exported = Path(job('prompt_export')['result']['path'])
        prompt.goto(next(exported.parent.glob('*.html')).as_uri())
        prompt.wait_for_function(expect_fit)
        checks.append('offline exported HTML has the same fit behavior')
        browser.close()
    assert not errors, errors
    result = {'status':'PASS','checks':checks,'page_errors':errors}
    (output/'results.json').write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(result,ensure_ascii=False))


if __name__ == '__main__':
    main()
