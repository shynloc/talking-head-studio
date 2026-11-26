"""Shared browser assertions for proofreading a real recording from head to tail."""
from pathlib import Path
import subprocess
import re
import hashlib
from playwright.sync_api import expect


def correct_recording(page,state,out,mode):
    spans=state['caption_spans']
    assert len(spans)>=3 and state['caption_review']['issues']
    assert all(s['text'].strip()!='是' or s['end']-s['start']<1.3 for s in spans)
    assert not any(s['text'][0] in '﹗!！。，,' for s in spans)
    if mode=='captions':
        assert not any(s['start']<11<s['end'] for s in spans),spans
    samples=lambda: page.evaluate("api('/api/project?id='+P.id).then(p=>p.exports.filter(e=>e.kind==='timeline_sample').length)")
    count=samples()
    page.locator('#caption-desk-open').click()
    audio=page.locator('#caption-audio')
    page.wait_for_function("document.querySelector('#caption-audio')?.currentTime>0")
    page.locator('#caption-next').click()
    changed=[]
    for i in (0,len(spans)//2,len(spans)-1):
        jump=page.locator('#caption-jump')
        jump.select_option(str(i))
        field=page.locator('#preview-text')
        expect(field).to_have_value(spans[i]['text'])
        page.wait_for_function("([a,b])=>{let v=document.querySelector('#caption-audio');return v && v.currentTime>=a-.05 && v.currentTime<=b+.1}",
                               arg=[spans[i]['listen_start'],spans[i]['listen_end']])
        value=field.input_value().rstrip('，。,！?!﹗')
        value+= '。' if not field.input_value().endswith('。') else '！'
        field.fill(value)
        expect(page.locator('#caption-save-state')).to_have_text('已保存')
        assert page.evaluate('([id,value])=>P.captions.find(c=>c.id===id).text===value',[spans[i]['id'],value])
        changed.append(spans[i]['id'])
    caps=page.evaluate('P.captions')
    pairs=[('贾维斯','JARVIS'),('加威斯','JARVIS'),('初代','第一代'),('视频','影片')]
    old,new=next((a,b) for a,b in pairs if sum(a in c['text'] for c in caps)>=2)
    before={c['id']:c['text'] for c in caps}
    page.locator('#caption-names summary').click()
    page.locator('#caption-old').fill(old);page.locator('#caption-new').fill(new)
    page.locator('#caption-bulk').click()
    page.wait_for_function('term=>P.captions.every(c=>!c.text.includes(term))',arg=old)
    page.locator('#caption-undo').click()
    page.wait_for_function('before=>P.captions.every(c=>c.text===before[c.id])',arg=before)
    page.locator('#caption-names summary').click()
    page.locator('#caption-old').fill(old);page.locator('#caption-new').fill(new)
    page.locator('#caption-bulk').click()
    page.wait_for_function('term=>P.captions.every(c=>!c.text.includes(term))',arg=old)
    # Also use the one-click suggestion after correcting just one occurrence.
    latest=page.evaluate('P.captions')
    source_cap=next(c for c in latest if new in c['text'])
    i=next(i for i,s in enumerate(spans) if s['id']==source_cap['id'])
    page.locator('#caption-jump').select_option(str(i))
    field=page.locator('#preview-text')
    expect(field).to_have_value(source_cap['text'])
    final_name={'JARVIS':'贾维斯','影片':'短片','第一代':'初代版'}[new]
    field.fill(source_cap['text'].replace(new,final_name))
    page.locator('#caption-auto-bulk').click()
    page.wait_for_function('term=>P.captions.every(c=>!c.text.includes(term))',arg=new)
    assert samples()==count
    page.screenshot(path=str(out/(mode+'-校对.png')))
    page.locator('#close-dialog').click()
    page.reload()
    page.locator('[data-workflow=finish]').click()
    expect(page.locator('#caption-proof')).to_be_visible()
    assert samples()==count
    page.locator('#caption-proof').click()
    expect(page.locator('#finish-confirm')).to_be_visible(timeout=240000)
    expect(page.locator('#proof-play')).to_be_visible()
    proof=page.evaluate("api('/api/v2/finish?id='+P.id)")
    assert abs(proof['sample']['duration']-state['duration'])<.15
    assert samples()==count+1
    button=page.locator('#proof-play')
    video=page.locator('#finish-panel video')
    video.evaluate("v=>{v.playbackRate=5;v.dataset.jumps='';v.addEventListener('seeked',()=>{v.dataset.jumps+=' '+v.currentTime})}")
    page.wait_for_function("document.querySelector('#finish-panel video')?.readyState>=2")
    if button.get_attribute('aria-pressed')=='true':button.click()
    button.click()
    page.wait_for_function("document.querySelector('#proof-play')?.textContent==='再看改过的几句'",timeout=45000)
    jumps=video.evaluate(r'v=>v.dataset.jumps.trim().split(/\s+/).filter(Boolean).map(Number)')
    assert any(t>8 for t in jumps),jumps
    assert not proof['caption_review']['pending']
    assert set(changed)<=set(page.evaluate('P.caption_review.proof_captions'))
    return dict(original_captions=spans,issues=state['caption_review']['issues'],edited=changed,old=old,new=final_name,intermediate=new,playback_jumps=jumps,
                name_occurrences=sum(s.count(old) for s in before.values()),per_edit_renders=0,proof=proof['sample'])


def check_final(page,dest,evidence,out,mode):
    p=page.evaluate("api('/api/project?id='+P.id)")
    item=next(e for e in reversed(p['exports']) if e['kind']=='timeline_final')
    path=Path(next(m['path'] for m in p['media'] if m['id']==item['id']))
    assert item['qa']['reviewed_sample']==evidence['proof']['id']
    assert hashlib.sha256(dest.read_bytes()).hexdigest()==item['qa']['sha256']
    proof_export=next(e for e in p['exports'] if e['id']==evidence['proof']['id'])
    assert proof_export['qa']['sha256']==item['qa']['sha256']
    srt=path.with_name('captions.srt').read_text(encoding='utf-8-sig')
    assert evidence['new'] in srt and evidence['old'] not in srt
    ass=path.with_name('captions.ass').read_text(encoding='utf-8-sig')
    assert evidence['new'] in ass
    def seconds(value):
        h,m,s=value.split(':')
        return float(h)*3600+float(m)*60+float(s)
    events=[line.split(',',9) for line in ass.splitlines() if line.startswith('Dialogue:')]
    intervals=[{'start':seconds(e[1]),'end':seconds(e[2]),'text':e[9]} for e in events]
    if mode=='captions':
        assert not any(e['start']<11<e['end'] for e in intervals)
        words=''.join(s['text'] for s in p['transcript'])
        original=''.join(c['original_text'] for c in p['captions'])
        assert re.sub(r'[^\w]','',words)==re.sub(r'[^\w]','',original)
    phrase=next(c for c in intervals if '是' in c['text'])
    assert len(phrase['text'])>1 and phrase['end']-phrase['start']<5
    evidence['rendered_phrase']=phrase
    evidence['source_word']=next({k:w[k] for k in ('word','start','end')} for s in p['transcript'] for w in s['words'] if w['word']=='是')
    check=next((s for s in evidence['original_captions'] if '是' in s['text']),evidence['original_captions'][0])
    second=(check['start']+check['end'])/2
    for name,sec in [('字幕',second)]+([('静音',11)] if mode=='captions' else []):
        subprocess.run(['ffmpeg','-v','error','-y','-ss',str(sec),'-i',str(dest),'-frames:v','1',str(out/(mode+'-'+name+'.png'))],check=True)
    evidence['final_srt']=srt
