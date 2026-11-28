"""Composite a demonstration with the time-aligned presenter for previews and editor exports."""
import media


def take(project, scene, base, base_start, start, duration, folder, w, h, fps, report):
    folder.mkdir(parents=True, exist_ok=True)
    # Animation uses project time; the presenter is seeked relative to the rendered base.
    media.create_overlay({**project, 'v2_overlay': True, 'scenes': [scene]}, folder, w, h, fps)
    demo = media.render_overlay(folder, w, h, fps, start, duration, report)
    speaker_width = max(2, round(w * scene.get('presenter_scale', .30) / 2) * 2)
    speaker_height = max(2, round(h * scene.get('presenter_scale', .30) / 2) * 2)
    key = 'chromakey=0x00ff00:0.22:0.08,' if project['settings'].get('presenter_style') == 'green' else ''
    x = 'W*0.04' if scene.get('presenter_side') == 'left' else 'W-w-W*0.04'
    graph = (f'color=c=0x182234:s={w}x{h}:r={fps}[bg];[bg][1:v]overlay[stage];'
             f'[0:v]{key}scale={speaker_width}:{speaker_height}:force_original_aspect_ratio=decrease:'
             f'force_divisible_by=2,setsar=1[host];[stage][host]overlay=x={x}:y=H*0.86-h[out]')
    out = folder / 'demonstration.mp4'
    media.run(['ffmpeg','-v','error','-ss',max(0,start-base_start),'-i',base,'-i',demo,
               '-filter_complex',graph,'-map','[out]','-t',duration,'-an','-c:v','libx264',
               '-preset','veryfast','-crf','17','-pix_fmt','yuv420p','-y',out],folder/'demonstration.log')
    return out


def background(project, scenes, base, work, start, duration, w, h, fps, report):
    composite = base
    # Bound the number of open decoders even for a long project.
    for first in range(0,len(scenes),12):
        inputs = ['-i',composite]
        filters = []
        for index, scene in enumerate(scenes[first:first+12],1):
            begin = max(scene['start'],start)
            end = min(scene['end'],start+duration)
            path = take(project,scene,base,start,begin,end-begin,work/f'demo-{first+index}',w,h,fps,report)
            offset = begin-start
            inputs += ['-itsoffset',offset,'-i',path]
            prev = '0:v' if index == 1 else f'v{index-1}'
            filters.append(f'[{prev}][{index}:v]overlay=eof_action=pass:repeatlast=0:'
                           f"enable='gte(t,{offset})*lt(t,{end-start})'[v{index}]")
        composite = work/f'demo-base-{first}.mp4'
        media.run(['ffmpeg','-v','error',*inputs,'-filter_complex',';'.join(filters),
                   '-map',f'[v{len(filters)}]','-map','0:a','-c:a','copy','-t',duration,'-c:v','libx264',
                   '-preset','fast','-crf','18','-pix_fmt','yuv420p','-y',composite],work/f'demo-base-{first}.log')
    return composite
