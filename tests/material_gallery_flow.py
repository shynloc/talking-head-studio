"""Use the existing gallery to pick numbered assets, review one sentence and export its exact preview."""
import argparse
from io import BytesIO
import json
import re
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
from zipfile import ZipFile

from PIL import Image
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from agent_client import AgentClient


def run(url, output):
    chosen = {'styles': 'WEB-012', 'palettes': 'PAL-013', 'objects': 'OBJ-017', 'stickers': 'STK-026'}
    script = '准备录一期播客。把桌面麦克风靠近嘴边，先试一段声音。'
    with sync_playwright() as playwright, TemporaryDirectory() as temp:
        browser = playwright.chromium.launch(channel='msedge')
        ctx = browser.new_context(viewport={'width': 1440, 'height': 960}, reduced_motion='reduce')
        page = ctx.new_page()
        errors = []
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(url + '/motion/index.html')
        page.locator('#search').fill('fx-001')
        expect(page.locator('#cards .card')).to_have_count(1)
        page.locator('#cards .pick').click()
        motion_prompt = page.locator('#prompt').input_value()
        assert 'FX-001' in motion_prompt
        page.locator('#search').fill('OBJ-017@PAL-012')
        shelf = page.frame_locator('#visual-frame')
        entry=shelf.locator('.entry[data-asset-id="OBJ-017"]')
        expect(entry).to_have_count(1)
        entry.click()
        expect(shelf.locator('#detail code')).to_have_text('OBJ-017@PAL-012')
        shelf.locator('#asset-search').fill('')
        shelf.locator('#recent-only').check()
        expect(shelf.locator('.entry[data-asset-id]')).to_have_count(8)
        for family, count in zip(['网页风格', '配色', '3D 物件', '贴纸'], [3, 3, 8, 10]):
            shelf.get_by_role('button', name=family, exact=True).click()
            expect(shelf.locator('.entry[data-asset-id]')).to_have_count(count)
        for code in chosen.values():
            shelf.locator('#asset-search').fill(code.lower())
            target = shelf.locator('[data-asset-id="' + code + '"]')
            expect(target).to_have_count(1)
            target.click()
        shelf.locator('#asset-search').fill('')
        shelf.locator('#overlay-view').click()
        expect(shelf.locator('#overlay-image')).to_be_visible()
        src = shelf.locator('#overlay-image').get_attribute('src')
        overlay = ctx.request.get(url + src).body()
        with Image.open(BytesIO(overlay)) as im:
            assert im.getchannel('A').getextrema() == (0, 255)
        expect(page.locator('#visual-prompt')).to_have_value(re.compile('STK-026'))
        shelf.locator('#layout-view').click()
        expect(shelf.locator('#preview .signalcard .wave')).to_be_visible()
        for code in ['WEB-010', 'WEB-011', 'WEB-012']:
            shelf.locator('#asset-search').fill(code)
            shelf.locator('[data-asset-id="' + code + '"]').click()
            assert shelf.locator('#preview article h3').inner_text()
        page.locator('#nav-lib').click()
        expect(page.locator('#prompt')).to_have_value(motion_prompt)
        page.locator('#nav-visual').click()
        page.set_viewport_size({'width': 390, 'height': 844})
        assert page.evaluate('document.documentElement.scrollWidth <= innerWidth')
        assert shelf.locator('body').evaluate('(el)=>el.scrollWidth<=innerWidth')
        page.set_viewport_size({'width': 1440, 'height': 960})
        shelf.get_by_role('button',name='3D 物件',exact=True).click()
        shelf.locator('#recent-only').check()
        expect(shelf.locator('#overlay-image')).to_be_visible()
        if output:
            output.mkdir(parents=True, exist_ok=True)
            page.screenshot(path=str(output/'预览界面.png'))
        page.locator('#use-visual').click()
        expect(page.locator('#style-summary')).to_contain_text('桌面麦克风')
        page.locator('#agent-mode').select_option('workbuddy')
        page.locator('#manuscript').fill(script)
        page.locator('#recommend').click()
        page.wait_for_function('state.review?.taskId')
        task = page.evaluate('state.review.taskId')
        client = AgentClient(url, 'workbuddy')
        claim = client.claim(task)
        assert claim['context']['sentences'][1] == script.split('。', 1)[1]
        assert {k:e['assetId'] for k,e in claim['context']['visualBrief'].items()} == chosen
        row = dict(sentence=1, title='试一段声音', reason='让观众看到收音设备，并用波形标出试听。',
                   brief='麦克风旁放声音波形，保留透明边缘。', route='library', visual=chosen)
        client.complete(task, claim['receipt'], json.dumps({'recommendations': [row]}, ensure_ascii=False))
        page.wait_for_function('state.review?.rows.some(r=>r.item.sample)')
        card = page.locator('.review-card[data-sentence="1"]')
        card.get_by_text('查看素材编号').click()
        expect(card.locator('details code')).to_contain_text('OBJ-017@PAL-013')
        card.locator('.accept').click()
        with page.expect_download() as download:
            page.locator('#export-choices').click()
        bundle = (output or Path(temp))/'播客收音-示例素材包.zip'
        download.value.save_as(bundle)
        with ZipFile(bundle) as archive:
            item = json.loads(archive.read('素材搭配.json'))['items'][0]
            assert item['assetRefs'] == chosen
            assert item['variantIds'] == {'objects':'OBJ-017@PAL-013','stickers':'STK-026@PAL-013'}
            assert archive.read(item['packageMedia']) == overlay
            archive.extractall(temp)
        layout = Path(temp)/item['packageSources']['layout.html']
        page.goto(layout.as_uri())
        expect(page.locator('article.signalcard')).to_be_visible()
        page.wait_for_function('Array.from(document.images).every(im=>im.complete && im.naturalWidth>0)')
        assert not errors, errors
        browser.close()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    run(args.url, args.output)
    print('Gallery, all four families, numbered Agent handoff, byte-identical PNG and offline layout passed.')
