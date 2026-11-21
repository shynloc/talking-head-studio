"""Real Chromium interactions, persistence, prompter, responsive layouts and all stage tabs."""
import argparse,json,urllib.request
from pathlib import Path
from playwright.sync_api import sync_playwright

def main():
    a=argparse.ArgumentParser();a.add_argument('--url',default='http://127.0.0.1:8765');a.add_argument('--out',required=True);a.add_argument('--media-project');args=a.parse_args()
    out=Path(args.out);out.mkdir(parents=True,exist_ok=True);errors=[];checks=[]
    boot=json.load(urllib.request.urlopen(args.url+'/api/bootstrap'))
    req=urllib.request.Request(args.url+'/api/new',data=json.dumps({'title':'UI 验收 · 三阶段口播'}).encode(),headers={'Content-Type':'application/json','X-Studio-Token':boot['token']})
    project=json.load(urllib.request.urlopen(req));pid=project['id']
    with sync_playwright() as p:
        b=p.chromium.launch(headless=True);ctx=b.new_context(viewport={'width':1440,'height':1040},reduced_motion='reduce');page=ctx.new_page();page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(args.url);page.wait_for_selector('#page-text');page.select_option('#projects',pid);page.wait_for_function('document.querySelector("#projects").value === '+json.dumps(pid));page.wait_for_timeout(300)
        page.fill('#page-title','把灵感，变成下一条作品');page.fill('#page-text','先准备好口播稿。然后连接设备。最后开始录制。');page.locator('#page-notes').click();page.wait_for_timeout(1200)
        page.reload();page.wait_for_selector('#page-title');assert page.input_value('#page-title')=='把灵感，变成下一条作品';checks.append('text autosave and reload')
        page.select_option('#anchor',index=2);page.click('[data-tag="flow"]');page.wait_for_timeout(900)
        assert page.locator('.annotation').count()==1;checks.append('sentence-bound tag')
        page.click('[data-cmd="add-page"]');page.select_option('#page-type','showcase');page.fill('#page-title','成品展示');page.fill('#page-duration','10');page.locator('#page-notes').click();page.wait_for_timeout(900)
        page.click('[data-cmd="move-up"]');page.wait_for_timeout(900);assert page.locator('.page-card').first.locator('h3').inner_text()=='成品展示';checks.append('add page, change type, duration and reorder')
        page.click('[data-cmd="duplicate-page"]');page.wait_for_timeout(900);assert page.locator('.page-card').count()==3
        page.click('[data-cmd="delete-page"]');page.wait_for_timeout(900);assert page.locator('.page-card').count()==2;checks.append('duplicate and delete')
        page.locator('.page-card').last.click();page.wait_for_timeout(300)
        with page.expect_popup() as pop:page.click('[data-cmd="prompt"]')
        prompt=pop.value;prompt.wait_for_selector('#text span');prompt.on('pageerror',lambda e:errors.append(str(e)));prompt.evaluate('window.STUDIO_TEST.follow("先准备好口播稿")')
        assert prompt.evaluate('window.STUDIO_TEST.getPosition()')>0;assert prompt.locator('.said').count()>0;checks.append('speech-match highlighting algorithm')
        prompt.click('#mirror');assert 'mirror' in prompt.locator('body').get_attribute('class');prompt.click('#retake');assert '第 2 次' in prompt.inner_text('#status');prompt.click('#next-btn');checks.append('prompter mirror, retake and navigation')
        prompt.screenshot(path=str(out/'prompter.png'),full_page=True);prompt.close();page.wait_for_timeout(900)
        page.locator('#toast').evaluate('(e)=>e.hidden=true');page.screenshot(path=str(out/'stage-1.png'),full_page=True)
        if args.media_project:page.select_option('#projects',args.media_project);page.wait_for_timeout(400)
        page.click('[data-stage="2"]');page.wait_for_selector('.review-grid');page.screenshot(path=str(out/'stage-2.png'),full_page=True);checks.append('stage 2 renders')
        page.click('[data-stage="3"]');page.wait_for_selector('.tabs');page.screenshot(path=str(out/'stage-3.png'),full_page=True)
        for name in ('captions','assets','exports','plan'):page.click(f'[data-tab="{name}"]');page.wait_for_timeout(150)
        checks.append('stage 3 captions, assets, exports, plan')
        page.click('[data-stage="1"]');page.set_viewport_size({'width':390,'height':844});page.wait_for_timeout(300)
        assert not page.evaluate('document.documentElement.scrollWidth>innerWidth+1');page.screenshot(path=str(out/'mobile.png'),full_page=True);checks.append('390px no horizontal overflow')
        b.close()
    assert not errors,errors
    (out/'browser-results.json').write_text(json.dumps({'status':'PASS','checks':checks,'page_errors':errors,'limits':['Microphone hardware and remote browser recognition were not exercised; matching/navigation were.']},ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'status':'PASS','checks':len(checks),'page_errors':errors}))

if __name__=='__main__':main()
