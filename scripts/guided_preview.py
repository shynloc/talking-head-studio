"""Prepare the first playable captioned sample for a selected recording."""
from core import Conflict, LOCK, rough_current, source
from jobs import doctor
from timeline_render import review_state

MODEL_ORDER = ('base', 'small', 'medium', 'turbo', 'tiny', 'large')


def prepare(jobs, pid, args, report):
    store = jobs.store
    entry = args.get('entry')
    if entry not in ('import', 'approve', 'keep', 'resume', 'find_cuts', 'use_cuts'):
        raise ValueError('请选择要预览的视频。')

    progress = 0
    def run(action, options, low, high):
        def update(n, message):
            nonlocal progress
            progress = max(progress, low + n * (high - low))
            report(progress, message)
        return jobs.action(pid, action, options, update)

    if entry == 'import':
        options = {k:args[k] for k in ('path','subtitle_path','use_as') if k in args}
        options.setdefault('use_as','captions')
        tools = doctor()['tools']
        if not (tools['ffmpeg'] and tools['ffprobe']):
            if not args.get('allow_tools'):
                return {'next':'tools','options':options,'source_id':store.load(pid).get('source_id')}
            run('prepare_video_tools', {}, 0, .06)
        item = run('import_media', options, .06, .08)
        if options['use_as'] == 'raw' and item.get('video'):
            entry = 'find_cuts'
        elif options['use_as'] != 'captions':
            return {'next':'editor' if item.get('ready_for_captions') else 'recording','source_id':item['id']}
        if not item.get('video'):
            return {'next':'recording', 'source_id':item['id']}
    else:
        p = store.load(pid)
        if not args.get('source_id') or args['source_id'] != p.get('source_id'):
            raise ValueError('当前视频已更换，请在这条视频上重新开始。')
        if entry == 'approve':
            if not p.get('rough') or p['rough']['media_id'] != args.get('rough_id'):
                raise ValueError('剪后视频已更新，请先试听当前版本。')
            run('approve_rough', {}, 0, .05)
        if entry == 'keep':
            run('skip_rough', {}, 0, .05)

    if entry in ('find_cuts', 'use_cuts'):
        source_id = item['id'] if args['entry'] == 'import' else args['source_id']
        if entry == 'find_cuts':
            run('analyze_cuts', {}, .08, .17)
        p = store.load(pid)
        expected = p['edl'] if entry == 'find_cuts' else args.get('edl')
        def check_selection(project):
            if project['source_id'] != source_id or project['edl'] != expected:
                raise Conflict('停顿选择已更新，请重新打开剪后预览。')
        check_selection(p)
        if entry == 'find_cuts' and any(not row['keep'] for row in expected):
            return {'next':'cuts', 'source_id':source_id}
        if not rough_current(p):
            run('render_rough', {}, .17, .32)
        with LOCK:
            p = store.load(pid)
            check_selection(p)
            if entry == 'find_cuts':
                p['approvals']['rough'] = {'kind':'no_cuts', 'source_id':source_id}
                store.save(p, label='没有需要缩短的停顿，沿用原片')
            else:
                run('approve_rough', {}, .32, .33)
    p = store.load(pid)
    result = {'source_id':p['source_id']}
    if not rough_current(p) or not p['approvals'].get('rough'):
        raise ValueError('先试听并确认要使用的剪后版本。')
    replacing = entry == 'resume' and args.get('subtitle_path')
    if replacing:
        run('import_transcript', {'path':args['subtitle_path']}, .05, .1)
        p = store.load(pid)
    if not p['transcript'] and not p['captions']:
        if not source(p).get('audio'):
            return dict(result, next='subtitles', message='这条视频没有音轨。')
        info = doctor()
        installed = info['models']
        preferred = p['settings'].get('model')
        model = next((m for m in (preferred, *MODEL_ORDER) if m in MODEL_ORDER and m in installed), 'base')
        needs_install = not all(info['modules'][m] for m in ('whisper', 'torch'))
        if (needs_install or model not in installed) and not args.get('allow_download'):
            return dict(result, next='setup', model=model, install=needs_install, download=model not in installed)
        if needs_install:
            run('prepare_transcription', {}, .08, .18)
        recognition = run('transcribe', {'model':model, 'allow_download':bool(args.get('allow_download'))}, .18, .62)
        result['recognition'] = {k:recognition[k] for k in ('engine','device','segments')}
        if not recognition['segments']:
            return dict(result, next='subtitles', message='没有识别到说话声。')
    state = review_state(store.load(pid))
    if replacing or entry in ('approve','keep','use_cuts','find_cuts') or not p['captions'] or state['state'] == 'align':
        report(.64, '正在把字幕对到剪后画面')
        run('plan', {}, .64, .7)
        state = review_state(store.load(pid))
    if state['state'] != 'ready':
        return dict(result, next='review')
    spans = state['caption_spans']
    if not spans:
        return dict(result, next='subtitles', message='保留的画面里没有可见字幕，请检查所选片段或字幕轨。')
    start = max(0, spans[0]['start'] - .2)
    sample = state['sample']
    if not sample or not sample['start'] <= spans[0]['start'] < sample['start'] + sample['duration']:
        report(.72, '正在生成第一句口播的字幕预览')
        sample = run('timeline_sample', {'start':start, 'duration':min(10, state['duration'] - start)}, .72, 1)
    return dict(result, next='review', sample_id=sample['id'])
