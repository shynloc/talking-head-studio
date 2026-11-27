"""Small original talking-head demonstrations and their project-local inputs."""
import base64
import hashlib
from io import BytesIO
import json
from pathlib import Path
import re
from array import array
import sys
import tempfile

from PIL import Image, ImageOps

import motion_samples as samples

MAX_INPUT = 12 * 1024**2
REFERENCE = re.compile(r"(截图|前段音频|后段音频)\s*([a-f0-9]{64})(?![a-f0-9])")
WORDS = re.compile(r"字([一二三])「([^」]{1,26})」")
SCENES = {"seal", "wave", "status", "route", "number", "focus"}


def with_labels(notes, default):
    words = list(default)
    for slot, value in WORDS.findall(notes):
        index = "一二三".index(slot)
        if index < len(words):
            words[index] = value
    return words


def package_input(root, kind, raw):
    if not raw or len(raw) > MAX_INPUT:
        raise ValueError("请选择不超过 12 MB 的截图或音频。")
    if kind == "image":
        try:
            with Image.open(BytesIO(raw)) as original:
                if original.width * original.height > 16_000_000:
                    raise ValueError("截图像素过多，请缩小到 1600 万像素以内。")
                original = ImageOps.exif_transpose(original).convert("RGBA")
                original.thumbnail((1000, 700))
                output = BytesIO()
                original.save(output, "PNG")
        except (OSError, Image.DecompressionBombError) as exc:
            raise ValueError("无法打开截图，请用 PNG、JPG 或 WebP。") from exc
        value = "data:image/png;base64," + base64.b64encode(output.getvalue()).decode("ascii")
    elif kind == "audio":
        from runtime import refresh_installed_tools
        refresh_installed_tools()
        with tempfile.TemporaryDirectory() as temp:
            source = Path(temp) / "audio"
            source.write_bytes(raw)
            try:
                pcm = samples.run(["ffmpeg", "-v", "error", "-protocol_whitelist", "file,pipe", "-i", str(source),
                    "-vn", "-t", "30", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"])
            except (FileNotFoundError, RuntimeError, ValueError) as exc:
                raise ValueError("无法读出音频，请用 WAV、MP3、M4A 或其他带声音的文件。") from exc
        signal = array("h")
        signal.frombytes(pcm)
        if sys.byteorder != "little":
            signal.byteswap()
        if len(signal) < 24:
            raise ValueError("音频太短，无法生成波形。")
        value = [round(max(abs(s) for s in signal[i*len(signal)//24:(i+1)*len(signal)//24])/32768, 4)
                 for i in range(24)]
    else:
        raise ValueError("请选择截图或音频。")
    body = json.dumps({"kind":kind,"value":value},ensure_ascii=False,separators=(",", ":")).encode()
    key = hashlib.sha256(body).hexdigest()
    dest = Path(root)/"motion-inputs"/(key+".json")
    dest.parent.mkdir(parents=True,exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=dest.parent,delete=False) as stage:
        stage.write(body)
    Path(stage.name).replace(dest)
    return {"key": key, "value": value}


def notes_inputs(root, notes, scene):
    valid = {"status":{"截图":"screenshot"}, "wave":{"前段音频":"waveBefore","后段音频":"waveAfter"}}.get(scene,{})
    attachments = {}
    for label, key in REFERENCE.findall(notes):
        if label not in valid:
            continue
        path = Path(root)/"motion-inputs"/(key+".json")
        if not path.is_file():
            raise ValueError("找不到这段标注对应的本机附件，请在搭配页重新选文件。")
        data = json.loads(path.read_bytes())
        if data["kind"] != ("image" if label=="截图" else "audio"):
            raise ValueError("演示附件类型不匹配。")
        attachments[valid[label]] = data["value"]
    if scene=="wave" and bool(attachments.get("waveBefore")) != bool(attachments.get("waveAfter")):
        raise ValueError("对照请同时选择前段和后段的音频。")
    return attachments


def image_url(path):
    if not path:
        return ""
    mime = "image/svg+xml" if Path(path).suffix == ".svg" else "image/png"
    return "data:" + mime + ";base64," + base64.b64encode(Path(path).read_bytes()).decode("ascii")


def source(root, treatment, context, spec):
    scene=treatment["scene"]
    if scene not in SCENES:
        raise ValueError("未知的演示样式。")
    notes=context.get("brief", "")
    seconds=context["seconds"]
    obj=spec.get("objects", {})
    sticker=spec.get("stickers", {})
    palette=spec.get("palettes") or samples.brief({"palettes":"atelier"})["palettes"]
    data=dict(scene=scene,heading=treatment["label"],colors=palette["colors"],seconds=seconds,
        frames=seconds*25,labels=with_labels(notes,treatment["labels"]),
        picture=image_url(obj.get("files",{}).get("preview")) if scene=="focus" else "",
        sticker=image_url(sticker.get("files",{}).get("vector")),
        anchor=next(iter(obj.get("tokens",{}).get("anchors",{}).values()),[.62,.52]))
    if scene == "number" and not WORDS.search(notes):
        values = re.findall(r"-?\d+(?:\.\d+)?", context["quote"])
        data["labels"] = [*values[:2], ""] if len(values) >= 2 else ["变化前", "变化后", ""]
    if scene=="wave":
        kit=next(k for k in samples.catalog()["practice"] if k["id"]=="compare-wave")
        data["waveBefore"],data["waveAfter"]=kit["originalWave"]
    data.update(notes_inputs(root,notes,scene))
    template=(samples.LIBRARY/"lesson-demo.html").read_text(encoding="utf8")
    return template.replace("__SCENE__",json.dumps(data,ensure_ascii=False).replace("<",r"\u003c"))
