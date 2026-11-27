"""Separate explicit visual directions from the text the presenter reads."""
import re
from bisect import bisect_left
from collections import defaultdict

MARKER = re.compile(r"[（(][ \t]*画面[ \t]*[：:]")
SENTENCE = re.compile(r"""[^。！？!?\n]+(?:[。！？!?]+[”’」』）)]*)?|[。！？!?]+""")
PERIOD = re.compile(r".+?(?:\.(?=\s|$)|$)")


def markers(line):
    """Yield complete marks on a single line, permitting balanced parentheses in the note."""
    cursor = 0
    while match := MARKER.search(line, cursor):
        depth = 1
        for i in range(match.end(), len(line)):
            char = line[i]
            if char in "（(":
                depth += 1
            elif char in "）)":
                depth -= 1
                if depth == 0:
                    yield match.start(), i + 1, line[match.end():i].strip()
                    cursor = i + 1
                    break
        else:
            # The reserved prefix still identifies a direction while the user is editing it.
            yield match.start(), len(line), ""
            return


def sentences(text):
    for match in SENTENCE.finditer(text):
        raw = match[0]
        trimmed = raw.strip()
        for part in PERIOD.finditer(trimmed):
            quote = part[0].strip()
            if quote:
                yield {"quote": quote, "offset": match.start() + raw.index(trimmed) +
                       part.start() + part[0].index(quote)}


def split(text):
    """Return clean prose and mark locations in that prose."""
    if not MARKER.search(text):
        return text, []
    output, annotations = [], []
    offset = 0
    previous = None
    for line in text.split("\n"):
        chunks, marks, cursor, length = [], [], 0, 0
        for start, end, note in markers(line):
            chunk = line[cursor:start]
            chunks.append(chunk)
            length += len(chunk)
            marks.append((length, note))
            cursor = end
        chunks.append(line[cursor:])
        current = "".join(chunks)
        if marks and not current.strip():
            annotations.extend((previous, note, False) for _, note in marks)
            continue
        for position, note in marks:
            before = current[:position].rstrip()
            anchor = offset + len(before) - 1 if before else None
            annotations.append(((anchor, anchor + 1) if anchor is not None else None, note, True))
        if current.strip():
            previous = offset, offset + len(current)
        output.append(current)
        offset += len(current) + 1
    return "\n".join(output), annotations


def spoken(text):
    return split(text)[0]


def analyze(text):
    clean, marks = split(text)
    units = list(sentences(clean))
    ends = [unit["offset"] + len(unit["quote"]) for unit in units]
    paragraph, inline = defaultdict(list), defaultdict(list)
    errors = []
    for location, note, is_inline in marks:
        if location is None:
            errors.append("有一条画面标注前面缺少口播正文，请移到要配画面的文字后面。")
            continue
        start, end = location
        target = inline if is_inline else paragraph
        i = bisect_left(ends, start + 1)
        while i < len(units) and units[i]["offset"] < end:
            target[i].append(note)
            i += 1
    bindings = []
    for i in range(len(units)):
        notes = inline.get(i) or paragraph.get(i)
        if not notes:
            continue
        if bindings and i not in inline and bindings[-1]["notes"] == notes and (
            bindings[-1]["sentences"][-1] == i - 1 and i - 1 not in inline
            and "\n" not in clean[units[i - 1]["offset"]:units[i]["offset"]]
        ):
            bindings[-1]["sentences"].append(i)
        else:
            bindings.append({"sentences": [i], "notes": notes})
    return clean, units, bindings, list(dict.fromkeys(errors))
