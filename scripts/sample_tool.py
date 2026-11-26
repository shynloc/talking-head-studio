"""Make a transparent sample on the Agent host, then deliver it using its task receipt."""

import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request
import zipfile

from PIL import Image
from agent_client import AgentClient
from core import ROOT
from launch import LOCAL_HTTP, request_json
from runtime import configure_tool_path
from motion_samples import LIMIT


def encode(frames, target):
    if target.exists():
        raise ValueError("输出文件已存在，请为这个版本另取文件名。")
    target.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=target.parent) as tmp:
        result = Path(tmp) / "media.mov"
        proc = subprocess.Popen(
            [
                "ffmpeg",
                "-v",
                "error",
                "-f",
                "image2pipe",
                "-framerate",
                "25",
                "-c:v",
                "png",
                "-i",
                "pipe:0",
                "-an",
                "-c:v",
                "prores_ks",
                "-profile:v",
                "4",
                "-pix_fmt",
                "yuva444p10le",
                "-alpha_bits",
                "16",
                "-threads",
                "4",
                str(result),
            ],
            stdin=subprocess.PIPE,
        )
        try:
            for frame in frames:
                if isinstance(frame, bytes):
                    proc.stdin.write(frame)
                else:
                    frame.save(proc.stdin, format="PNG")
            proc.stdin.close()
            if proc.wait() != 0:
                raise ValueError("透明 MOV 编码失败。")
            result.replace(target)
        finally:
            if proc.poll() is None:
                proc.kill()
                proc.wait()


def html_frames(path, w, h, count):
    from playwright.sync_api import sync_playwright

    engine = ROOT / "vendor/html-creator-studio-core/shared/frame-styles.mjs"
    core_js = re.sub(r"\bexport\s+", "", engine.read_text(encoding="utf8"))
    with sync_playwright() as pw:
        try:
            browser = pw.chromium.launch(headless=True)
        except Exception:
            browser = pw.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(
            viewport={"width": w, "height": h},
            device_scale_factor=1,
            service_workers="block",
        )
        page.route("**/*", lambda route: route.abort())
        page.add_init_script(script=core_js)
        # set_content does not navigate, so inject the frame library before inline scene scripts run.
        source = path.read_text(encoding="utf-8-sig")
        library = "<script>" + core_js + "</script>"
        marker = re.match(r"\s*<!doctype[^>]*>", source, flags=re.I)
        offset = marker.end() if marker else 0
        page.set_content(source[:offset] + library + source[offset:], wait_until="load")
        page.evaluate("document.fonts.ready")
        if not page.evaluate("typeof window.renderFrame==='function'"):
            raise ValueError("HTML 需要提供 window.renderFrame(frame,total)。")
        for i in range(count):
            page.evaluate("([i,n])=>window.renderFrame(i,n)", [i, count])
            yield page.screenshot(omit_background=True, animations="allow")
        browser.close()


def sticker_frames(path, action, count, w, h):
    spec = importlib.util.spec_from_file_location(
        "gif_factory", ROOT / "vendor/gif-factory/scripts/export_pack.py"
    )
    factory = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(factory)
    with Image.open(path) as img:
        sprite = img.convert("RGBA")
    sprite.thumbnail((int(w * 0.73), int(h * 0.73)), Image.Resampling.LANCZOS)
    for i in range(count):
        dx, dy, squash, angle = factory.motion(action, i / count)
        scale = min(w, h) / 150
        size = (
            max(1, round(sprite.width * (1 + squash * 0.009))),
            max(1, round(sprite.height * (1 - squash * 0.009))),
        )
        overlay = sprite.resize(size, Image.Resampling.LANCZOS).rotate(
            angle, Image.Resampling.BICUBIC, expand=True
        )
        canvas = Image.new("RGBA", (w, h))
        canvas.alpha_composite(
            overlay,
            (
                round((w - overlay.width) / 2 + scale * dx),
                round((h - overlay.height) / 2 + scale * dy),
            ),
        )
        yield canvas


def deliver(args):
    client = AgentClient(args.url, args.agent)
    token = request_json(client.url + "/api/bootstrap")["token"]
    ext = args.media.suffix.lower()
    if ext not in (".png", ".mov"):
        raise ValueError("请选择透明 PNG 或 MOV。")
    with tempfile.TemporaryDirectory() as tmp:
        bundle = Path(tmp) / "sample.zip"
        with zipfile.ZipFile(bundle, "w", zipfile.ZIP_DEFLATED, compresslevel=1) as z:
            z.write(args.media, "media" + ext)
            for path in args.source:
                z.write(path, "sources/" + path.name)
        size = bundle.stat().st_size
        if size > LIMIT:
            raise ValueError("素材包太大。")
        url = (
            client.url
            + "/api/motion/deliver?"
            + urlencode({"id": args.task, "agent": args.agent})
        )
        with bundle.open("rb") as f:
            req = Request(
                url,
                f,
                headers={
                    "X-Studio-Token": token,
                    "X-Studio-Receipt": args.receipt,
                    "Content-Type": "application/zip",
                    "Content-Length": str(size),
                },
                method="POST",
            )
            with LOCAL_HTTP.open(req, timeout=360) as res:
                return json.load(res)


def main():
    configure_tool_path()
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for cmd in ("html", "gif"):
        p = sub.add_parser(cmd)
        p.add_argument("input", type=Path)
        p.add_argument("output", type=Path)
        p.add_argument("--seconds", type=int, choices=range(1, 13), default=3)
        p.add_argument("--width", type=int, default=640)
        p.add_argument("--height", type=int, default=480)
        if cmd == "gif":
            p.add_argument(
                "--action",
                choices=[
                    "jump",
                    "nod",
                    "sway",
                    "pulse",
                    "pop",
                    "breathe",
                    "peek",
                    "tremble",
                    "stomp",
                ],
                default="jump",
            )
    p = sub.add_parser("deliver")
    p.add_argument("task")
    p.add_argument("--agent", choices=("codex", "workbuddy"), required=True)
    p.add_argument("--receipt", required=True)
    p.add_argument("--url", default="http://127.0.0.1:8765")
    p.add_argument("--media", type=Path, required=True)
    p.add_argument("--source", type=Path, action="append", default=[])
    args = parser.parse_args()
    try:
        if args.command == "deliver":
            print(json.dumps(deliver(args), ensure_ascii=False))
            return
        if any(n < 16 or n > 2048 or n % 2 for n in [args.width, args.height]):
            raise ValueError("宽高应为 16–2048 的偶数。")
        frames = (
            html_frames(args.input, args.width, args.height, 25 * args.seconds)
            if args.command == "html"
            else sticker_frames(
                args.input, args.action, 25 * args.seconds, args.width, args.height
            )
        )
        encode(frames, args.output)
        print(args.output)
    except HTTPError as exc:
        parser.exit(1, json.loads(exc.read()).get("error", str(exc)) + "\n")
    except (ValueError, OSError) as exc:
        parser.exit(1, str(exc) + "\n")


if __name__ == "__main__":
    main()
