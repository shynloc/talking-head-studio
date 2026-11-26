import io
import json
import struct
import sys
import tempfile
import unittest
import zipfile
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import motion_package
import motion_samples
from agent_tasks import AgentTasks
from core import Conflict, Store
from motion_recommend import recommendations, snapshot
from test_agent_tasks import FakeCodex


class SampleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)

    def png(self, opaque=False, extra=None):
        image = Image.new("RGBA", (24, 16), "white" if opaque else (0, 0, 0, 0))
        image.putpixel((5, 6), (12, 42, 55, 150))
        pixels = io.BytesIO()
        image.save(pixels, "PNG")
        raw = io.BytesIO()
        with zipfile.ZipFile(raw, "w") as z:
            z.writestr("media.png", pixels.getvalue())
            if extra:
                z.writestr(extra, "{}")
        raw.seek(0)
        return raw

    def test_valid_alpha_and_content_identity(self):
        first = motion_samples.receive(self.root, self.png())
        self.assertEqual(first, motion_samples.receive(self.root, self.png()))
        second = motion_samples.receive(
            self.root, self.png(extra="sources/recipe.json")
        )
        self.assertNotEqual(first["id"], second["id"])
        for file in (self.png(True), self.png(extra="sources/../recipe.json")):
            with self.assertRaises(ValueError):
                motion_samples.receive(self.root, file)

    def test_portable_pack_rehydrates_original(self):
        version = motion_samples.from_library(
            self.root, {"objects": "camera", "stickers": "tape", "palettes": "ink"}
        )
        item = {"title": "相机", "quote": "把相机放稳。", "sample": version}
        header = json.dumps(
            {"format": "talking-head-motion/2", "items": [item]}
        ).encode()
        packet = struct.pack(">I", len(header)) + header
        result = motion_package.export(self.root, io.BytesIO(packet), len(packet))
        path = motion_package.download(self.root, result["url"].split("/")[-1])
        fresh = self.root / "new"
        restored = motion_package.restore(fresh, path)["items"][0]
        self.assertEqual(version, restored["sample"])
        self.assertTrue(any(k.endswith(".glb") for k in restored["packageSources"]))
        self.assertTrue(any(k.endswith(".svg") for k in restored["packageSources"]))

    def test_routing_uses_source_anchor_and_explicit_palette(self):
        ctx = snapshot("将灯移近。", ["将灯移近。"], {"palettes": "herb"})
        row = {
            "route": "html",
            "sentence": 0,
            "brief": "画灯的位置变化",
            "reason": "展示位移",
            "title": "移灯",
            "visual": {"palettes": "ink"},
        }
        result = recommendations(ctx, {"recommendations": [row]})
        self.assertEqual(result[0]["visual"]["palettes"], "herb")
        self.assertEqual(result[0]["quote"], ctx["sentences"][0])

    def test_receipt_route_and_one_version_per_job(self):
        tasks = AgentTasks(Store(self.temp.name), FakeCodex())
        self.addCleanup(tasks.pool.shutdown)
        data = dict(
            text="举起夹子。",
            sentences=["举起夹子。"],
            sentence=0,
            agent="codex",
            route="imagegen",
            title="夹子",
            brief="透明夹子",
            request_id="a",
            workspace="motion_" + "a" * 32,
        )
        job = tasks.production(data)
        self.assertEqual(job, tasks.production(data))
        claim = tasks.claim({"agent": "codex", "id": job["id"]})
        with self.assertRaises(Conflict):
            tasks.check_delivery(job["id"], "codex", "wrong")
        args = (job["id"], "codex", claim["receipt"])
        with self.assertRaises(ValueError):
            tasks.finish_delivery(*args, {"kind": "animation", "id": "1"})
        sample = motion_samples.receive(self.root, self.png())
        self.assertEqual(tasks.finish_delivery(*args, sample)["sample"], sample)
        self.assertEqual(tasks.finish_delivery(*args, sample)["sample"], sample)
        with self.assertRaises(Conflict):
            tasks.finish_delivery(
                *args,
                motion_samples.receive(self.root, self.png(extra="sources/new.json")),
            )
