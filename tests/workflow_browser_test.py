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
        page.locator('[data-v2="blank"]').click()
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
        expect(page.locator('#import-text')).to_be_visible()
        before = page.evaluate('projectList.length')
        page.locator('#close-dialog').click()
        page.reload()
        page.locator('[data-v2="import-new"]').click()
        assert page.evaluate('projectList.length') == before
        with page.expect_file_chooser() as chooser:
            page.locator('#manuscript-file').click()
        chooser.value.set_files(draft)
        expect(page.locator('#page-count')).to_contain_text('页', timeout=15000)
        page.locator('#draft-create').click()
        expect(page.locator('[data-workflow="prompt"]')).to_be_visible()
        assert '今天先介绍这个小技巧。' in page.locator('#page-text').input_value()
        checks.append('cancelled import creates no project and an existing manuscript becomes editable cue pages')

        def start_with_video():
            page.locator('[data-v2="home"]').click()
            page.locator('[data-v2="video-new"]').click()
            expect(page.locator('#dialog-title')).to_have_text('导入录制')
            with page.expect_file_chooser() as chooser:
                page.locator('#video-file').click()
            chooser.value.set_files([video,caption])
            expect(page.locator('[data-workflow="find-pauses"]')).to_be_visible(timeout=20000)
            expect(page.locator('[data-workflow="keep-recording"]')).to_be_visible()
            expect(page.locator('[data-tl="collapse"]')).to_have_attribute('aria-expanded', 'false')

        start_with_video()
        page.screenshot(path=str(args.out / '01-视频选择.png'))
        page.locator('[data-workflow="find-pauses"]').click()
        expect(page.locator('[data-workflow="approve-rough"]')).to_be_visible(timeout=25000)
        assert page.locator('.cut-row.removed').count() >= 1
        page.locator('[data-workflow="play-rough"]').click()
        page.wait_for_function("document.querySelector('#player').currentTime > 0")
        page.locator('[data-workflow="approve-rough"]').click()
        expect(page.locator('#finish-confirm')).to_be_visible(timeout=45000)
        page.locator('#finish-confirm').click()
        with page.expect_download() as raw_download:
            page.get_by_text('下载完整成片', exact=True).click(timeout=45000)
        raw_final = args.out / '原始录像剪后成片.mp4'
        raw_download.value.save_as(raw_final)
        raw_duration = float(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration','-of','csv=p=0',str(raw_final)]))
        assert 0 < raw_duration < 3
        page.locator('#close-dialog').click()
        checks.append('raw recording, automatic rough cut, imported captions, preview and shorter exported MP4')

        start_with_video()
        page.locator('[data-workflow="keep-recording"]').click()
        expect(page.locator('#finish-confirm')).to_be_visible(timeout=45000)
        page.locator('#finish-edit').click()
        page.reload()
        expect(page.locator('[data-stage="3"]')).to_have_class('active')
        expect(page.locator('[data-workflow="edit-captions"]')).to_be_visible(timeout=20000)
        page.locator('[data-workflow="edit-captions"]').click()
        expect(page.locator('[data-field="text"]').first).to_have_value('先介绍主题。')
        page.locator('[data-illustrate]').first.click()
        page.locator('#cue-name').fill('先介绍主题')
        page.locator('#cue-use').click()
        expect(page.locator('#dialog')).not_to_be_visible()
        page.wait_for_function("P.timeline.clips.some(c=>c.track==='title' && c.name==='先介绍主题' && Math.abs(c.start-.03)<.02)")
        page.locator('[data-illustrate]').first.click()
        page.locator('#cue-kind').select_option('picture')
        page.locator('#cue-use').click()
        expect(page.locator('#cue-state')).to_contain_text('先选')
        from PIL import Image
        image = args.out / '插图.png'
        Image.new('RGBA',(64,64),(0,47,167,180)).save(image)
        page.locator('#cue-file').set_input_files(image)
        page.locator('#cue-use').click()
        expect(page.locator('#dialog')).not_to_be_visible(timeout=15000)
        page.wait_for_function("P.timeline.clips.some(c=>c.track==='pip' && c.asset_id && Math.abs(c.start-.03)<.02)")
        page.locator('[data-workflow="finish"]').click()
        expect(page.locator('#finish-start')).not_to_be_visible()
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
