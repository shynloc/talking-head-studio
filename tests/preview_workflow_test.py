"""Walk the paused-preview, recording-note and subtitles-only paths in an isolated workbench."""
import argparse
import json
import subprocess
from pathlib import Path
from playwright.sync_api import expect, sync_playwright


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--url',required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--video',type=Path,required=True)
    parser.add_argument('--srt',type=Path,required=True)
    parser.add_argument('--image',type=Path,required=True)
    args=parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    rows=[block.splitlines()[-1] for block in args.srt.read_text(encoding='utf-8-sig').strip().split('\n\n')]
    target=rows[2]
    with sync_playwright() as pl:
        browser=pl.chromium.launch(channel='msedge',headless=True)
        page=browser.new_page(viewport={'width':1280,'height':850})
        page.set_default_timeout(20000)
        page_errors=[]
        page.on('pageerror',lambda e:page_errors.append(str(e)))
        page.goto(args.url)
        page.locator('[data-v2=blank]').click()
        page.locator('#page-text').fill('。'.join(rows)+'。')
        page.locator('#page-text').blur()
        page.wait_for_function('P.pages[0].sentences.length>=3')
        page.locator('.annotations summary').click()
        sid=page.evaluate('P.pages[0].sentences[2].id')
        page.locator('#anchor').select_option(sid)
        page.locator('[data-tag=product]').click()
        page.locator('[data-tag-label]').fill('开发板展示')
        page.locator('[data-tag-label]').blur()
        page.locator('[data-workflow=recording]').click()

        def import_video(mode):
            page.locator('#recording-use').select_option(mode)
            if mode=='captions':
                page.evaluate("let input=document.createElement('input');input.id='drop-fixture';input.type='file';input.multiple=true;document.body.append(input)")
                files=page.locator('#drop-fixture')
                files.set_input_files([args.video,args.srt])
                files.evaluate("""el=>{const data=new DataTransfer();for(const file of el.files)data.items.add(file);
                    document.querySelector('#recording-drop').dispatchEvent(new DragEvent('drop',{bubbles:true,dataTransfer:data}));el.remove()}""")
                expect(page.locator('#finish-confirm')).to_be_visible(timeout=90000)
                assert page.evaluate('P.captions.map(c=>c.text)')==rows
                jobs=page.evaluate("api('/api/jobs?id='+P.id)")
                assert all('recognition' not in job.get('result',{}) for job in jobs)
                return
            with page.expect_file_chooser() as event:page.locator('#video-file').click()
            event.value.set_files(args.video)
            expect(page.locator('[data-stage="3"]')).to_have_attribute('aria-current','step',timeout=45000)
            with page.expect_file_chooser() as event:page.locator('[data-workflow=caption-file]').click()
            event.value.set_files(args.srt)
            expect(page.locator('[data-workflow=finish]')).to_be_visible(timeout=45000)

        import_video('ready')
        page.locator('[data-recording-note]').click()
        expect(page.locator('#note-use')).to_be_visible(timeout=90000)
        assert page.locator('#note-caption').input_value()==page.evaluate('P.captions[2].id')
        page.locator('#note-change').click()
        page.locator('#note-mode').select_option('animated')
        page.locator('#note-file').set_input_files(args.image)
        page.locator('#note-try').click()
        expect(page.locator('#note-use')).to_be_visible(timeout=120000)
        assert not page.evaluate('P.timeline.clips.find(c=>c.tag_id).enabled')
        page.screenshot(path=str(args.out/'录前备注小样.png'))
        page.locator('#note-use').click()
        expect(page.locator('#dialog')).not_to_be_visible()
        assert page.evaluate('P.timeline.clips.find(c=>c.tag_id).enabled')
        cap=page.evaluate('P.captions[2]')
        trial_start=max(.15,cap['start']-.3)
        page.locator('[data-workflow=finish]').click()
        expect(page.locator('#finish-confirm')).to_be_visible(timeout=90000)
        page.locator('#finish-another').click()
        page.locator('#finish-start').fill(str(round(trial_start,1)))
        page.locator('#finish-duration').fill('3')
        page.locator('#finish-generate').click()
        expect(page.locator('#finish-confirm')).to_be_visible(timeout=90000)

        def pause_on_sentence():
            state=page.evaluate("api('/api/v2/finish?id='+P.id)")
            span=next(c for c in state['caption_spans'] if c['id']==cap['id'])
            relative=span['start']+.15-state['sample']['start']
            page.wait_for_function("document.querySelector('#finish-panel video')?.readyState>=2")
            page.locator('#finish-panel video').evaluate('(v,t)=>{v.pause();v.currentTime=t;}',relative)
            expect(page.locator('#preview-caption')).to_be_enabled()
            expect(page.locator('#preview-line')).to_contain_text(target)
        pause_on_sentence()
        page.locator('#preview-caption').click()
        updated=target+'。'
        page.locator('#preview-text').fill(updated)
        page.locator('#preview-save').click()
        expect(page.locator('#finish-confirm')).to_be_visible(timeout=90000)
        pause_on_sentence()
        page.locator('#preview-visual').click()
        page.locator('#preview-asset').select_option('')
        page.locator('#preview-text').fill('开发板')
        page.locator('#preview-save').click()
        expect(page.locator('#finish-confirm')).to_be_visible(timeout=90000)
        pause_on_sentence()
        page.screenshot(path=str(args.out/'暂停就地修改.png'))
        assert page.evaluate("P.timeline.clips.some(c=>c.name==='开发板'&&c.enabled)")
        assert page.evaluate("P.captions.map(c=>c.text)").count(updated)==1
        def export(name):
            page.locator('#finish-confirm').click()
            with page.expect_download(timeout=120000) as event:
                page.get_by_text('下载完整成片',exact=True).click(timeout=120000)
            dest=args.out/name
            event.value.save_as(dest)
            subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(dest),'-f','null','-'],check=True)
            return str(dest)
        film=export('就地改字和画面.mp4')
        page.locator('#close-dialog').click()
        page.locator('[data-v2=home]').click()
        page.locator('[data-v2=video-new]').click()
        import_video('captions')
        expect(page.locator('#caption-only')).to_be_checked()
        expect(page.locator('[data-recording-note]')).to_have_count(0)
        expect(page.locator('#finish-confirm')).to_be_visible(timeout=90000)
        expect(page.locator('#preview-visual')).to_have_count(0)
        short=export('只加字幕.mp4')
        assert not page_errors,page_errors
        (args.out/'results.json').write_text(json.dumps({'status':'PASS','video':args.video.name,'tested_caption':target,
            'sample_start':trial_start,'main':film,'subtitles_only':short,'approvals':'isolated test projects'},ensure_ascii=False,indent=2),encoding='utf8')
        print('PASS',target,flush=True)
        browser.close()


if __name__=='__main__':
    main()
