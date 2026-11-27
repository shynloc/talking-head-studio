"""Verify the same marked manuscript with the live VisionBuddy website and offline ZIP."""
import argparse
import json
from pathlib import Path
from zipfile import ZipFile

from playwright.sync_api import expect, sync_playwright

from manuscript_annotations_flow import run as manuscript_flow


def select(base, mode, archive=None):
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel="msedge")
        page = browser.new_page()
        page.goto(base + "/motion/index.html?view=visual")
        panel = page.locator('#library-source')
        expect(panel.locator('summary')).to_contain_text('素材来源 ·')
        panel.locator('summary').click()
        with page.expect_navigation(wait_until='domcontentloaded', timeout=160000):
            if archive:
                panel.locator('input[type=file]').set_input_files(archive)
            else:
                panel.locator(f'[data-library-action="{mode}"]').click()
        expect(panel.locator('summary')).to_contain_text('在线库' if mode == 'online' else '本地库')
        state = page.request.get(base+'/api/motion/library-source').json()
        assert state['mode'] == mode
        assert state['libraryRelease'] == '1.0.0'
        if archive:
            assert state['installed'] == '1.0.0'
        browser.close()


def check_pack(path):
    with ZipFile(path) as bundle:
        data = json.loads(bundle.read('素材搭配.json'))
        assert {item['libraryRelease'] for item in data['items']} == {'1.0.0'}
        return [bundle.read(i) for i in bundle.namelist() if i.endswith('.mov')]


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', required=True)
    parser.add_argument('--zip', required=True, type=Path)
    parser.add_argument('--out', required=True, type=Path)
    a = parser.parse_args()
    select(a.url, 'online')
    manuscript_flow(a.url, a.out/'在线')
    select(a.url, 'local', a.zip.resolve())
    manuscript_flow(a.url, a.out/'本地')
    online = check_pack(a.out/'在线/同一篇稿-透明素材包.zip')
    local = check_pack(a.out/'本地/同一篇稿-透明素材包.zip')
    assert len(online) == len(local) == 2
    assert online == local
    print('Online and installed ZIP: identical MOVs, pinned versions, and manuscript rules verified.')
