import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import motion_samples as samples
import motion_treatments as effects
from motion_recommend import recommendations, snapshot


class SentenceEffectTests(unittest.TestCase):
    def test_catalog_and_anchors_cover_every_variant(self):
        data = samples.catalog()
        self.assertEqual(
            [len(data[k]) for k in ("objects", "stickers", "styles", "palettes")],
            [16, 24, 9, 11],
        )
        colors = {p["id"] for p in data["palettes"]}
        for entry in data["objects"] + data["stickers"]:
            self.assertEqual(set(entry["variants"]), colors)
            for variant in entry["variants"].values():
                self.assertTrue(
                    all((samples.LIBRARY / path).is_file() for path in variant.values())
                )
        for effect in effects.catalog().values():
            obj = next(o for o in data["objects"] if o["id"] == effect["object"])
            anchor = obj["tokens"]["anchors"][effect["part"]]
            self.assertTrue(all(0 <= v <= 1 for v in anchor))

    def test_agent_picks_are_ordered_and_bound_to_object(self):
        ctx = snapshot("按电子秤的归零键。", ["按电子秤的归零键。"])
        row = dict(
            sentence=0,
            route="library",
            visual={"objects": "scale"},
            treatment="scale-tare",
            title="归零",
            brief="按键位置",
            reason="找到归零按钮",
            alternatives=["scale-tare", "scale-read"],
        )
        self.assertEqual(
            recommendations(ctx, {"recommendations": [row]})[0]["alternatives"],
            row["alternatives"],
        )
        for overrides in (
            {"treatment": "pack-lift"},
            {"alternatives": ["absent"]},
            {"route": "html"},
        ):
            with self.assertRaises(ValueError):
                recommendations(ctx, {"recommendations": [row | overrides]})

    def test_numbers_and_marks_come_from_the_sentence(self):
        context = dict(
            treatment="scale-read", visual={"objects": "scale", "palettes": "violet"}
        )
        d, _ = effects.scene_data(context | {"quote": "电子秤归零后倒入 80 克面粉。"})
        self.assertEqual(d["value"], "80 克")
        self.assertEqual(d["colors"]["accent"], "#673DA3")
        empty, _ = effects.scene_data(context | {"quote": "电子秤先归零再读数。"})
        self.assertNotRegex(empty["value"], r"\d")
        for ordinal, y in [("一", 237), ("二", 212), ("五", 137)]:
            d, _ = effects.scene_data(
                dict(
                    treatment="cup-pour",
                    visual={"objects": "jug"},
                    quote=f"加到第{ordinal}条刻度。",
                )
            )
            self.assertEqual(d["fillY"], y)
            self.assertEqual(d["callout"], f"第{ordinal}条刻度")
