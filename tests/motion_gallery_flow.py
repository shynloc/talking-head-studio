"""Exercise the visual gallery, independent browsing, and resumable material desks."""
import argparse
from io import BytesIO
from pathlib import Path
from zipfile import ZipFile

from PIL import Image
from playwright.sync_api import expect, sync_playwright


def check(base_url, screenshot=None):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(channel="msedge")
        context = browser.new_context(viewport={"width": 1440, "height": 960},
                                      reduced_motion="reduce", permissions=["clipboard-read", "clipboard-write"])
        page = context.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        url = base_url + "/motion/index.html"
        page.goto(url)
        cards = page.locator("#cards .card")
        expect(cards).to_have_count(100)
        expect(page.locator("#filters button")).to_have_count(18)
        expect(page.locator("#composer")).to_be_visible()
        if screenshot:
            page.screenshot(path=screenshot)
        page.locator("#search").fill("翻面")
        card = page.locator('[data-id="flip"]')
        poster = card.locator("canvas").evaluate("(c) => c.toDataURL()")
        card.get_by_role("button", name="播放：", exact=False).click()
        page.wait_for_function("image => document.querySelector('[data-id=flip] canvas').toDataURL() !== image", arg=poster)
        card.locator(".pick").click()
        expect(card.locator(".pick")).to_have_attribute("aria-pressed", "true")
        page.locator("#expand").click()
        prompt = page.locator("#full-input")
        new_text = prompt.input_value() + "\n请留出标题的位置。"
        prompt.fill(new_text)
        page.locator("#full-copy").click()
        expect(page.locator("#full-count")).to_have_text("已复制全文")
        assert page.evaluate("navigator.clipboard.readText()").splitlines() == new_text.splitlines()
        page.locator("#done-edit").click()
        page.locator("#jumpmix").click()
        page.locator("#scrub").fill("59")
        with page.expect_download() as png:
            page.locator("#snapshot").click()
        with Image.open(png.value.path()) as frame:
            assert frame.size == (960, 360) and frame.getchannel("A").getextrema() == (0, 255)
        samples = context.request.get(base_url + "/motion/sample-pack.zip")
        assert samples.ok
        with ZipFile(BytesIO(samples.body())) as bundle:
            assert bundle.testzip() is None
            assert len([name for name in bundle.namelist() if name.endswith(".mov")]) == 8

        page.locator("#nav-example").click()
        expect(page.locator("#manuscript")).to_be_editable()
        original = "书页从封面翻到书签。"
        page.locator("#manuscript").fill(original)
        page.get_by_role("button", name="素材包 0").click()
        expect(page.locator("#pack")).to_be_visible()
        expect(page.locator("#save-state")).to_have_text("草稿已存本机")
        page.goto(url)
        expect(cards).to_have_count(100)
        expect(page.locator("#prompt")).to_have_value(new_text)
        page.locator("#nav-example").click()
        expect(page.locator("#manuscript")).to_be_visible()
        expect(page.locator("#manuscript")).to_have_value(original)
        page.locator("#manual-lines summary").click()
        page.locator(".sentence").first.click()
        page.locator("#approve").click()
        expect(page.locator(".pack-item")).to_have_count(1)
        expect(page.locator("#save-state")).to_have_text("草稿已存本机")
        page.locator("#browse-gallery").click()
        expect(cards).to_have_count(100)
        page.locator("#nav-example").click()
        expect(page.locator(".pack-item")).to_have_count(1)

        scoped = "motion_" + "1" * 32
        page.goto(url + "?desk=" + scoped)
        expect(page.locator("#manuscript")).to_have_value("")
        page.locator("#browse-gallery").click()
        expect(cards).to_have_count(100)
        expect(page.locator("#nav-example")).to_have_attribute("href", "index.html?desk=" + scoped)
        assert "请留出标题的位置。" not in page.locator("#prompt").input_value()
        page.set_viewport_size({"width": 390, "height": 844})
        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
        page.locator("#expand").click()
        expect(page.locator("#full-input")).to_be_visible()
        assert not errors, errors
        browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True)
    parser.add_argument("--screenshot", type=Path)
    args = parser.parse_args()
    check(args.url, args.screenshot)
    print("Gallery playback, prompt, transparent PNG, sample ZIP, and draft isolation passed.")
