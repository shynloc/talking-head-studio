"""Run the everyday browser paths in a dedicated test workbench."""

import argparse
import json
import math
import struct
import subprocess
import wave
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def make_video(folder):
    audio = folder / '录音样例.wav'
    rate = 16000
    with wave.open(str(audio), 'wb') as file:
        file.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
        frames = [round(8500 * math.sin(2 * math.pi * 330 * i / rate)) if i < .7 * rate or i > 2.4 * rate else 0
                  for i in range(3 * rate)]
        file.writeframes(struct.pack(f'<{len(frames)}h', *frames))
    video = folder / '已有 视频.mp4'
    subprocess.run(['ffmpeg', '-nostdin', '-v', 'error', '-f', 'lavfi', '-i', 'testsrc2=s=270x360:r=12:d=3',
                    '-i', str(audio), '-c:v', 'libx264', '-pix_fmt', 'yuv420p', '-c:a', 'aac',
                    '-shortest', '-y', str(video)], check=True)
    return video


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--out', type=Path, required=True)
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    video = make_video(args.out)
    caption = args.out / '已有 字幕.srt'
    caption.write_text('1\n00:00:00,030 --> 00:00:00,620\n先介绍主题。\n\n'
                       '2\n00:00:02,420 --> 00:00:02,960\n再总结这段内容。\n', encoding='utf-8')
    checks, errors = [], []
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge', headless=True)
        page = browser.new_page(viewport={'width': 1280, 'height': 830})
        page.on('pageerror', lambda error: errors.append(str(error)))
        page.goto(args.url)
        page.get_by_role('button', name='新建项目').click()
        page.locator('[data-workflow="write"]').click()
        editor = page.locator('#page-text')
        expect(editor).to_be_focused()
        editor.fill('今天分享一个简单的做法。')
        expect(editor).to_be_focused()
        expect(page.locator('[data-workflow="prompt"]')).to_be_visible()
        expect(page.locator('[data-tl="collapse"]')).to_have_attribute('aria-expanded', 'false')
        page.locator('[data-tl="collapse"]').click()
        expect(page.locator('[data-tl="add"]')).to_be_visible()
        checks.append('writing updates the next action in place, with advanced timeline available on demand')

        draft = args.out / '口播稿.txt'
        draft.write_text('今天先介绍这个小技巧。\n\n最后看看实际效果。', encoding='utf-8')
        page.locator('[data-v2="home"]').click()
        page.locator('[data-v2="import-new"]').click()
        page.wait_for_function('mdEditor?._ready')
        with page.expect_file_chooser() as chooser:
            page.locator('#manuscript-file').click()
        chooser.value.set_files(draft)
        expect(page.locator('#draft-state')).to_contain_text('等待', timeout=15000)
        page.locator('#draft-create').click()
        expect(page.locator('[data-workflow="prompt"]')).to_be_visible()
        expect(page.locator('#page-text')).to_contain_text('今天先介绍这个小技巧。')
        checks.append('existing text can become editable cue pages while AI suggestions are pending')

        def start_with_video():
            page.locator('[data-v2="home"]').click()
            page.locator('[data-v2="video-new"]').click()
            expect(page.locator('#dialog-title')).to_have_text('导入录制')
            with page.expect_file_chooser() as chooser:
                page.locator('#video-file').click()
            chooser.value.set_files(video)
            expect(page.locator('[data-workflow="find-pauses"]')).to_be_visible(timeout=20000)
            expect(page.locator('[data-workflow="keep-recording"]')).to_be_visible()
            expect(page.locator('[data-tl="collapse"]')).to_have_attribute('aria-expanded', 'false')

        start_with_video()
        page.screenshot(path=str(args.out / '01-视频选择.png'))
        page.locator('[data-workflow="find-pauses"]').click()
        expect(page.locator('[data-workflow="render-rough"]')).to_be_visible(timeout=25000)
        assert page.locator('.cut-row.removed').count() >= 1
        page.locator('[data-workflow="render-rough"]').click()
        expect(page.locator('[data-workflow="approve-rough"]')).to_be_visible(timeout=25000)
        page.locator('[data-workflow="play-rough"]').click()
        page.wait_for_function("document.querySelector('#player').currentTime > 0")
        page.locator('[data-workflow="approve-rough"]').click()
        expect(page.locator('[data-workflow="captions"]')).to_be_visible(timeout=20000)
        checks.append('normal recording can find pauses, preview the cuts and confirm the version')

        start_with_video()
        page.locator('[data-workflow="keep-recording"]').click()
        expect(page.locator('[data-workflow="captions"]')).to_be_visible(timeout=20000)
        page.locator('[data-workflow="captions"]').click()
        expect(page.locator('[data-workflow="transcribe"]')).to_be_visible()
        page.reload()
        expect(page.locator('[data-stage="3"]')).to_have_class('active')
        with page.expect_file_chooser() as chooser:
            page.locator('[data-workflow="caption-file"]').click()
        chooser.value.set_files(caption)
        page.locator('[data-workflow="make-captions"]').click(timeout=20000)
        expect(page.locator('[data-workflow="edit-captions"]')).to_be_visible(timeout=20000)
        page.locator('[data-workflow="edit-captions"]').click()
        expect(page.locator('[data-field="text"]').first).to_have_value('先介绍主题。')
        page.locator('[data-workflow="finish"]').click()
        expect(page.locator('#finish-start')).not_to_be_visible()
        page.locator('#finish-generate').click(timeout=20000)
        expect(page.locator('#finish-confirm')).to_be_visible(timeout=45000)
        page.screenshot(path=str(args.out / '02-预览确认.png'))
        page.locator('#finish-confirm').click()
        with page.expect_download() as download:
            page.get_by_text('下载完整成片', exact=True).click(timeout=45000)
        final = args.out / '工作流 回归成片.mp4'
        download.value.save_as(final)
        probe = subprocess.check_output(['ffprobe', '-v', 'error', '-show_streams', '-of', 'json', str(final)])
        tracks = json.loads(probe)['streams']
        assert any(track['codec_type'] == 'video' and (track['width'], track['height']) == (270, 360) for track in tracks)
        assert any(track['codec_type'] == 'audio' for track in tracks)
        checks.append('already-edited video keeps its confirmation after subtitle import and exports from the guided preview')
        browser.close()
    assert not errors, errors
    result = {'status': 'PASS', 'checks': checks}
    (args.out / 'results.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    print(json.dumps(result), flush=True)


if __name__ == '__main__':
    main()
