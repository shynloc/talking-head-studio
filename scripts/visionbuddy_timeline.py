"""Preview and import VisionBuddy's approved materials into a Workbench timeline."""

import hashlib
import json
import math
from pathlib import Path
import re
import shutil
import struct
import subprocess
from tempfile import NamedTemporaryFile, TemporaryDirectory
from zipfile import ZipFile

import timeline
import motion_package
import motion_samples
from core import Conflict, LOCK, inverse_time, normalized, source, uid

MAX_JSON = 24 * 1024**2
ROW = re.compile(r"r\d{4}")


def finite(value):
    return type(value) in (int, float) and math.isfinite(value)


def read_json(archive, name):
    if archive.getinfo(name).file_size > MAX_JSON:
        raise ValueError("VisionBuddy 时间清单过大。")
    return json.loads(archive.read(name))


def old_movie_size(archive, member):
    if archive.getinfo(member).file_size > motion_samples.LIMIT:
        raise ValueError("透明动画文件超过工作台上限。")
    probe = shutil.which("ffprobe")
    if not probe:
        raise ValueError("读取旧版透明 MOV 的尺寸需要 FFprobe。")
    with TemporaryDirectory(prefix="visionbuddy-shape-") as folder:
        path = Path(folder) / "inspect.mov"
        with archive.open(member) as src, path.open("xb") as dest:
            shutil.copyfileobj(src, dest)
        result = subprocess.run([
            probe, "-v", "error", "-protocol_whitelist", "file,pipe", "-f", "mov",
            "-select_streams", "v:0", "-show_entries", "stream=width,height", "-of", "json", str(path)
        ], stdin=subprocess.DEVNULL, capture_output=True, timeout=30)
    if result.returncode:
        raise ValueError("无法读取透明 MOV 尺寸。")
    streams = json.loads(result.stdout).get("streams", [])
    if not streams:
        raise ValueError("透明 MOV 没有可用视频画面。")
    return streams[0]


def parse(bundle):
    with ZipFile(bundle) as archive:
        names = archive.namelist()
        if len(names) > 22000 or len(set(names)) != len(names):
            raise ValueError("素材包文件过多或重复。")
        if "素材搭配.json" not in names or "时间与素材.json" not in names:
            raise ValueError("请从 VisionBuddy 导出已采用的 PNG 或 MOV 素材包。")
        timing = read_json(archive, "时间与素材.json")
        packed = read_json(archive, "素材搭配.json")
        if (not isinstance(timing, dict) or timing.get("format") != "visionbuddy-timeline/1"
                or timing.get("timeBasis") not in (None, "source")
                or not isinstance(timing.get("rows"), list) or len(timing["rows"]) > 4000
                or not isinstance(packed, dict) or packed.get("format") != "talking-head-motion/2"):
            raise ValueError("VisionBuddy 素材包格式无效。")
        if timing.get("composition", "presenter") not in ("presenter", "demo", "mixed"):
            raise ValueError("素材包的画面主次无效。")
        items = motion_package.validate(packed)
        seen, chosen = set(), []
        for row in timing["rows"]:
            if (not isinstance(row, dict) or not isinstance(row.get("id"), str) or not ROW.fullmatch(row["id"])
                    or row["id"] in seen or not isinstance(row.get("quote"), str) or not row["quote"].strip()
                    or row.get("state") not in ("adopted", "plain", "none", "blocked", "pending", "skipped")):
                raise ValueError("VisionBuddy 原句清单无效。")
            if (row.get("composition") not in (None, "presenter", "demo")
                    or row.get("compositionOrigin") not in (None, "auto", "user")
                    or row.get("compositionOrigin") and not row.get("composition")):
                raise ValueError("素材包的逐句画面主次无效。")
            seen.add(row["id"])
            if row["state"] == "adopted":
                chosen.append(row)
        if len(chosen) != len(items):
            raise ValueError("已采用的原句与导出的媒体数量不同。")
        for row, item in zip(chosen, items):
            name = row.get("media")
            if (row["quote"] != item["quote"] or not isinstance(name, str)
                    or name != item.get("packageMedia") or name not in names
                    or Path(name).suffix not in (".png", ".mov") or "sample" not in item):
                raise ValueError("VisionBuddy 原句和媒体无法一一对应。")
            place = row.get("placement")
            if (not isinstance(place, dict) or place.get("side") not in ("left", "right")
                    or not finite(place.get("scale")) or not .20 <= place["scale"] <= .65):
                raise ValueError("VisionBuddy 摆放尺寸无效。")
            if "start" in place or "end" in place:
                a, b = place.get("start"), place.get("end")
                if not finite(a) or not finite(b) or not 0 <= a < b or b - a > 12.01:
                    raise ValueError("VisionBuddy 原片时间码无效。")
            if Path(name).suffix == ".mov" and (not finite(item.get("seconds")) or not 0 < item["seconds"] <= 12):
                raise ValueError("VisionBuddy 动画时长无效。")
            shape = item.get("visionbuddyMedia")
            if shape is None and name.endswith(".png"):
                with archive.open(name) as png:
                    header = png.read(24)
                if len(header) != 24 or header[:8] != b"\x89PNG\r\n\x1a\n":
                    raise ValueError("VisionBuddy PNG 文件无效。")
                shape = dict(zip(("width", "height"), struct.unpack(">II", header[16:24])))
            if shape is None:
                shape = old_movie_size(archive, name)
            if (not isinstance(shape, dict) or any(type(shape.get(k)) is not int or not 1 <= shape[k] <= 4096
                                                    for k in ("width", "height"))):
                raise ValueError("VisionBuddy 透明素材尺寸无效。")
            item["visionbuddyMedia"] = shape
    return timing, list(zip(chosen, items))


def immutable_key(values):
    return hashlib.sha256(json.dumps(values, sort_keys=True, ensure_ascii=False).encode("utf8")).hexdigest()


def source_check(p, timing):
    recording = source(p)
    if not recording or p["timeline"]["mode"] != "actual":
        return "请先在工作台把时间线对齐到视频，或改用原句定位。"
    duration = timing.get("sourceDuration")
    if duration is not None and (not finite(duration) or abs(duration - recording["duration"]) > .18):
        return "包内时间码与当前原片时长不符，可改用原句定位。"
    identity = timing.get("recording")
    if identity:
        try:
            name, size, *_ = json.loads(identity) if isinstance(identity, str) else identity
            path = Path(recording["path"])
            own_name = recording.get("name") or path.name
            if name.casefold() != own_name.casefold() or path.stat().st_size != size:
                return "审核包关联的是另一份原片，可改用原句定位。"
        except (OSError, ValueError, TypeError, AttributeError, KeyError):
            return "无法核对包里的原片身份，可改用原句定位。"
    return ""


def fragments(p, a, b, source_clock):
    if not source_clock:
        length = sum(c["duration"] for c in p["timeline"]["clips"] if c["track"] == "main")
        return [(a, min(b, length), 0)] if a + .001 < min(b, length) else []
    result = []
    for clip in p["timeline"]["clips"]:
        if (clip["track"] != "main" or clip.get("asset_id") or clip.get("source_id") != p["source_id"]
                or clip.get("enabled", True) is False):
            continue
        begin = clip.get("source_in", 0)
        lo, hi = max(a, begin), min(b, begin + clip["duration"])
        if hi > lo + .001:
            t = clip["start"] + lo - begin
            result.append((t, t + hi - lo, lo - a))
    return result


def quote_events(p):
    if p["timeline"]["mode"] == "actual":
        segments = p.get("transcript") or []
        if segments:
            return [(normalized(s["text"]), s["start"], s["end"]) for s in segments], True
        mapping = (p.get("rough") or {}).get("mapping", [])
        rows = []
        for cap in p.get("captions", []):
            a = inverse_time(cap["start"], mapping)
            b = inverse_time(cap["end"], mapping, end=True)
            if a is not None and b is not None and b > a:
                rows.append((normalized(cap["text"]), a, b))
        return rows, True
    pages = {pg["id"]: pg for pg in p["pages"]}
    rows = []
    for clip in p["timeline"]["clips"]:
        pg = pages.get(clip.get("page_id"))
        if clip["track"] != "main" or not pg:
            continue
        phrases = [normalized(s["text"]) for s in pg.get("sentences", [])] or [normalized(pg["text"])]
        count = sum(map(len, phrases))
        cursor = clip["start"]
        for phrase in phrases:
            if phrase and count:
                end = cursor + clip["duration"] * len(phrase) / count
                rows.append((phrase, cursor, end))
                cursor = end
    return rows, False


def find_quote(events, phrase):
    target = normalized(phrase)
    events = [(words, a, b) for words, a, b in events if words and b > a]
    text = "".join(words for words, _, _ in events)
    first = text.find(target) if target else -1
    if first < 0:
        return None, "找不到对应原句。"
    if text.find(target, first + 1) >= 0:
        return None, "原句出现多次，请手动选位置或使用原片时间码。"
    seen = 0
    for words, a, b in events:
        if seen <= first < seen + len(words):
            return a + (b - a) * (first - seen) / len(words), ""
        seen += len(words)
    return None, "无法定位原句。"


def layout(p, placement, shape):
    recording = source(p)
    ratio = (recording.get("width") or 1280) / (recording.get("height") or 720) * shape["height"] / shape["width"]
    preferred = placement["scale"]
    side = placement["side"]
    border, y = .05, .07
    px, py, pw, ph = p["settings"]["protected_rect"]
    cap = min(preferred, (.90 - y) / ratio)
    if ph > 0 and pw > 0 and py + ph > y:
        side_space = px - border if side == "left" else 1 - border - px - pw
        top_space = (py - y) / ratio
        cap = min(cap, max(side_space, top_space))
    if cap < .08:
        return None
    width = math.floor(cap * 10000) / 10000
    height = math.floor(width * ratio * 10000) / 10000
    x = border if side == "left" else 1 - border - width
    return {"x": round(x, 4), "y": y, "width": width, "height": height}


def preview(p, timing, items, method):
    if method not in ("auto", "quote"):
        raise ValueError("请选择原片时间码或原句定位。")
    if p["timeline"]["mode"] == "actual":
        timeline.validate_output(p)
    elif p.get("source_id"):
        raise ValueError("当前原片还没对齐到工作台时间线。请先完成粗剪和时间线校准。")
    events, quote_clock = quote_events(p)
    old = {clip.get("visionbuddyRow") for clip in p["timeline"]["clips"]}
    matches, pending = {}, []
    for row, item in items:
        place, sid = row["placement"], item["sample"]["id"]
        identity = [row["id"], row["quote"], sid, place]
        arrangement = {}
        if timing.get("composition"):
            arrangement["bundle_composition"] = timing["composition"]
        if row.get("composition"):
            field = "composition" if row.get("compositionOrigin") == "user" else "suggested_composition"
            arrangement[field] = row["composition"]
            identity.extend([field, row["composition"]])
        elif timing.get("composition") == "demo":
            identity.append("demo")
        if timing.get("composition") in ("mixed", "demo") or row.get("composition") == "demo":
            arrangement.update(presenter_side=place["side"], presenter_scale=place["scale"])
        key = immutable_key(identity)
        record = {"id": row["id"], "quote": row["quote"], "title": item["title"], "key": key}
        if key in old:
            matches[row["id"]] = {**record, "state": "existing", "message": "已在当前时间线。"}
            continue
        timed = "start" in place and method != "quote"
        if timed:
            issue = source_check(p, timing)
            start, end = place["start"], place["end"]
            source_clock = True
        else:
            start, issue = find_quote(events, row["quote"])
            span = item.get("seconds") if finite(item.get("seconds")) and item["seconds"] > 0 else 3
            end = start + span if start is not None else None
            source_clock = quote_clock
        shape = item["visionbuddyMedia"]
        if not issue and item["packageMedia"].endswith(".mov"):
            end = min(end, start + item["seconds"])
        intervals = fragments(p, start, end, source_clock) if not issue else []
        if not intervals and not issue:
            issue = "该时间段已被剪掉，或落在主画面之外。"
        directions = [timeline.demo_first(p, {"track":"sticker","visionbuddyRow":key,"start":a,**arrangement})
                      for a, _, _ in intervals]
        demo = bool(directions) and all(directions)
        coords = layout(p, place, shape)
        if demo and coords is None:
            coords = {"x": .05, "y": .04, "width": .35, "height": .20}
        if not issue and coords is None:
            issue = "指定一侧的留白不足，请调整人物保护区或素材位置。"
        if issue:
            matches[row["id"]] = {**record, "state": "unplaced", "message": issue}
            continue
        pieces = [{"start": round(a, 6), "end": round(b, 6), "sourceIn": round(offset, 6), **coords}
                  for a, b, offset in intervals]
        warning = ("演示为主，人物位于" + ("左下" if place["side"] == "left" else "右下") + "。") if demo else (
            "已按人物保护区收窄。" if coords["width"] + .0005 < place["scale"] else "")
        matches[row["id"]] = {**record, "state": "ready", "basis": "source" if timed else "quote",
                              "pieces": pieces, "message": warning}
        pending.append((record, item, pieces, arrangement))
    reviewed = [matches.get(row["id"]) or {k: row[k] for k in ("id", "quote", "state")}
                for row in timing["rows"]]
    return reviewed, pending


def arrange(store, pid, archive, version, method, action="preview", receipt=""):
    timing, items = parse(archive)
    with LOCK:
        p = store.load(pid)
        if p["version"] != version:
            raise Conflict("工程已更新，请重新检查 VisionBuddy 摆放位置。")
        rows, pending = preview(p, timing, items, method)
        check = immutable_key([pid, version, method, timing, [item["sample"]["id"] for _, item in items]])
        result = {"rows": rows, "receipt": check, "version": version, "added": 0, "planned": len(pending)}
        if action == "preview":
            return result
        if action != "apply" or receipt != check:
            raise Conflict("请先检查当前工程的摆放位置。")
        if not pending:
            return {**result, "project": p}

        archive.seek(0)
        verified = motion_package.restore(store.root, archive)
        samples = {item["sample"]["id"]: item["sample"] for item in verified["items"]}
        assets = {item.get("visionbuddySample"): item for item in p["assets"] if item.get("visionbuddySample")}
        work = store.folder(pid) / "assets" / "visionbuddy"
        work.mkdir(parents=True, exist_ok=True)
        for record, item, pieces, arrangement in pending:
            sid = item["sample"]["id"]
            meta = samples[sid]
            suffix = Path(item["packageMedia"]).suffix
            shape = item["visionbuddyMedia"]
            if (meta["width"], meta["height"]) != (shape["width"], shape["height"]):
                raise ValueError("包内记录的透明素材尺寸与实际文件不同。")
            if sid not in assets:
                master = motion_samples.folder(store.root, sid) / ("media" + suffix)
                target = work / (sid + suffix)
                if not target.is_file():
                    with NamedTemporaryFile(dir=work, prefix=".copy-", delete=False) as staged:
                        partial = Path(staged.name)
                        try:
                            with master.open("rb") as file:
                                shutil.copyfileobj(file, staged)
                        except OSError:
                            staged.close()
                            partial.unlink(missing_ok=True)
                            raise
                    partial.replace(target)
                asset = {"id":uid("asset"), "name":item["title"], "path":str(target),
                         "kind":"animation" if suffix == ".mov" else "image",
                         "width":meta["width"], "height":meta["height"], "duration":meta["seconds"],
                         "visionbuddySample":sid}
                assets[sid] = asset
                p["assets"].append(asset)
            for piece in pieces:
                if suffix == ".mov" and piece["sourceIn"] + piece["end"] - piece["start"] > meta["seconds"] + .01:
                    raise ValueError("审核画面超出透明片段时长，请重新导出素材包。")
                p["timeline"]["clips"].append({
                    "id":uid("clip"), "track":"sticker", "kind":"sticker", "anchor":"absolute", "enabled":True, **arrangement,
                    "name":item["title"], "asset_id":assets[sid]["id"], "visionbuddyRow":record["key"],
                    "start":piece["start"], "duration":round(piece["end"] - piece["start"], 6),
                    "source_in":piece["sourceIn"] if suffix == ".mov" else 0,
                    **{k:piece[k] for k in ("x", "y", "width", "height")},
                })
        p["approvals"].pop("timeline", None)
        p["approvals"].pop("final", None)
        timeline.validate(p)
        result.update(added=len(pending), project=store.save(p, version, label="导入 VisionBuddy 画面草稿"))
    return result

