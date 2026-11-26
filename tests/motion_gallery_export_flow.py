"""Play the added effects and round-trip a free composition through an editable package."""
import argparse
import base64
import json
import re
import subprocess
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from PIL import Image
from playwright.sync_api import expect, sync_playwright


def check(url, out):
    out.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge")
        page = browser.new_page(viewport={"width": 1400, "height": 940}, reduced_motion="reduce")
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(url + "/motion/index.html?show=new")
        cards = page.locator("#cards .card")
        expect(cards).to_have_count(8)
        expect(page.locator("#recipes .recipe")).to_have_count(16)
        expect(page.locator("#export-mix")).to_be_disabled()
        # Every new effect draws distinct frames, real alpha and artwork.
        stats = page.evaluate("""() => DATA.recent.map(id => {
          const c = document.createElement('canvas'); c.width = 480; c.height = 180;
          const frames = [.1, .31, .53, .75, .91].map(t => {
            draw(c, t, [id], 'book', true);
            const rgba = c.getContext('2d').getImageData(0, 0, c.width, c.height).data;
            return {pixels: c.toDataURL(), alpha: rgba[3], ink: rgba.some((x,i)=> i%4===3 && x>100)};
          });
          return [id, new Set(frames.map(f=>f.pixels)).size, frames.every(f=>f.alpha===0), frames.some(f=>f.ink)]
        })""")
        assert all(n > 1 and alpha and ink for _, n, alpha, ink in stats), stats
        page.locator("#search").fill("不可能匹配的名字")
        page.get_by_role("button", name="清除筛选").click()
        expect(cards).to_have_count(108)
        for query, name in [("旁批", "marginNote"), ("长按", "holdConfirm"), ("修图前后", "compareWipe"), ("调档", "dialTurn")]:
            page.locator("#search").fill(query)
            expect(page.locator(f'[data-id="{name}"]')).to_be_visible()
        page.locator('[data-id="dialTurn"] .pick').click()
        page.locator("#jumpmix").click()
        page.locator("#step-labels").locator("xpath=ancestor::details/summary").click()
        page.locator("#step-labels").fill("微火、小火、中火")
        page.locator("#duration").locator("xpath=ancestor::details/summary").click()
        page.locator("#duration").fill("3")
        page.locator("#bg").select_option("dark")
        page.locator("#scrub").fill("50")
        png = page.locator("#mix").evaluate("(c)=>c.toDataURL().split(',')[1]")
        preview = Image.open(BytesIO(base64.b64decode(png))).convert("RGBA")
        expect(page.locator("#prompt")).to_have_value(re.compile("微火.*小火.*中火", re.S))
        pack = out / "旋钮调档-透明动画.zip"
        with page.expect_download(timeout=120000) as downloaded:
            page.locator("#export-mix").click()
        downloaded.value.save_as(pack)
        with ZipFile(pack) as z:
            assert z.testzip() is None
            manifest = json.loads(z.read("素材搭配.json"))["items"][0]
            assert manifest["standalone"] and manifest["quote"] == "" and manifest["ids"] == ["dialTurn"]
            still = Image.open(BytesIO(z.read(next(n for n in z.namelist() if n.endswith(".png"))))).convert("RGBA")
            assert still.tobytes() == preview.tobytes() and still.getchannel("A").getextrema() == (0, 255)
            movie = out / "旋钮调档.mov"
            movie.write_bytes(z.read(next(n for n in z.namelist() if n.endswith(".mov"))))
        stream = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_streams", "-of", "json", movie]))["streams"][0]
        assert (stream["profile"],stream["nb_frames"],stream["r_frame_rate"]) == ("4444","75","25/1")
        assert stream["pix_fmt"].startswith("yuva")

        # The two foreground images travel in the package. The preview backdrop stays local.
        page.locator("#search").fill("修图前后")
        page.get_by_role("button", name="移除把旋钮转到下一档").click()
        page.locator('[data-id="compareWipe"] .pick').click()
        for slot, color in [("image-a", "#ababab"), ("image-b", "#e87a41")]:
            file = out / (slot + ".png")
            Image.new("RGBA", (120, 70), color).save(file)
            page.locator("#" + slot).set_input_files(file)
            expect(page.locator("#export-mix")).to_be_enabled()
        page.locator("#scrub").fill("50")
        page.route("**/api/motion/status", lambda route: route.fulfill(json={"ready": False}))
        page.locator("#export-mix").click()
        expect(page.locator("#mix-progress")).to_contain_text("FFmpeg")
        expect(page.locator("#export-mix")).to_be_enabled()
        page.unroute("**/api/motion/status")
        with page.expect_download(timeout=120000) as photos:
            page.locator("#export-mix").click()
        with ZipFile(photos.value.path()) as z:
            photo = json.loads(z.read("素材搭配.json"))["items"][0]
            assert photo["ids"] == ["compareWipe"] and set(photo["files"]) == {"imageA", "imageB"}
            still = Image.open(BytesIO(z.read(next(n for n in z.namelist() if n.endswith(".png")))))
            colors = {color for _, color in still.convert("RGBA").getcolors(still.width * still.height)}
            assert {(171, 171, 171, 255), (232, 122, 65, 255), (0, 0, 0, 0)} <= colors
        page.locator("#nav-example").click()
        expect(page.locator("#manuscript")).to_be_editable()
        page.locator("#restore-file").set_input_files(pack)
        expect(page.locator(".pack-item")).to_have_count(1)
        page.get_by_role("button", name="改这款").click()
        expect(page.locator("#selected-quote")).to_have_text("动效词库里的自由搭配")
        page.locator("#scrub").fill("37")
        reopened = page.locator("#preview").evaluate("(c)=>c.toDataURL().split(',')[1]")
        assert Image.open(BytesIO(base64.b64decode(reopened))).convert("RGBA").tobytes() == preview.tobytes()
        page.locator("#seconds").select_option("1")
        page.locator("#approve").click()
        with page.expect_download(timeout=120000) as revised:
            page.locator("#export").click()
        with ZipFile(revised.value.path()) as z:
            assert json.loads(z.read("素材搭配.json"))["items"][0]["seconds"] == 1
        assert not errors, errors
        browser.close()
        print("Eight moving transparent previews, keyword search, gallery export, matching PNG, editable import and re-export passed.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    check(args.url, args.out)
