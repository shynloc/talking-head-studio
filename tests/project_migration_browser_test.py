"""Open full, light and legacy packs in a separate workbench and render each."""

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from zipfile import ZipFile

from playwright.sync_api import expect, sync_playwright
from project_migration_fixtures import write_legacy_lightweight

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
import media
import materials
import project_bundle
import timeline
from core import Store, file_digest, source


def api_project(page):
    return page.evaluate("api('/api/project?id='+P.id)")


def choose(page, button, file):
    with page.expect_file_chooser() as picker:
        page.locator(button).click()
    picker.value.set_files(file)


def open_pack(page, pack):
    page.locator('[data-v2=import-project]').click()
    choose(page, '#project-import-file', pack)


def make_packs(args):
    origin = Store(args.out / '源工程')
    project = json.loads(args.project.read_text(encoding='utf-8'))
    assert project['approvals'].get('rough') and project['timeline']['mode']=='actual'
    project['title'] = '换机验收 · 真实口播'
    files = args.out / '原片与素材'
    files.mkdir(exist_ok=True)
    original = files / '口播 原片.mp4'
    shutil.copy2(source(project)['path'], original)
    source(project)['path'] = str(original)
    rough = files / '已确认 粗剪.mp4'
    shutil.copy2(project['rough']['path'], rough)
    project['rough']['path'] = str(rough)
    for item in project['media']:
        if item['id'] == project['rough']['media_id']:
            item['path'] = str(rough)
    project['captions'][0]['text'] = '这句是迁移前人工校对的字幕。'
    project['settings']['caption_only'] = False
    origin.save(project)
    clip_path = files / '透明 动效.mov'
    with ZipFile(args.motion_bundle) as bundle:
        member = next(name for name in bundle.namelist() if name.startswith('透明动画/') and name.endswith('.mov'))
        clip_path.write_bytes(bundle.read(member))
    tone = files / '独立 音效.wav'
    subprocess.run(['ffmpeg','-nostdin','-v','error','-f','lavfi','-i','sine=duration=1','-y',str(tone)],check=True)
    pid = project['id']
    overlay = materials.add(origin,pid,clip_path,'固定版本透明素材','VisionBuddy')
    sound = materials.add(origin,pid,tone,'音效','测试')
    project = origin.load(pid)
    asset = next(a for a in project['assets'] if a['id']==overlay['id'])
    assert asset['alpha_capable']
    asset.update(libraryRelease='1.0.0',assetId='OBJ-017',variantId='OBJ-017@PAL-013')
    for track, item in [('pip', overlay), ('sfx', sound)]:
        project['timeline']['clips'].append(dict(id='migration-'+track,track=track,
            name=item['name'],kind='asset',asset_id=item['id'],anchor='absolute',enabled=True,
            start=1,duration=min(1,item['duration']),source_in=0))
    timeline.validate(project)
    project = origin.save(project)
    report = lambda *_: None
    full = Path(project_bundle.export_bundle(origin,project,report,True)['path'])
    light = Path(project_bundle.export_bundle(origin,project,report)['path'])
    legacy = args.out / '旧版本工程.zip'
    write_legacy_lightweight(light, legacy)
    broken = args.out / '损坏工程.zip'
    with ZipFile(full) as original_zip, ZipFile(broken,'w') as altered:
        first_asset = next(n for n in original_zip.namelist() if n.startswith('assets/'))
        for name in original_zip.namelist():
            data = original_zip.read(name)
            altered.writestr(name, bytes([data[0]^1])+data[1:] if name==first_asset else data)
    wrong = files / '同画幅同时长的错片.mp4'
    subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(original),'-c','copy',
        '-metadata','title=Different source bytes','-y',str(wrong)],check=True)
    assert file_digest(original)!=file_digest(wrong)
    assert all(media.probe(original)[k]==media.probe(wrong)[k] for k in ('duration','width','height'))
    return project, full, light, legacy, broken, original, wrong


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project',required=True,type=Path)
    parser.add_argument('--motion-bundle',required=True,type=Path)
    parser.add_argument('--out',required=True,type=Path)
    parser.add_argument('--target-url',required=True)
    parser.add_argument('--target-data',required=True,type=Path)
    args = parser.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    original, full, light, legacy, broken, recording, wrong = make_packs(args)
    results = {}
    with sync_playwright() as pl:
        browser = pl.chromium.launch(channel='msedge',headless=True)
        page = browser.new_page(viewport={'width':1280,'height':850})
        errors = []
        page.on('pageerror',lambda error:errors.append(str(error)))
        page.goto(args.target_url)
        existing = page.evaluate("api('/api/bootstrap').then(b=>b.projects.map(p=>p.id))")
        open_pack(page,broken)
        expect(page.locator('#project-import-error')).to_contain_text('媒体校验失败',timeout=90000)
        assert page.evaluate("api('/api/bootstrap').then(b=>b.projects.map(p=>p.id))")==existing
        page.locator('#close-dialog').click()
        for kind, pack in [('full',full),('light',light),('legacy',legacy)]:
            open_pack(page,pack)
            pid = page.wait_for_function("(title)=>P?.title===title && !homeMode && P.id",arg=original['title'],timeout=90000).json_value()
            restored = api_project(page)
            assert pid != original['id'] and pid not in existing
            existing.append(pid)
            assert restored['pages']==original['pages'] and restored['edl']==original['edl']
            assert restored['captions']==original['captions'] and restored['timeline']==original['timeline']
            asset = next(a for a in restored['assets'] if a.get('libraryRelease'))
            assert (asset['libraryRelease'],asset['variantId'],asset['alpha_capable'])==('1.0.0','OBJ-017@PAL-013',True)
            assert file_digest(asset['path'])==file_digest(next(a['path'] for a in original['assets'] if a['id']==asset['id']))
            assert all(Path(a['path']).is_relative_to(args.target_data) for a in restored['assets'])
            if kind == 'full':
                assert restored['approvals']['rough']['kind']=='migrated'
                assert all(Path(p).is_relative_to(args.target_data) for p in (source(restored)['path'],restored['rough']['path']))
            else:
                assert not source(restored)['path']
                page.locator('[data-workflow=relink]').click()
                if kind == 'light':
                    choose(page,'#relink-file',wrong)
                    expect(page.locator('#toast')).to_contain_text('这不是工程包中的原片')
                    assert not source(api_project(page))['path']
                    page.locator('[data-workflow=relink]').click()
                else:
                    expect(page.get_by_text('旧工程包会核对时长和画幅',exact=False)).to_be_visible()
                choose(page,'#relink-file',recording)
                expect(page.locator('[data-stage="3"]')).to_have_attribute('aria-current','step',timeout=90000)
            page.locator('[data-workflow=finish]').click()
            if kind=='legacy':
                page.get_by_role('button',name='用这版剪辑继续',exact=True).click(timeout=90000)
            expect(page.locator('#finish-confirm')).to_be_visible(timeout=180000)
            with page.expect_download(timeout=180000) as transfer:
                page.locator('#finish-confirm').click()
            video = args.out/(kind+'.mp4')
            transfer.value.save_as(video)
            subprocess.run(['ffmpeg','-nostdin','-v','error','-xerror','-i',str(video),'-f','null','-'],check=True)
            output = media.probe(video)
            assert output['audio'] and (output['width'],output['height'])==(480,640)
            assert abs(output['duration']-22.033333)<.2
            state = api_project(page)
            assert state['captions']==original['captions']
            jobs = page.evaluate("api('/api/jobs?id='+P.id)")
            assert not any(j['action'] in ('transcribe','analyze_cuts') or j.get('result',{}).get('recognition') for j in jobs)
            results[kind] = {'id':pid,'duration':output['duration'],'video':video.name}
            page.locator('#close-dialog').click()
            page.locator('[data-v2=home]').click()
        assert not errors, errors
        browser.close()
    (args.out/'results.json').write_text(json.dumps(results,ensure_ascii=False,indent=2),encoding='utf8')
    print(json.dumps(results,ensure_ascii=False),flush=True)


if __name__ == '__main__':
    main()
