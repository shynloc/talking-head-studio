"""Validated, immutable transparent media shared by agent tasks, card previews and exports."""

import io
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import shutil
import subprocess
import tempfile
import zipfile
from functools import lru_cache

from core import ROOT, write_json
from runtime import refresh_installed_tools

LIBRARY = ROOT / "assets/workbench/motion/visual"
LIMIT = 192 * 1024**2
SOURCE_TYPES = {
    ".html",
    ".json",
    ".svg",
    ".png",
    ".glb",
    ".gif",
    ".webp",
    ".css",
    ".js",
    ".txt",
    ".md",
    ".mjs",
}


@lru_cache(maxsize=1)
def catalog():
    return json.loads((LIBRARY / "catalog.json").read_text(encoding="utf8"))


def resolve_entry(group, key):
    if isinstance(key, str):
        for entry in catalog()[group]:
            if key == entry["id"] or key.upper() == entry["assetId"]:
                return entry
    raise ValueError("素材册中没有所选搭配。")


def selection(raw=None):
    if raw is None:
        return {}
    if not isinstance(raw, dict):
        raise ValueError("风格搭配格式不正确。")
    result = {}
    for group in ("styles", "palettes", "objects", "stickers"):
        key = raw.get(group)
        if key:
            if group in ("objects", "stickers") and isinstance(key, str) and "@" in key:
                key, color = key.split("@", 1)
                palette = resolve_entry("palettes", color)["id"]
                if result.get("palettes", palette) != palette:
                    raise ValueError("所选版本使用不同配色，请用同一套配色。")
                result["palettes"] = palette
            result[group] = resolve_entry(group, key)["id"]
    return result


def brief(raw):
    selected = selection(raw)
    result = {}
    for kind, key in selected.items():
        entry = next(e for e in catalog()[kind] if e["id"] == key)
        result[kind] = {
            k: v for k, v in entry.items() if k not in ("variants", "files", "source")
        }
        if "variants" in entry:
            palette = resolve_entry("palettes", selected.get("palettes", "atelier"))
            result[kind]["variantId"] = entry["assetId"] + "@" + palette["assetId"]
            result[kind]["files"] = {
                k: str(LIBRARY / v)
                for k, v in entry["variants"][
                    selected.get("palettes", "atelier")
                ].items()
            }
    return result


def folder(root, key):
    if not isinstance(key, str) or not re.fullmatch("[0-9a-f]{64}", key):
        raise ValueError("无效的素材版本。")
    return root / "motion-samples" / key


def metadata(root, key):
    return json.loads((folder(root, key) / "meta.json").read_text(encoding="utf8"))


def preview_file(root, key, name):
    if not re.fullmatch(r"(poster|f\d{3})\.webp", name):
        raise ValueError("无效的预览帧。")
    return folder(root, key) / name


def run(args):
    result = subprocess.run(
        args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=180
    )
    if result.returncode:
        raise ValueError(
            "透明素材无法解码或编码。" + result.stderr.decode("utf8", "replace")[-300:]
        )
    return result.stdout


def frame_preview(image, stage, index):
    from PIL import Image

    rgba = image.convert("RGBA")
    lo, hi = rgba.getchannel("A").getextrema()
    rgba.thumbnail((640, 480), Image.Resampling.LANCZOS)
    rgba.save(stage / f"f{index:03}.webp", lossless=True, method=1)
    return lo, hi


def inspect(stage, master):
    from PIL import Image

    if master.suffix == ".png":
        with Image.open(master) as im:
            w, h = im.size
            if (
                im.format != "PNG"
                or max(w, h) > 4096
                or getattr(im, "is_animated", False)
            ):
                raise ValueError("静态素材需要不超过 4096 像素的透明 PNG。")
            lo, hi = frame_preview(im, stage, 0)
        if lo != 0 or hi < 32:
            raise ValueError("PNG 需要有可见内容和全透明留白。")
        count, fps, poster = 1, 0, 0
    else:
        refresh_installed_tools()
        stream = json.loads(
            run(
                [
                    "ffprobe",
                    "-v",
                    "error",
                    "-select_streams",
                    "v:0",
                    "-show_streams",
                    "-of",
                    "json",
                    str(master),
                ]
            )
        )["streams"][0]
        w, h = int(stream["width"]), int(stream["height"])
        count = int(stream.get("nb_frames", 0))
        fps = 25
        if (
            stream["codec_name"] != "prores"
            or not stream["pix_fmt"].startswith("yuva")
            or stream["r_frame_rate"] != "25/1"
            or not 1 <= count <= 300
            or max(w, h) > 2048
        ):
            raise ValueError(
                "动画需要 25 fps、最长 12 秒、带透明通道的 ProRes 4444 MOV。"
            )
        with tempfile.TemporaryDirectory(dir=stage) as decoded:
            run(
                [
                    "ffmpeg",
                    "-v",
                    "error",
                    "-i",
                    str(master),
                    "-map",
                    "0:v:0",
                    "-vf",
                    "scale=640:480:force_original_aspect_ratio=decrease",
                    "-pix_fmt",
                    "rgba",
                    "-frames:v",
                    str(count),
                    str(Path(decoded) / "%04d.png"),
                ]
            )
            frames = sorted(Path(decoded).glob("*.png"))
            visible = []
            if len(frames) != count:
                raise ValueError("动画帧数与文件记录不一致。")
            for n, path in enumerate(frames):
                with Image.open(path) as im:
                    lo, hi = frame_preview(im, stage, n)
                if lo != 0:
                    raise ValueError("动画含有整幅不透明背景。")
                if hi >= 32:
                    visible.append(n)
            if not visible:
                raise ValueError("动画没有可见画面。")
            poster = min(visible, key=lambda n: abs(n - count * 0.55))
    shutil.copyfile(stage / f"f{poster:03}.webp", stage / "poster.webp")
    return dict(
        kind="image" if not fps else "animation",
        width=w,
        height=h,
        frames=count,
        fps=fps,
        poster=poster,
        seconds=count / fps if fps else 0,
    )


def receive(root, bundle):
    home = root / "motion-samples"
    home.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=home, prefix=".load-") as tmp:
        stage = Path(tmp) / "sample"
        stage.mkdir()
        with zipfile.ZipFile(bundle) as z:
            infos = z.infolist()
            seen = set()
            if len(infos) > 320 or sum(i.file_size for i in infos) > LIMIT:
                raise ValueError("素材或源文件太大。")
            for info in infos:
                name = info.filename
                p = PurePosixPath(name)
                if (
                    name not in ("media.png", "media.mov")
                    and not (
                        len(p.parts) >= 2
                        and p.parts[0] == "sources"
                        and p.suffix.lower() in SOURCE_TYPES
                    )
                    or not p.parts
                    or any(
                        not re.fullmatch(r"[\w. -]{1,120}", s)
                        or s in (".", "..")
                        or s.endswith((".", " "))
                        for s in p.parts
                    )
                    or p.as_posix() != name
                    or name.casefold() in seen
                    or info.is_dir()
                ):
                    raise ValueError("素材包包含无效文件名。")
                seen.add(name.casefold())
                dest = stage.joinpath(*p.parts)
                dest.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info) as src, dest.open("wb") as fh:
                    shutil.copyfileobj(src, fh)
        masters = list(stage.glob("media.*"))
        if len(masters) != 1:
            raise ValueError("需要一个透明 PNG 或 MOV 主文件。")
        signature = hashlib.sha256()
        for p in sorted(stage.rglob("*")):
            if p.is_file():
                signature.update(p.relative_to(stage).as_posix().encode() + b"\0")
                with p.open("rb") as f:
                    signature.update(
                        hashlib.file_digest(f, "sha256").digest()
                        if hasattr(hashlib, "file_digest")
                        else hashlib.sha256(f.read()).digest()
                    )
        key = signature.hexdigest()
        dest = folder(root, key)
        if not dest.exists():
            meta = dict(id=key, **inspect(stage, masters[0]))
            write_json(stage / "meta.json", meta)
            try:
                stage.rename(dest)
            except OSError:
                if not dest.is_dir():
                    raise
        return metadata(root, key)


def overlay_png(spec):
    from PIL import Image

    obj, sticker = spec.get("objects"), spec.get("stickers")
    if not (obj or sticker):
        raise ValueError("请从素材册挑一个物件或贴纸。")
    main = (obj or sticker)["files"]["preview"]
    if obj and sticker:
        with (
            Image.open(main) as im,
            Image.open(sticker["files"]["preview"]) as mark,
        ):
            im = im.convert("RGBA")
            mark = mark.convert("RGBA")
            mark.thumbnail(
                (im.width // 3, im.height // 3), Image.Resampling.LANCZOS
            )
            anchors = obj.get("tokens", {}).get("anchors", {})
            tip = sticker.get("tokens", {}).get("anchor")
            x, y = im.width - mark.width - 12, 12
            point_marks = {
                "pin",
                "loupe",
                "focus",
                "leader",
                "tap",
                "dragtrail",
                "rotatearc",
                "dimension",
                "level",
            }
            if sticker["id"] not in point_marks and tip:
                bounds = im.getbbox()
                if bounds:
                    x = min(
                        im.width - mark.width - 4, bounds[2] - mark.width // 3
                    )
                    y = max(4, bounds[1] - mark.height // 4)
            if sticker["id"] in point_marks and anchors and tip:
                target = (
                    "tare"
                    if sticker["id"] == "tap" and "tare" in anchors
                    else next(iter(anchors))
                )
                u, v = anchors[target]
                x = round(u * im.width - tip[0] / 192 * mark.width)
                y = round(v * im.height - tip[1] / 128 * mark.height)
                x = max(0, min(x, im.width - mark.width))
                y = max(0, min(y, im.height - mark.height))
                if sticker["id"] == "loupe":
                    from PIL import ImageDraw

                    radius = max(4, round(33 * mark.width / 192))
                    cx, cy = round(u * im.width), round(v * im.height)
                    half = max(2, radius // 2)
                    zoom = im.crop(
                        (cx - half, cy - half, cx + half, cy + half)
                    ).resize((radius * 2, radius * 2), Image.Resampling.LANCZOS)
                    mask = Image.new("L", zoom.size)
                    ImageDraw.Draw(mask).ellipse(
                        (0, 0, 2 * radius - 1, 2 * radius - 1), fill=255
                    )
                    im.paste(
                        zoom,
                        (
                            x + round(78 * mark.width / 192) - radius,
                            y + round(51 * mark.height / 128) - radius,
                        ),
                        mask,
                    )
            im.alpha_composite(mark, (x, y))
            result = io.BytesIO()
            im.save(result, format="PNG")
            return result.getvalue()
    return Path(main).read_bytes()


def layout_html(spec):
    style = spec["styles"]
    palette = spec.get("palettes") or brief({"palettes": "atelier"})["palettes"]
    def relative_entry(group):
        entry = spec.get(group)
        if not entry:
            return None
        return dict(entry, files={key: entry["id"] + Path(path).suffix
                                  for key, path in entry["files"].items()})

    inputs = [style, palette, relative_entry("objects"), relative_entry("stickers")]
    args = json.dumps(inputs, ensure_ascii=False).replace("<", r"\u003c")
    page = (LIBRARY / "index.html").read_text(encoding="utf8")
    css = page.split('<style id="scene-css">', 1)[1].split("</style>", 1)[0]
    script = (LIBRARY / "layout.js").read_text(encoding="utf8")
    return ('<!doctype html><html lang="zh-CN"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            '<title>网页排版小样</title><style>body{margin:4vw auto;max-width:720px;padding:12px}'
            + css + '</style><body><script>' + script
            + '\ndocument.body.append(scene(...' + args + '))</script></body></html>')


def library_sources(archive, spec, prefix):
    obj, sticker = spec.get("objects"), spec.get("stickers")
    names = {}

    def write(name, value):
        archive.writestr(prefix + name, value)
        names[name] = prefix + name

    refs = {group: entry["assetId"] for group, entry in spec.items()}
    write("asset-ids.json", json.dumps(refs, ensure_ascii=False, indent=2))
    if spec.get("styles"):
        write("layout.html", layout_html(spec))
    for entry in (obj, sticker):
        if entry:
            for path in entry["files"].values():
                name = entry["id"] + Path(path).suffix
                archive.write(path, prefix + name)
                names[name] = prefix + name
    return names


def from_library(root, raw):
    spec = brief(raw)
    with tempfile.TemporaryDirectory() as tmp:
        bundle = Path(tmp) / "library.zip"
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("media.png", overlay_png(spec))
            library_sources(archive, spec, "sources/")
            archive.writestr(
                "sources/style.json", json.dumps(selection(raw), ensure_ascii=False)
            )
        return receive(root, bundle)
