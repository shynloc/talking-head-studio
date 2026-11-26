"""Exercise personal overlay creation, native media export and editable round-trip."""
import argparse
import base64
import io
import json
import subprocess
import zipfile
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageStat
from playwright.sync_api import expect, sync_playwright

TEXT = '先定主色，再排标题，最后留下呼吸空间。海报从初稿变成定稿。印样从12张增加到28张。'


def pixels(raw):
    return Image.open(io.BytesIO(raw)).convert('RGBA')


def check_media(zip_path, expected, out):
    with zipfile.ZipFile(zip_path) as z:
        assert z.testzip() is None
        movs = sorted(n for n in z.namelist() if n.endswith('.mov'))
        stills = sorted(n for n in z.namelist() if n.endswith('.png'))
        assert len(movs) == len(stills) == len(expected)
        manifest = json.loads(z.read('素材搭配.json'))
        (out/'素材搭配.json').write_bytes(z.read('素材搭配.json'))
        result = []
        for i, (movie, png, sample) in enumerate(zip(movs, stills, expected)):
            item = manifest['items'][i]
            assert item['quote'] == sample['quote'] and item['seconds'] == sample['seconds']
            assert item['title'] == sample['title'] and item['poster'] == sample['frame']
            assert pixels(z.read(png)).tobytes() == pixels(sample['png']).tobytes()
            path = out / Path(movie).name
            path.write_bytes(z.read(movie))
            stream = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-of','json',str(path)]))['streams'][0]
            assert (stream['codec_name'],stream['profile'],int(stream['nb_frames']),stream['width'],stream['height']) == ('prores','4444',item['seconds']*25,960,360)
            assert stream['pix_fmt'].startswith('yuva') and stream['r_frame_rate']=='25/1'
            ref = pixels(sample['png'])
            raw = subprocess.check_output(['ffmpeg','-v','error','-i',str(path),'-vf',f"select=eq(n\\,{item['poster']})",
                    '-frames:v','1','-f','rawvideo','-pix_fmt','rgba','pipe:1'])
            frame = Image.frombytes('RGBA',(960,360),raw)
            alpha = ref.getchannel('A')
            assert alpha.getextrema() == (0,255) and frame.getpixel((0,0))[3] == 0
            matte = Image.new('RGBA',frame.size,(34,64,120,255))
            delta = ImageStat.Stat(ImageChops.difference(Image.alpha_composite(matte,ref).convert('RGB'),
                                    Image.alpha_composite(matte,frame).convert('RGB'))).mean
            assert max(delta) < 3,delta
            result.append({'quote':item['quote'],'frames':stream['nb_frames'],'codec':stream['profile'],'preview_frame_rgb_mae':delta})
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--url',required=True);p.add_argument('--out',required=True,type=Path);p.add_argument('--channel',default='msedge')
    args=p.parse_args();out=args.out;out.mkdir(parents=True,exist_ok=True)
    for i,color in enumerate(['#ff8024','#244bd3']):
        im=Image.new('RGBA',(120,90));dr=ImageDraw.Draw(im);dr.rounded_rectangle((5,5,100,85),radius=18,fill=color)
        dr.ellipse((26+16*i,25,61+16*i,60),fill='#f6e5cd');im.save(out/f'art-{i}.png')
    with sync_playwright() as pw:
        browser=pw.chromium.launch(channel=args.channel,headless=True)
        page=browser.new_page(viewport={'width':1360,'height':900},reduced_motion='reduce')
        page.set_default_timeout(12000);errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
        page.goto(args.url)
        page.get_by_role('link',name='只做口播素材',exact=False).click()
        expect(page.locator('#manuscript')).to_be_editable()
        page.locator('#manuscript').fill(TEXT)
        expect(page.locator('.sentence')).to_have_count(3)
        page.screenshot(path=str(out/'选原句.png'))
        samples=[]
        def capture():
            sample=page.evaluate("""()=>({quote:state.draft.quote,seconds:state.draft.seconds,title:state.draft.title,frame,
                       png:document.getElementById('preview').toDataURL().split(',')[1]})""")
            sample['png']=base64.b64decode(sample['png']);return sample
        page.locator('#manual-lines summary').click()
        page.locator('.sentence').nth(0).click()
        page.locator('#title').fill('用留白组织画面')
        page.locator('#seconds').select_option('2')
        page.locator('#open-library').click()
        expect(page.locator('#cards .card')).to_have_count(100)
        page.locator('[data-group=textcue]').click();page.locator('[data-id=underline] .pick').click()
        page.locator('#close-library').click();page.locator('#play').click()
        page.wait_for_function("Number(document.getElementById('scrub').value)>3");page.locator('#play').click()
        page.locator('#scrub').fill('29');samples.append(capture());page.locator('#approve').click()
        page.locator('#more').click();page.locator('.sentence').nth(1).click()
        page.locator('#title').fill('从想法到成品');page.locator('#recipe').select_option('1')
        page.locator('#seconds').select_option('3')
        page.locator('#details summary').click();page.locator('#a').fill('初稿');page.locator('#b').fill('定稿')
        page.locator('#image-a').set_input_files(out/'art-0.png');page.wait_for_function('images.imageA')
        page.locator('#image-b').set_input_files(out/'art-1.png');page.wait_for_function('images.imageB')
        page.locator('#backdrop').select_option('dark');page.locator('#scrub').fill('59')
        samples.append(capture());page.screenshot(path=str(out/'配画面.png'))
        page.locator('#approve').click();expect(page.locator('.pack-item')).to_have_count(2);page.reload();expect(page.locator('.pack-item')).to_have_count(2)
        page.screenshot(path=str(out/'素材包.png'))
        with page.expect_download(timeout=120000) as dl:page.locator('#export').click()
        first=out/'自定义透明素材包.zip';dl.value.save_as(first)
        stats=check_media(first,samples,out)
        page.locator('#more').click();page.locator('#manuscript').fill(TEXT+'最后看一眼颜色。')
        expect(page.locator('.sentence')).to_have_count(4)
        ctx2=browser.new_context(viewport={'width':390,'height':844},reduced_motion='reduce')
        other=ctx2.new_page();other.on('pageerror',lambda e:errors.append(str(e)))
        other.goto(args.url+'/motion/index.html?view=desk');expect(other.locator('#manuscript')).to_be_editable()
        other.locator('#restore-file').set_input_files(out/'素材搭配.json')
        expect(other.locator('.pack-item')).to_have_count(2);other.locator('.pack-item button').filter(has_text='改这款').last.click()
        expect(other.locator('#title')).to_have_value('从想法到成品');assert other.evaluate('!!images.imageA && !!images.imageB')
        other.locator('#title').fill('改稿后的海报');other.locator('#seconds').select_option('1');other.locator('#approve').click()
        assert other.evaluate('document.documentElement.scrollWidth<=innerWidth')
        with other.expect_download(timeout=120000) as again:other.locator('#export').click()
        revised=out/'修改后重新导出.zip';again.value.save_as(revised)
        with zipfile.ZipFile(revised) as z:
            items=json.loads(z.read('素材搭配.json'))['items']
            assert items[1]['title']=='改稿后的海报' and items[1]['seconds']==1
        ctx2.close();browser.close();assert not errors,errors
    (out/'results.json').write_text(json.dumps(stats,indent=2,ensure_ascii=False),encoding='utf8')
    print('Custom two-clip export, preview frame comparison, import, editing, re-export and mobile layout passed.')


if __name__=='__main__':
    main()
