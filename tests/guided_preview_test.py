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


def check_cut_review(page,out,expect_two,check_resume=False):
    open_review = page.locator('[data-workflow=review-cuts]')
    expect(open_review).to_be_visible(timeout=120000)
    rows = page.evaluate('P.edl.filter(c=>!c.keep)')
    count = len(rows)
    assert count>0 and (not expect_two or count==2)
    assert page.evaluate('!P.rough && !P.approvals.rough && !P.captions.length')
    open_review.click()
    def in_range(low,high):
        page.wait_for_function('([a,b])=>{let v=document.querySelector("#cut-video");return v && !v.seeking && !v.paused && v.currentTime>a && v.currentTime<b}',arg=[low,high],timeout=30000)
    if expect_two:
        first,last=rows
        in_range(first['end'],first['end']+1.6)
        expect(page.locator('#cut-count')).to_have_text('第 2 处，共 2 处',timeout=15000)
        in_range(last['end'],last['end']+1.6)
        if check_resume:
            page.reload()
            expect(page.locator('#cut-count')).to_have_text('第 2 处，共 2 处')
            expect(page.locator('#cut-play')).to_have_text('播放')
            page.locator('#cut-play').click()
            in_range(last['end'],last['end']+1.6)
        page.locator('#cut-compare').click()
        in_range(last['start']+.05,last['end'])
        page.locator('#cut-compare').click()
        in_range(last['end'],last['end']+1.6)
        page.locator('#cut-restore').click()
        in_range(last['start']+.05,last['end'])
        page.locator('#cut-restore').click()
        in_range(last['end'],last['end']+1.6)
        page.locator('#cut-prev').click()
        page.locator('#cut-restore').click()
        in_range(first['start']+.03,first['end'])
        page.screenshot(path=str(out/'raw-恢复停顿.png'))
        page.locator('#close-dialog').click()
        page.wait_for_function('!dirty && !saving')
        page.reload()
        expect(open_review).to_be_visible()
        open_review.click()
        expect(page.locator('#cut-state')).to_have_text('已恢复原停顿')
        page.locator('#cut-full').click()
        in_range(first['start']+.03,first['end'])
        expect(page.locator('#cut-count')).to_have_text('完整剪后视频')
        page.locator('#cut-full').click()
    else:
        page.wait_for_function('document.querySelector("#cut-video")?.currentTime>0')
    assert page.evaluate('!P.rough && !P.media.some(m=>m.kind==="rough") && !P.approvals.rough')
    kept=page.evaluate('P.edl')
    removed=sum(r['end']-r['start'] for r in kept if not r['keep'])
    page.locator('#cut-confirm').click()
    return {'candidates':rows,'selection':kept,'seconds_removed':removed,'rough_renders_before_confirmation':0}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url', required=True)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--video', type=Path, required=True, help='A recording longer than 10 seconds with a long pause')
    parser.add_argument('--proofread',action='store_true',help='Check V3.9 caption corrections on the 26-second regression recording')
    parser.add_argument('--resume',action='store_true',help='Check reopening cut review, caption review and completed export')
    args = parser.parse_args()
    args.out.mkdir(parents=True, exist_ok=True)
    w,h,total = inspect_video(args.video)
    evidence = {'source_sha256':hashlib.sha256(args.video.read_bytes()).hexdigest(),'routes':{}}
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel='msedge',headless=True)
        page = browser.new_page(viewport={'width':1280,'height':850})
        errors = []
        page.on('pageerror',lambda e:errors.append(str(e)))
        for mode in ('captions','ready','raw'):
            page.goto(args.url)
            page.locator('[data-v2=video-new]').click()
            page.locator(f'#recording-{mode}').check()
            with page.expect_file_chooser() as picker:
                page.locator('#video-file').click()
            picker.value.set_files(args.video)
            if mode == 'raw':
                review = check_cut_review(page,args.out,expect_two=args.proofread,check_resume=args.resume)
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
            assert page.evaluate('Boolean(P.settings.caption_only)') == (mode=='captions')
            guided = [j['result'] for j in jobs if j['action']=='first_preview' and j['status']=='done']
            if mode=='raw':
                assert [g.get('next') for g in guided].count('cuts')==1
            guided = [g for g in guided if g.get('next')=='review']
            assert len(guided)==1 and guided[0]['recognition']['segments']>0
            assert guided[0]['sample_id']==state['sample']['id']
            t = state['caption_spans'][0]['start']
            assert state['sample']['start']<=t<state['sample']['start']+state['sample']['duration']
            assert state['sample']['duration']<state['duration']
            expect(page.locator('#finish-panel')).to_contain_text('完整视频')
            assert not state['approved']
            page.screenshot(path=str(args.out/(mode+'-preview.png')))
            correction={}
            if args.proofread:
                from caption_desk_flow import correct_recording, check_final
                correction=correct_recording(page,state,args.out,mode,check_resume=args.resume)
            if args.resume:
                page.locator('#finish-confirm').click()
                page.wait_for_function("savedFinishRequest(P.id).id || document.querySelector('#finish-panel a.key')")
                page.locator('#close-dialog').click()
                page.locator('[data-v2=home]').click()
                download=page.locator('.resume-project').get_by_role('link',name='下载成片',exact=True)
                expect(download).to_be_visible(timeout=180000)
                assert page.evaluate("api('/api/jobs?id='+P.id).then(jobs=>jobs.filter(j=>j.action==='confirm_timeline_final').length)") == 1
                with page.expect_download() as saved:
                    download.click()
            else:
                with page.expect_download(timeout=180000) as saved:
                    page.locator('#finish-confirm').click()
            dest = args.out/({
                'captions':'已剪视频只加字幕.mp4',
                'ready':'已剪视频加字幕和画面.mp4',
                'raw':'原始录像粗剪加字幕.mp4',
            }[mode])
            saved.value.save_as(dest)
            width,height,duration = inspect_video(dest)
            assert (width,height)==(w,h) and abs(duration-state['duration'])<.15
            assert (duration<total-.3 if mode=='raw' else abs(duration-total)<.15)
            subprocess.run(['ffmpeg','-nostdin','-v','error','-xerror','-i',str(dest),'-f','null','-'],check=True)
            if args.proofread:check_final(page,dest,correction,args.out,mode)
            evidence['routes'][mode]=dict(corrections=correction,project=page.evaluate('P.id'),recognition=guided[0]['recognition'],
                subtitles=state['caption_spans'],preview=state['sample'],duration=duration,width=w,height=h)
            if mode=='raw':
                rendered=page.evaluate('P.media.filter(m=>m.kind==="rough").length')
                assert rendered==1
                review['rough_renders_after_confirmation']=rendered
                evidence['routes'][mode]['cut_review']=review
                assert abs(duration - (total-review['seconds_removed'])) < .15
            else:
                assert not page.locator('#cut-review').count()
                assert all(j['action']!='prepare_rough' for j in jobs)
                assert page.evaluate('P.rough.media_id===P.source_id')
            print(mode, duration, guided[0]['recognition'], flush=True)
        assert not errors, errors
        browser.close()
    (args.out/'results.json').write_text(json.dumps(evidence,ensure_ascii=False,indent=2),encoding='utf8')


if __name__=='__main__':
    main()
