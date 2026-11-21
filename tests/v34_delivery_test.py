"""Regression and shared desktop acceptance fixture for the Stage 3 exits."""
import argparse
import json
from pathlib import Path
import re
import subprocess
import sys
import time
from urllib.request import Request, urlopen
from zipfile import ZipFile

from PIL import Image, ImageDraw
from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from core import file_digest
import media


def regression(url, output, speech_one, speech_two, verify_jianying=False):
    output.mkdir(parents=True, exist_ok=True)
    token = ''

    def api(path, payload=None):
        body = None if payload is None else json.dumps(payload, ensure_ascii=False).encode('utf-8')
        headers = {'Content-Type': 'application/json', 'X-Studio-Token': token}
        with urlopen(Request(url + path, data=body, headers=headers), timeout=30) as response:
            return json.load(response)

    token = api('/api/bootstrap')['token']
    p = api('/api/new', {'title': 'V3.4 同条样片 · 合成验收'})
    pid = p['id']

    def job(action, args=None, expect_error=None):
        task = api('/api/action', {'project_id': pid, 'action': action, 'args': args or {}})
        deadline = time.monotonic() + 120
        while time.monotonic() < deadline:
            result = next(j for j in api('/api/jobs?id=' + pid) if j['id'] == task['id'])
            if result['status'] in ('done', 'error'):
                if expect_error:
                    assert result['status'] == 'error' and expect_error in result['error'], result
                    return result
                assert result['status'] == 'done', result
                return result['result']
            time.sleep(.25)
        raise TimeoutError(action)

    stage_one = media.probe(speech_one)['duration']
    recording = output / '合成口播.mp4'
    media.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i', 'color=c=0xe3cbb4:s=360x640:r=24:d=30',
               '-i', speech_one, '-i', speech_two, '-filter_complex',
               '[1:a]aresample=48000[a];[2:a]aresample=48000[b];[a][b]concat=n=2:v=0:a=1[out]',
               '-map', '0:v', '-map', '[out]', '-vf',
               "drawbox=x=116:y=202:w=128:h=140:color=0x253559:t=fill,drawbox=x=60:y=342:w=240:h=234:color=0x466171:t=fill",
               '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-shortest', '-y', recording])
    duration = media.probe(recording)['duration']
    assert duration > 4
    sound = output / '提示音.wav'
    media.run(['ffmpeg', '-v', 'error', '-f', 'lavfi', '-i',
               'sine=frequency=720:sample_rate=48000:duration=2', '-y', sound])
    sticker = output / '透明贴纸.png'
    png = Image.new('RGBA', (180, 140))
    draw = ImageDraw.Draw(png)
    draw.rounded_rectangle((8, 8, 172, 132), radius=28, fill='#f29849')
    draw.ellipse((50, 30, 130, 110), fill='#002fa7')
    png.save(sticker)

    first = '先把设备连接到电脑。'
    second = '然后检查声音，再开始录制。'
    job('script', {'text': first + second})
    job('prompt_export')
    job('import_media', {'path': str(recording)})
    job('skip_rough')
    transcript = output / '合成口播转写.json'
    transcript.write_text(json.dumps([
        {'start': 0, 'end': stage_one, 'text': first},
        {'start': stage_one, 'end': duration, 'text': second},
    ], ensure_ascii=False), encoding='utf-8')
    job('import_transcript', {'path': str(transcript)})
    project_url = '/api/project?id=' + pid
    p = api(project_url)
    api('/api/v2/align', {'id': pid, 'version': p['version']})
    asset = job('add_asset', {'path': str(sticker)})
    gif = job('gif', {'asset_id': asset['id'], 'label': '试看片', 'animation': 'pulse'})
    sfx = job('add_asset', {'path': str(sound)})
    p = api(project_url)
    p['timeline']['clips'].extend([
        {'id': 'demo-gif', 'track': 'sticker', 'kind': 'sticker', 'name': '提示贴纸', 'start': .5,
         'duration': 2.5, 'asset_id': gif['id'], 'x': .04, 'y': .04, 'width': .22, 'height': .15},
        {'id': 'demo-flow', 'track': 'title', 'kind': 'flow', 'name': '录制流程', 'start': .75,
         'duration': 2.75, 'steps': ['连接', '试音', '开录'], 'x': .29, 'y': .04, 'width': .67, 'height': .18},
        {'id': 'demo-sfx', 'track': 'sfx', 'name': '提示音', 'start': 1, 'duration': .5,
         'source_in': .25, 'asset_id': sfx['id'], 'volume': .2, 'fade': .05},
    ])
    api('/api/save', p)
    assert len(api(project_url)['captions']) >= 2
    job('editor_package', expect_error='重新试看')
    browser_errors = []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge', headless=True)
        browser_page = browser.new_page(viewport={'width': 1280, 'height': 920}, accept_downloads=True)
        browser_page.on('pageerror', lambda error: browser_errors.append(str(error)))
        browser_page.goto(url + '/#project=' + pid)
        browser_page.locator('[data-stage="3"]').click()
        browser_page.get_by_role('button', name='试看动画与音效').click()
        browser_page.get_by_role('button', name=re.compile('录制流程')).click()
        expect(browser_page.locator('#finish-panel h3')).to_contain_text('录制流程')
        expect(browser_page.locator('[data-finish-delivery]')).to_have_count(0)
        browser_page.locator('#finish-generate').click()
        browser_page.wait_for_function("document.querySelector('.finish-video')?.readyState >= 2", timeout=120000)
        browser_page.locator('.finish-video').evaluate('(video) => video.play()')
        browser_page.wait_for_function("document.querySelector('.finish-video').currentTime > .5")
        browser_page.locator('.finish-video').evaluate('(video) => video.pause()')
        last_choice = browser_page.locator('[data-finish-delivery="jianying_reviewed_export"]')
        assert last_choice.bounding_box()['y'] + last_choice.bounding_box()['height'] <= 920
        browser_page.screenshot(path=str(output / '预览和出片选择.png'))
        state = api('/api/v2/finish?id=' + pid)
        assert abs(state['sample']['start'] - .25) < .02 and state['sample']['duration'] > 3
        expect(browser_page.locator('[data-finish-delivery]')).to_have_count(3)
        option = '[data-finish-delivery="editor_package"]'
        browser_page.locator(option).click()
        download = browser_page.get_by_role('link', name='下载素材包')
        download.wait_for(timeout=120000)
        with browser_page.expect_download() as pending:
            download.click()
        archive = output / '通用剪辑素材.zip'
        pending.value.save_as(archive)
        browser_page.locator('#finish-return').click()
        browser_page.locator('[data-finish-delivery="chatcut_package"]').click()
        browser_page.locator('#finish-handoff').wait_for(timeout=120000)
        browser_page.locator('#finish-handoff').click()
        browser_page.get_by_role('button', name='复制任务卡').click()
        card = browser_page.get_by_label('可复制内容')
        expect(card).to_have_value(re.compile(r'handoff_[0-9a-f]{12}'))
        browser_page.screenshot(path=str(output / 'ChatCut待办.png'))
        browser.close()
    assert not browser_errors, browser_errors

    unpacked = output / '另一位置'
    with ZipFile(archive) as bundle:
        assert bundle.testzip() is None
        bundle.extractall(unpacked)
    root = unpacked / '口播剪辑素材'
    manifest = json.loads((root / '时间线.json').read_text(encoding='utf-8'))
    assert manifest['timeline_hash'] == state['hash']
    assert manifest['sample']['sha256'] == file_digest(root / '预览.mp4')
    assert '开录' not in (root / manifest['subtitles']).read_text(encoding='utf-8-sig')
    assert '连接到电脑' in (root / manifest['subtitles']).read_text(encoding='utf-8-sig')
    assert (manifest['width'], manifest['height'], manifest['fps']) == (360, 640, 24)
    for placement in manifest['clips']:
        path = root / placement['path']
        assert path.is_file() and not Path(placement['path']).is_absolute(), placement
        if placement['role'] == 'visual':
            frame = output / (placement['id'] + '-alpha.png')
            media.run(['ffmpeg', '-v', 'error', '-ss', '0.5', '-i', path, '-vf', 'alphaextract,format=gray',
                       '-frames:v', '1', '-y', frame])
            with Image.open(frame) as alpha:
                assert alpha.getpixel((359, 639)) == 0 and alpha.getextrema()[1] > 50
    audio = next(clip for clip in manifest['clips'] if clip['role'] == 'audio')
    assert (audio['start'], audio['source_in'], audio['volume']) == (1, .25, .2)
    props = media.probe(root / manifest['base'])
    assert props['audio'] and abs(props['duration'] - manifest['duration']) < .15
    review = {'sample_id': state['sample']['id'], 'hash': state['hash']}
    final = job('confirm_timeline_final', review)
    chatcut = next(j['result'] for j in api('/api/jobs?id=' + pid) if j['action']=='chatcut_package')
    result = {'project_id': pid, 'root': str(root), 'has_preview': True, 'review': review,
              'workbench_final': final['path'], 'chatcut_package': chatcut['path']}
    if verify_jianying:
        result['jianying'] = job('jianying_reviewed_export', review)['path']
        with ZipFile(result['jianying']) as native:
            native.extractall(output / '新草稿位置')
        draft = next((output / '新草稿位置').glob('口播工作台-*'))
        subprocess.run([sys.executable, '-X', 'utf8', str(draft / '重新关联路径.py')], check=True)
        info = json.loads((draft / 'draft_info.json').read_text(encoding='utf-8'))
        assert {track['type'] for track in info['tracks']} == {'video', 'audio', 'text'}
        assert len(info['materials']['videos']) >= 3
        assert all(Path(item['path']).is_relative_to(draft) and Path(item['path']).is_file()
                   for kind in ('videos', 'audios') for item in info['materials'][kind])
        assert file_digest(draft / '预览.mp4') == manifest['sample']['sha256']
    p = api(project_url)
    p['timeline']['clips'][-1]['volume'] = .35
    api('/api/save', p)
    for action in ('editor_package', 'chatcut_package', 'jianying_reviewed_export'):
        job(action, review, expect_error='重新试看')
    (output / 'results.json').write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(result, ensure_ascii=False))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--url', required=True)
    parser.add_argument('--out', required=True, type=Path)
    parser.add_argument('--speech-one', required=True, type=Path)
    parser.add_argument('--speech-two', required=True, type=Path)
    parser.add_argument('--jianying', action='store_true')
    args = parser.parse_args()
    regression(args.url, args.out.resolve(), args.speech_one.resolve(), args.speech_two.resolve(), args.jianying)
