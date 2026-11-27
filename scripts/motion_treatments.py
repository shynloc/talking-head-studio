"""Sentence-specific alternatives using the same published assets as the visual picker."""

import base64
from functools import lru_cache
import json
from pathlib import Path
import re
import tempfile
import zipfile

import motion_samples as samples
import vision_library as vision


def catalog():
    return read_catalog(vision.data_path("visual/treatments.json"))


@lru_cache(maxsize=12)
def read_catalog(path):
    return {
        row["id"]: row
        for row in json.loads(path.read_text(encoding="utf8"))
    }


def resolve(key, object_id=None):
    item = catalog().get(key) if isinstance(key, str) else None
    if not item and isinstance(key, str):
        item = next((row for row in catalog().values() if row["assetId"] == key.upper()), None)
    if not item or (object_id and item["object"] != object_id):
        raise ValueError("这项演示与所选物件不符，请重新挑选。")
    return item


def alternatives(raw):
    if raw is None:
        return []
    if (
        not isinstance(raw, list)
        or len(raw) > 3
        or any(not isinstance(k, str) for k in raw)
    ):
        raise ValueError("每句可选最多三个素材册中的替代效果。")
    return list(dict.fromkeys(resolve(key)["id"] for key in raw))


def scene_data(context):
    treatment = resolve(context["treatment"], context["visual"].get("objects"))
    visual = context["visual"]
    spec = samples.brief(visual)
    obj = spec["objects"]
    palette = spec.get("palettes") or samples.brief({"palettes": "atelier"})["palettes"]
    quote = context["quote"]
    unit = (
        r"(?:千克|公斤|克|kg|g)"
        if treatment["object"] == "scale"
        else r"(?:毫升|升|mL|ml|L)"
    )
    values = re.findall(
        r"(?<![\d.])(?:\d+(?:\.\d+)?|[零一二三四五六七八九十百千万两半]+)\s*" + unit,
        quote,
        re.I,
    )
    value = values[-1].strip() if values else ""
    ordinal = re.search(r"第([一二三四五1-5])(?:条|格|道)", quote)
    mark = "第" + ordinal[1] + "条刻度" if ordinal else ""
    position = (
        "一二三四五".find(ordinal[1]) + 1
        if ordinal and not ordinal[1].isdigit()
        else int(ordinal[1])
        if ordinal
        else 3
    )
    callouts = {
        "level": mark or value or "液面位置",
        "tare": "归零按键",
        "display": value or "秤面读数",
        "jaw": "夹口",
        "pocket": "侧袋开口",
    }
    data = dict(
        object=treatment["object"],
        kind=treatment["kind"],
        part=treatment["part"],
        colors=palette["colors"],
        value=value or "✓",
        finalLabel=value or "查看读数",
        callout=callouts[treatment["part"]],
        fillY=237 - (position - 1) * 25,
        anchor=obj["tokens"]["anchors"][treatment["part"]],
    )
    data["frames"] = context.get("seconds", 3) * 25
    data["style"] = visual.get("styles", "field")
    if "stickers" in spec:
        sticker = Path(spec["stickers"]["files"]["vector"])
        data["sticker"] = "data:image/svg+xml;base64," + base64.b64encode(
            sticker.read_bytes()
        ).decode("ascii")
    if treatment["kind"] == "still":
        data["png"] = "data:image/png;base64," + base64.b64encode(
            Path(obj["files"]["preview"]).read_bytes()
        ).decode("ascii")
    return data, spec


def render(root, context):
    from sample_tool import html_frames, encode

    data, spec = scene_data(context)
    code = (samples.LIBRARY / "part-demo.html").read_text(encoding="utf8")
    source = code.replace(
        "__SCENE__", json.dumps(data, ensure_ascii=False).replace("<", "\\u003c")
    )
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp)
        html = path / "scene.html"
        html.write_text(source, encoding="utf8")
        static = data["kind"] == "still"
        frames = html_frames(html, 560, 330, 1 if static else context["seconds"] * 25)
        master = path / ("media.png" if static else "media.mov")
        if static:
            try:
                master.write_bytes(next(frames))
            finally:
                frames.close()
        else:
            encode(frames, master)
        with zipfile.ZipFile(
            path / "sample.zip", "w", zipfile.ZIP_DEFLATED, compresslevel=2
        ) as z:
            z.write(master, master.name)
            z.write(html, "sources/scene.html")
            obj = spec["objects"]
            z.write(obj["files"]["model"], "sources/" + obj["id"] + ".glb")
            if "stickers" in spec:
                z.write(
                    spec["stickers"]["files"]["vector"],
                    "sources/" + spec["stickers"]["id"] + ".svg",
                )
            z.writestr(
                "sources/recipe.json",
                json.dumps(
                    {
                        k: context[k]
                        for k in ("quote", "visual", "treatment", "seconds")
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
            )
        return samples.receive(root, path / "sample.zip")
