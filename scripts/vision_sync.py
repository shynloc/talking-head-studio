"""Check the published Workbench and VisionBuddy compatibility agreement."""
import argparse
import json
from pathlib import Path

from core import ROOT, VERSION
import vision_library as vision

FEATURE_IDS = {
    "components": {"UI-003"},
    "practice": {"KIT-001", "KIT-002", "KIT-003"},
    "lessonEffects": {"DEMO-010", "DEMO-011", "DEMO-012"},
    "styles": {"WEB-019", "WEB-020", "WEB-021"},
    "stickers": {"ICO-002"},
}


def check_catalog(raw):
    data = json.loads(raw)
    for group, required in FEATURE_IDS.items():
        missing = required - {entry["assetId"] for entry in data.get(group, [])}
        if missing:
            raise ValueError("素材目录缺少工作台已启用的功能：" + "、".join(sorted(missing)))
    return data


def check_source(repository):
    published = (repository / "VERSION").read_text(encoding="utf8").strip()
    agreement = json.loads((repository / "compatibility.json").read_bytes())
    expected = vision.PAIR["recommendedRelease"]
    if published != expected:
        raise ValueError(f"工作台指定使用 {expected}，VisionBuddy 源码为 {published}。请成对更新。")
    if agreement["rendererVersion"] not in vision.PAIR["rendererVersions"]:
        raise ValueError("工作台需要支持素材库的渲染器版本。")
    if vision.version_key(agreement["minimumWorkbench"]) > vision.version_key(VERSION):
        raise ValueError("先更新工作台，达到素材库声明的最低版本。")
    shared = repository / "site/visual"
    studio = ROOT / "assets/workbench/motion/visual"
    for name in vision.PAIR["sharedFiles"]:
        if (shared / name).read_bytes() != (studio / name).read_bytes():
            raise ValueError(f"两仓库共用的 {name} 已分叉，请同步源码。")
    data = check_catalog((shared / "catalog.json").read_bytes())
    print(f"Talking Head Studio {VERSION} × VisionBuddy {published} · {len(data['practice'])} 个口播搭配。")


def check_online():
    domain = vision.ORIGIN
    library = json.loads(vision.fetch(domain + "/latest.json", 32768, 10))
    release = vision.valid_version(library["libraryRelease"])
    if release != vision.PAIR["recommendedRelease"]:
        raise ValueError(f"公网素材库为 {release}，当前工作台配对版本为 {vision.PAIR['recommendedRelease']}。")
    expected_path = f"/releases/{release}/manifest.json"
    if library["manifest"] != expected_path:
        raise ValueError("公网发布指针的清单路径无效。")
    data = vision.manifest(vision.fetch(domain + expected_path, vision.MAX_MANIFEST, 10), release)
    name = "site/visual/catalog.json"
    body = vision.fetch(domain + f"/releases/{release}/" + name, data["files"][name]["size"], 15)
    check_catalog(vision.verify(body, data["files"][name]))
    print(f"公网 VisionBuddy {release} 的清单、哈希和工作台功能通过核验。")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--source", type=Path)
    mode.add_argument("--online", action="store_true")
    args = parser.parse_args()
    if args.online:
        check_online()
    else:
        check_source(args.source.resolve())
