"""Exercise both creator routes with the same local talking-head recording and real ASR."""
import argparse
import hashlib
import json
import subprocess
from pathlib import Path

from playwright.sync_api import expect, sync_playwright


def inspect_video(path):
    data = subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format','-of','json',str(path)])
    meta = json.loads(data)
    video = next(t for t in meta['streams'] if t['codec_type']=='video')
    assert any(t['codec_type']=='audio' for t in meta['streams'])
    return video['width'], video['height'], float(meta['format']['duration'])


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--video', type=Path, required=True, help='A recording longer than 10 seconds with a long pause')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    w,h,total = inspect_video(args.video)
    evidence = {'source_sha256':hashlib.sha256(args.video.read_bytes()).hexdigest(),'routes':{}}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge',headless=True)
        page = browser.new_page(viewport={'width':1280,'height':850})
        errors = []
        page.on('pageerror',lambda e:errors.append(str(e)))
        for mode in ('captions','raw'):
            page.goto(args.url)
            page.locator('[data-v2=video-new]').click()
            page.locator('#recording-use').select_option(mode)
            with page.expect_file_chooser() as picker:
                page.locator('#video-file').click()
            picker.value.set_files(args.video)
            if mode == 'raw':
                page.locator('[data-workflow=find-pauses]').click(timeout=45000)
                page.locator('[data-workflow=play-rough]').click(timeout=120000)
                page.wait_for_function("document.querySelector('#player').currentTime>0")
                assert not page.evaluate('P.approvals.rough || P.captions.length')
                assert page.locator('.cut-row.removed').count()>0
                page.locator('[data-workflow=approve-rough]').click()
            else:
                page.wait_for_function("P && localStorage.getItem('studio-preview-task-'+P.id)",timeout=60000)
                page.reload()
            expect(page.locator('#finish-confirm')).to_be_visible(timeout=480000)
            player = page.locator('#finish-panel video')
            player.evaluate('v=>v.play()')
            page.wait_for_function("document.querySelector('#finish-panel video').currentTime>0.15")
            player.evaluate('v=>v.pause()')
            state = page.evaluate("api('/api/v2/finish?id='+P.id)")
            jobs = page.evaluate("api('/api/jobs?id='+P.id)")
            guided = [j['result'] for j in jobs if j['action']=='first_preview' and j['status']=='done']
            assert len(guided)==1 and guided[0]['recognition']['segments']>0
            assert guided[0]['sample_id']==state['sample']['id']
            t = state['caption_spans'][0]['start']
            assert state['sample']['start']<=t<state['sample']['start']+state['sample']['duration']
            assert state['sample']['duration']<state['duration']
            expect(page.locator('#finish-panel')).to_contain_text('完整视频')
            assert not state['approved']
            page.screenshot(path=str(args.out/(mode+'-preview.png')))
            with page.expect_download(timeout=180000) as saved:
                page.locator('#finish-confirm').click()
            dest = args.out/('已剪视频加字幕.mp4' if mode=='captions' else '原始录像粗剪加字幕.mp4')
            saved.value.save_as(dest)
            width,height,duration = inspect_video(dest)
            assert (width,height)==(w,h) and abs(duration-state['duration'])<.15
            assert (abs(duration-total)<.15 if mode=='captions' else duration<total-.3)
            subprocess.run(['ffmpeg','-nostdin','-v','error','-xerror','-i',str(dest),'-f','null','-'],check=True)
            evidence['routes'][mode]=dict(project=page.evaluate('P.id'),recognition=guided[0]['recognition'],
                subtitles=state['caption_spans'],preview=state['sample'],duration=duration,width=w,height=h)
            print(mode, duration, guided[0]['recognition'], flush=True)
        assert not errors, errors
        browser.close()
    (args.out/'results.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf8')


if __name__=='__main__':
    main()
