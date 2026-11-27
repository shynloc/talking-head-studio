"""Read timed captions in original recording coordinates before changing a project."""
import json
import math
import re
from pathlib import Path

from core import uid
from manuscript_annotations import spoken


def read_segments(path, duration):
    path = Path(path)
    text = path.read_text(encoding='utf-8-sig')
    if path.suffix.lower() == '.json':
        raw = json.loads(text)
        rows = raw.get('segments', []) if isinstance(raw, dict) else raw
    else:
        stamp = r'(?:\d{1,}:)?\d{2}:\d{2}[.,]\d{3}'
        pattern = rf'^({stamp})\s*-->[ \t]*({stamp})[^\n]*\n(.*?)(?=\n[ \t]*\n|\Z)'
        def seconds(value):
            total = 0
            for part in value.replace(',', '.').split(':'):
                total = total * 60 + float(part)
            return total
        rows = [{'start': seconds(m[1]), 'end': seconds(m[2]), 'text': m[3].strip()}
                for m in re.finditer(pattern, text, re.M | re.S)]
    segments = []
    for row in rows:
        start, end = float(row['start']), float(row['end'])
        if not math.isfinite(end) or not 0 <= start < end <= duration + .1:
            raise ValueError('字幕时间超出当前原片，请选择与这条视频配套的字幕。')
        raw_text = str(row['text'])
        clean = spoken(raw_text)
        if clean.strip():
            segments.append({'id':uid('seg'), 'start':start, 'end':end, 'text':clean,
                             'words':row.get('words', []) if clean == raw_text else [],
                             'subtitle_cue':path.suffix.lower() in ('.srt','.vtt')})
    if not segments:
        raise ValueError('没有读到带时间的字幕，请选择 SRT、VTT 或 Whisper JSON。')
    return segments
