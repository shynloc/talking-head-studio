import concurrent.futures
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from agent_tasks import AgentTasks
from core import Conflict, Store
from motion_recommend import catalog, snapshot, recommendations
from test_agent_tasks import FakeCodex


class MotionRecommendationTests(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tasks = AgentTasks(Store(tmp.name), FakeCodex())
        self.addCleanup(self.tasks.pool.shutdown)
        lines = ["今天来看纸张。", "样张从12张增加到24张。", "谢谢。"]
        self.request = dict(
            workspace="motion_" + "c" * 32,
            request_id="first",
            agent="codex",
            text="\n".join(lines),
            sentences=lines,
        )
        self.row = dict(
            sentence=1,
            reason="两端对照张数的变化。",
            title="样张增加",
            ids=["fade", "dotPair"],
            a="之前",
            b="之后",
            values=[12, 24],
            seconds=2,
        )

    def test_contract_and_recovery(self):
        task = self.tasks.create_motion(self.request, None)
        self.assertEqual(task, self.tasks.create_motion(self.request, None))
        self.assertEqual(self.tasks.listing(), [])
        self.assertEqual(self.tasks.listing(agent="codex")[0]["id"], task["id"])
        self.assertEqual(self.tasks.resume(task["id"], lambda _: "card")["delivery"], "manual")
        claim = self.tasks.claim(dict(id=task["id"], agent="codex"))
        self.assertEqual(claim["context"]["manuscript"], self.request["text"])
        payload = dict(id=task["id"], receipt=claim["receipt"], agent="codex")
        for invalid in [
            dict(sentence=99),
            dict(ids=["unknown"]),
            dict(quote="改写了原文。"),
            dict(ids=["slopePair", "dotPair"]),
            dict(values=[-1, 20]),
            dict(b=""),
        ]:
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                self.tasks.complete(
                    dict(payload, result=json.dumps({"recommendations": [self.row | invalid]}))
                )
        self.assertEqual(self.tasks.get(task["id"])["status"], "claimed")
        result = json.dumps({"recommendations": [self.row]}, ensure_ascii=False)
        ready = self.tasks.complete(dict(payload, result=result))
        self.assertEqual(ready["recommendations"][0]["quote"], self.request["sentences"][1])
        self.assertEqual(self.tasks.complete(dict(payload, result=result)), ready)
        with self.assertRaises(Conflict):
            self.tasks.create_motion(self.request | {"sentences": ["新稿。"], "text": "新稿。"}, None)

    def test_catalog_and_whole_source(self):
        data = catalog()
        self.assertEqual(len({entry["id"] for entry in data["terms"]}), 108)
        self.assertEqual(len(data["groups"]), 17)
        self.assertTrue(all(t["ref"] in data["refs"] for t in data["terms"]))
        with self.assertRaises(ValueError):
            snapshot(self.request["text"], self.request["sentences"][1:])
        with self.assertRaises(ValueError):
            snapshot(self.request["text"], self.request["sentences"][:2])
        ctx = snapshot("甲。 甲。", ["甲。", "甲。"])
        self.assertEqual(recommendations(ctx, {"recommendations": []}), [])
        with self.assertRaises(ValueError):
            recommendations(ctx, {"recommendations": [self.row] * 2})

    def test_workbuddy_reply_and_failed_model(self):
        task = self.tasks.create_motion(self.request | {"agent": "workbuddy"}, None)
        with self.assertRaises(Conflict):
            self.tasks.claim(dict(id=task["id"], agent="codex"))
        ready = self.tasks.complete_manually(dict(id=task["id"], result='{"recommendations":[]}'))
        self.assertEqual((ready["recommendations"], ready["manual_result"]), ([], True))
        service = Mock()
        service.config.return_value = {"ready": False}
        request = self.request | {"agent": "service", "request_id": "other"}
        with self.assertRaises(ValueError):
            self.tasks.create_motion(request, service)
        service.config.return_value = {"ready": True}
        for n, reply in enumerate([json.dumps({"recommendations": [self.row]}), "invalid model response"]):
            with concurrent.futures.ThreadPoolExecutor() as pool:
                service.pool = pool
                service.model_reply.return_value = reply
                task = self.tasks.create_motion(request | {"request_id": str(n)}, service)
            self.assertEqual(self.tasks.get(task["id"])["status"], ["ready", "failed"][n])

    def test_scoped_desk_and_compact_dispatch(self):
        workspace = self.tasks.motion_desk("thread-one")
        self.assertEqual(self.tasks.motion_desk("thread-one"), workspace)
        self.assertNotEqual(self.tasks.motion_desk("thread-two"), workspace)
        task = self.tasks.create_motion(self.request | {"workspace": workspace}, None)

        def card(public):
            self.assertNotIn("context", public)
            return public["id"]

        self.tasks.resume(task["id"], card)
        self.tasks.pool.shutdown()
        self.assertEqual(self.tasks.codex.sent[0][0]["thread_id"], "thread-one")
