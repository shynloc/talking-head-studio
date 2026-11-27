"""Test copied annotations from selection to the two outputs that may be read aloud."""
import argparse
import json
import re
import subprocess
import sys
import time
from pathlib import Path
from zipfile import ZipFile

from playwright.sync_api import expect, sync_playwright

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
from agent_client import AgentClient
from media import subtitles


def run(url, out):
    out.mkdir(parents=True, exist_ok=True)
    first = '今天试一套录音流程（只用桌面设备）。'
    second = '先把麦克风靠近。我们试一段声音。'
    third = '最后把电量从20%充到80%。'
    fourth = '这一句留给我直接说。'
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel='msedge')
        ctx = browser.new_context(viewport={'width': 1440, 'height': 980}, reduced_motion='reduce',
                                  permissions=['clipboard-read', 'clipboard-write'])
        page = ctx.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(url + '/motion/index.html')
        page.locator('#search').fill('FX-001')
        page.locator('#cards .pick').click()
        page.locator('#copy-to-script').click()
        fx = page.evaluate('navigator.clipboard.readText()')
        assert re.match(r'（画面：.*FX-001', fx)
        page.locator('#nav-visual').click()
        frame = page.frame_locator('#visual-frame')
        frame.locator('#asset-search').fill('OBJ-017@PAL-013')
        frame.locator('[data-asset-id="OBJ-017"]').click()
        expect(frame.locator('#detail code')).to_have_text('OBJ-017@PAL-013')
        page.locator('#copy-to-script').click()
        objects = page.evaluate('navigator.clipboard.readText()')
        assert 'OBJ-017@PAL-013' in objects and 'STK-026@PAL-013' in objects
        manuscript = '\n\n'.join([
            first,
            second + '\n' + objects + '\n' + fx[:-1] + '说到「试一段声音」时出现。）',
            third,
            fourth + '（画面：无）',
        ])
        (out/'同一篇口播稿.txt').write_text(manuscript, encoding='utf8')
        page.locator('#nav-example').click()
        expect(page.locator('#manuscript')).to_be_editable()
        page.locator('#agent-mode').select_option('workbuddy')
        page.locator('#manuscript').fill(manuscript)
        expect(page.locator('#annotations-status')).to_contain_text('2 处')
        fixed = page.locator('[data-annotation="specified"]')
        none = page.locator('[data-annotation="none"]')
        expect(fixed).to_contain_text(second)
        expect(fixed).to_contain_text('说到「试一段声音」时出现')
        expect(none).to_contain_text('纯口播')
        expect(none.locator('.accept')).to_have_count(0)
        fixed.get_by_text('查看素材编号').click()
        expect(fixed).to_contain_text('FX-001')
        expect(fixed.locator('canvas')).to_be_visible()
        page.wait_for_function("""Array.from(document.querySelector('[data-annotation=specified] canvas')
              .getContext('2d').getImageData(0,0,720,270).data).some((v,i)=>i%4===3&&v>127)""")
        fixed.locator('.accept').click()
        expect(fixed.locator('.accept')).to_have_attribute('aria-pressed', 'true')

        page.locator('#recommend').click()
        page.wait_for_function('!!state.review?.taskId')
        task = page.evaluate('state.review.taskId')
        client = AgentClient(url, 'workbuddy')
        claim = client.claim(task)
        data = claim['context']
        assert data['eligibleSentences'] == [0, 3]
        assert data['sentences'] == [first, '先把麦克风靠近。', '我们试一段声音。', third, fourth]
        assert '画面：' not in data['manuscript']
        # Even if a host returns blocked lines, the server only accepts the eligible recommendation.
        rows = [dict(sentence=i, ids=['FX-001'], title='电量对比', reason='强调电量变化。') for i in [1, 4, 3]]
        client.complete(task, claim['receipt'], json.dumps({'recommendations': rows}, ensure_ascii=False))
        page.wait_for_function("state.review?.status==='ready'")
        expect(page.locator('.review-card')).to_have_count(3)
        expect(fixed.locator('.accept')).to_have_attribute('aria-pressed', 'true')
        page.locator('[data-sentence="3"] .accept').click()
        expect(page.locator('#export-choices')).to_contain_text('2 款')
        page.locator('#picks').screenshot(path=str(out/'三种标注在原句卡.png'))
        page.reload()
        expect(fixed.locator('.accept')).to_have_attribute('aria-pressed', 'true')
        with page.expect_download(timeout=90000) as dl:
            page.locator('#export-choices').click()
        pack = out/'同一篇稿-透明素材包.zip'
        dl.value.save_as(pack)
        with ZipFile(pack) as archive:
            items = json.loads(archive.read('素材搭配.json'))['items']
            explicit = next(item for item in items if item.get('binding'))
            assert explicit['quote'] == second
            assert explicit['binding']['cue'] == '试一段声音'
            assert explicit['variantIds']['objects'] == 'OBJ-017@PAL-013'
            assert explicit['assetRefs']['effects'] == ['FX-001']
            assert any(name.endswith('.glb') for name in explicit['packageSources'])
            assert [item['quote'] for item in items if item is not explicit] == [third]
            assert fourth not in archive.read('原句对照.txt').decode()

        token = ctx.request.get(url+'/api/bootstrap').json()['token']
        def api(path, data=None):
            response = (ctx.request.get(url+path) if data is None else
                        ctx.request.post(url+path, data=data, headers={'X-Studio-Token': token}))
            assert response.ok, response.text()
            return response.json()

        draft = api('/api/v2/draft', {'title': '同一篇稿·标注验证', 'text': manuscript})
        project = api('/api/v2/create', {'id': draft['id']})
        pid = project['id']
        assert project['source_text'] == manuscript
        assert ''.join(p['text'] for p in project['pages']) == first+second+third+fourth
        prompt = ctx.new_page()
        prompt.on('pageerror', lambda error: errors.append(str(error)))
        prompt.goto(url + '/prompter?id=' + pid)
        expect(prompt.locator('#page')).to_contain_text(first)
        seen = ''
        for i in range(len(project['pages'])):
            if i:
                prompt.locator('#next-btn').click()
            expect(prompt.locator('#page')).to_contain_text(project['pages'][i]['sentences'][0]['text'])
            seen += prompt.locator('#page').inner_text()
        assert '画面：' not in seen and 'FX-001' not in seen and fourth in seen

        fixture = out/'字幕测试片.mp4'
        subprocess.run(['ffmpeg','-v','error','-f','lavfi','-i','color=c=navy:s=160x240:r=12:d=8',
                        '-c:v','libx264','-pix_fmt','yuv420p','-y',str(fixture)], check=True)
        srt = out/'带标注的输入字幕.srt'
        cues = [first, second+'\n'+objects+'\n'+fx, third, fourth+'（画面：无）']
        srt.write_text('\n\n'.join(
            f'{i+1}\n00:00:0{i*2},000 --> 00:00:0{i*2+1},900\n{cue}' for i,cue in enumerate(cues)
        )+'\n', encoding='utf8')
        def job(action, args=None):
            ref = api('/api/action', {'project_id': pid, 'action': action, 'args': args or {}})
            until = time.monotonic() + 60
            while time.monotonic() < until:
                result = next(j for j in api('/api/jobs?id='+pid) if j['id']==ref['id'])
                if result['status'] not in {'running','queued'}:
                    assert result['status'] == 'done', result
                    return
                time.sleep(.15)
            raise TimeoutError(action)

        job('import_media', {'path': str(fixture)})
        job('skip_rough')
        job('captions_from_file', {'path': str(srt)})
        cuts = api('/api/project?id='+pid)
        assert [cap['text'] for cap in cuts['captions']] == [first,second,third,fourth]
        subtitles(cuts, out, 160, 240)
        for suffix in ['srt','ass']:
            output = (out/f'captions.{suffix}').read_text(encoding='utf-8-sig')
            assert '画面：' not in output and 'OBJ-017' not in output and fourth in output
        assert not errors, errors
        browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--out', required=True, type=Path)
    args = parser.parse_args()
    run(args.url, args.out.resolve())
    print('Copied IDs, locked paragraph, pure speech, eligible Agent reply, MOV pack, prompter and SRT/ASS passed.')
