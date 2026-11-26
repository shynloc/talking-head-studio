"""Browser integration for manuscript intake, pending replies and every new transparent effect."""

import argparse
import json
import sys
from pathlib import Path

from playwright.sync_api import expect, sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from agent_client import AgentClient


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", required=True, help="An isolated local workbench")
    parser.add_argument("--channel", default="msedge")
    args = parser.parse_args()
    text = "大家好。先打开相册，再选择照片，最后导出副本。展架设在出口旁边。谢谢。"
    client = AgentClient(args.url, "workbuddy")
    with sync_playwright() as pw:
        browser = pw.chromium.launch(channel=args.channel)
        ctx = browser.new_context(
            permissions=["clipboard-read", "clipboard-write"], viewport={"width": 390, "height": 844}
        )
        page = ctx.new_page()
        errors = []
        page.on("pageerror", lambda error: errors.append(str(error)))
        page.goto(args.url + "/motion/index.html?view=desk")
        expect(page.locator("#manuscript")).to_be_editable()
        page.locator("#agent-mode").select_option("workbuddy")

        def paste(value):
            page.evaluate("(s)=>navigator.clipboard.writeText(s)", value)
            page.locator("#manuscript").focus()
            page.keyboard.press("ControlOrMeta+A")
            page.keyboard.press("ControlOrMeta+V")
            page.wait_for_function("state.review?.taskId")
            return page.evaluate("state.review.taskId")

        first = paste(text)
        expect(page.locator(".review-card")).to_have_count(1)
        page.locator(".review-card .skip").click()
        claim = client.claim(first)
        assert claim["context"]["sentences"] == [
            "大家好。",
            "先打开相册，再选择照片，最后导出副本。",
            "展架设在出口旁边。",
            "谢谢。",
        ]
        client.complete(
            first,
            claim["receipt"],
            json.dumps(
                {
                    "recommendations": [
                        dict(
                            sentence=2,
                            reason="用标记强调展架所在位置。",
                            title="出口旁的展架",
                            ids=["pinDrop"],
                            seconds=1,
                        ),
                        dict(
                            sentence=1,
                            reason="逐项显示这三个操作。",
                            title="导出照片",
                            labels=["打开相册", "选择照片", "导出副本"],
                            ids=["checkList"],
                        ),
                    ]
                }
            ),
        )
        page.wait_for_function("state.review.status==='ready'")
        expect(page.locator(".review-card")).to_have_count(1)
        page.locator("#undo-skip").click()
        page.locator('[data-sentence="2"] .accept').click()
        expect(page.locator("#export-choices")).to_contain_text("1 款")
        old = paste("需要另外分析的一稿。")
        claim = client.claim(old)
        current = paste("明天一起去公园。")
        assert old != current
        client.complete(old, claim["receipt"], json.dumps({"recommendations": []}))
        assert page.evaluate("state.review.taskId") == current
        expect(page.locator("#export-choices")).to_be_disabled()
        claim = client.claim(current)
        client.complete(current, claim["receipt"], json.dumps({"recommendations": []}))
        page.wait_for_function("state.review.status==='ready'")
        expect(page.locator(".review-card")).to_have_count(0)
        assert page.evaluate("document.documentElement.scrollWidth<=innerWidth")
        checks = page.evaluate("""()=>{
          const canvas=document.createElement('canvas');canvas.width=480;canvas.height=180
          return DATA.terms.filter(t=>t.foreground).map(t=>{
            const frames=[.15,.85].map(at=>{draw(canvas,at,[t.id],'coffee',true)
              const d=canvas.getContext('2d').getImageData(0,0,480,180).data
              return {image:canvas.toDataURL(), corner:d[3], painted:d.some((v,i)=>i%4===3&&v>150)}
            })
            return {id:t.id,ok:frames.every(f=>!f.corner&&f.painted)&&frames[0].image!==frames[1].image}
          })
        }""")
        assert len(checks) == 26 and all(c["ok"] for c in checks), [c for c in checks if not c["ok"]]
        assert not errors, errors
        browser.close()
    print(
        "Whole-script paste, WorkBuddy protocol, delayed replies, skip/restore, scoped choices, mobile and 26 animated alpha previews passed."
    )


if __name__ == "__main__":
    main()
