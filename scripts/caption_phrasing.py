"""Group recognized words into readable captions without crossing spoken pauses."""
import re
import unicodedata

CLOSING = '，。？！；：、,.?!;:…﹗﹖”’）)]】》'
CLAUSE_END = '，,：:、；;'
SENTENCE_END = '。？！!?；;﹗﹖'
CONNECTORS = ('然后','但是','所以','因为','如果','接下来','而且','不过','我们','你可以','这里','最后')
WEAK_END = ('的','把','被','跟','和','在','从','给','让','是','将','与','到','第','一个')


def lexical(text):
    return ''.join(c for c in text if c.isalnum())


def display_text(words):
    return ''.join(w['text'] for w in words).strip().translate(str.maketrans({'﹗':'！','﹖':'？'}))


def speech_word(w):
    word = dict(w)
    n = max(1, len(lexical(word['text'])))
    length = word['end'] - word['start']
    if length > max(2.6, .8*n + .6):
        # Word alignment can assign an entire pause to one token. New ASR also
        # splits on measured silence. For old transcripts keep the onset and flag it.
        word['end'] = word['start'] + min(length, .36 + .28*n)
        word['timing_trimmed'] = True
    return word


def divide(words):
    """Choose breaks near punctuation or phrase boundaries, leaving a readable tail."""
    while len(words)>1:
        length=len(display_text(words))
        if length<=26 and (words[-1]['end']-words[0]['start']<=5.3 or length<=10):
            break
        options=[]
        for i in range(1,len(words)):
            left=display_text(words[:i]); right=display_text(words[i:i+5]); n=len(left)
            if n>26 and options: break
            if not right or right[0] in CLOSING or not lexical(left):continue
            tail=length-n
            score=abs(n-min(20,length/2 if length<39 else 20))*.32
            score+=max(0,5-tail)*2+max(0,5-len(lexical(left)))*2
            score+=5*max(0,words[i-1]['end']-words[0]['start']-5)
            if left.endswith(tuple(CLAUSE_END)):score-=5
            if right.startswith(CONNECTORS):score-=3
            if left.endswith(WEAK_END):score+=4
            if left[-1].isascii() and left[-1].isalnum() and right[0].isascii() and right[0].isalnum() and not words[i]['text'].startswith(' '):score+=8
            score-=min(.6,max(0,words[i]['start']-words[i-1]['end']))*5
            options.append((score,i))
        if not options:break
        split=min(options)[1]
        yield words[:split]
        words=words[split:]
    if words:yield words


def groups(words, imported, previous):
    # Keep earlier human corrections attached to their original word IDs.
    fixed={wid:c['id'] for c in previous if c.get('text')!=c.get('original_text',c.get('text'))
           for wid in c.get('word_ids',[])}
    buf=[]; key=None
    def emit():
        if key is not None:
            return [buf] if buf else []
        return divide(buf)
    for raw in words:
        cue=raw['segment_id'] in imported
        w=raw if cue else speech_word(raw)
        next_key=('file',w['segment_id']) if cue else fixed.get(w['word_id'])
        punctuation=bool(w['text'].strip()) and all(c in CLOSING or unicodedata.category(c).startswith('P') for c in w['text'].strip())
        if next_key is None and (not buf or key is None):
            # ASR sometimes emits a closing mark by itself, or prefixes it to
            # the next Chinese word. It belongs to the preceding spoken phrase.
            prefix=re.match(r'^[，。！？；：、﹗﹖!?,;]+',w['text'])
            if prefix:
                rest=w['text'][len(prefix[0]):]
                if rest.strip():
                    if buf:buf[-1]=dict(buf[-1],text=buf[-1]['text']+prefix[0])
                    w=dict(w,text=rest)
                elif not buf:
                    continue
                elif not w.get('estimated') and w['end']-buf[-1]['end']>.45:
                    w=dict(w,start=buf[-1]['end'],end=buf[-1]['end'])
        if buf and (next_key!=key or (key is None and not punctuation and
                (w['start']-buf[-1]['end']>.68 or display_text(buf).rstrip('”’）').endswith(tuple(SENTENCE_END))
                 or (buf[-1]['text'].endswith(tuple(CLAUSE_END)) and len(lexical(display_text(buf)))>=5
                     and w['start']-buf[-1]['end']>.18)))):
            yield from emit()
            buf=[]
        buf.append(w);key=next_key
    yield from emit()


def review_reason(words):
    if any(w.get('timing_trimmed') for w in words):
        return '这句附近有停顿，听听文字和说话是否对齐。'
    probs=[w['probability'] for w in words if w.get('probability') is not None and lexical(w['text'])]
    if probs and (min(probs)<.25 or sum(p<.55 for p in probs)>=2):
        return '这句有字没听清，建议听一下原话。'
    return ''
