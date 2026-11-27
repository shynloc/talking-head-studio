import concurrent.futures
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

from agent_tasks import AgentTasks
from core import Conflict, Store, default_project


class FakeCodex:
    def __init__(self):
        self.sent = []
        self.outcome = 'queued'

    def available(self):
        return True

    def verify(self, thread_id):
        return {'thread_id': thread_id, 'cwd': 'fixture'}

    def queue(self, binding, card):
        self.sent.append((binding, card))
        return self.outcome


class AgentTaskTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.store = Store(temp.name)
        project = default_project()
        project['pages'][0]['text'] = '初稿'
        self.project = self.store.save(project)
        self.adapter = FakeCodex()
        self.tasks = AgentTasks(self.store, self.adapter)
        self.addCleanup(self.tasks.pool.shutdown)

    def create(self, agent='codex'):
        return self.tasks.create({'project_id': self.project['id'], 'agent': agent,
                                  'instruction': '把稿件写得更顺', 'request_id': 'form-1'})

    def test_duplicate_submission_and_concurrent_claim(self):
        created = self.create()
        self.assertEqual(self.create()['id'], created['id'])
        def claim():
            try:
                return self.tasks.claim({'id': created['id'], 'agent': 'codex'})
            except Conflict:
                return None
        with concurrent.futures.ThreadPoolExecutor(2) as pool:
            claims = [item for item in pool.map(lambda _: claim(), range(2)) if item]
        self.assertEqual(len(claims), 1)
        self.assertEqual(claims[0]['context']['pages'][0]['text'], '初稿')
        self.assertNotIn('receipt', self.tasks.get(created['id']))
        self.assertNotIn('context', self.tasks.listing()[0])

    def test_workbuddy_manual_delivery_and_stale_suggestions(self):
        task = self.create('workbuddy')
        self.assertEqual(self.tasks.resume(task['id'], lambda _: 'card')['delivery'], 'manual')
        self.assertFalse(self.adapter.sent)
        with self.assertRaises(Conflict):
            self.tasks.claim({'id': task['id'], 'agent': 'codex'})
        claim = self.tasks.claim({'id': task['id'], 'agent': 'workbuddy'})
        self.project['pages'][0]['text'] = '用户修改稿'
        self.store.save(self.project)
        payload = {'id': task['id'], 'agent': 'workbuddy', 'receipt': claim['receipt'], 'result': '处理建议'}
        ready = self.tasks.complete(payload)
        self.assertTrue(ready['project_changed'])
        self.assertEqual(self.tasks.complete(payload), ready)
        self.assertEqual(self.store.load(self.project['id'])['pages'][0]['text'], '用户修改稿')

    def test_reset_revokes_receipt_and_manual_result_is_saved(self):
        task = self.create()
        claim = self.tasks.claim({'id': task['id'], 'agent': 'codex'})
        self.tasks.reset_claim(task['id'])
        with self.assertRaises(Conflict):
            self.tasks.complete({'id': task['id'], 'agent': 'codex', 'receipt': claim['receipt'], 'result': '旧结果'})
        self.assertEqual(self.tasks.complete_manually({'id': task['id'], 'result': '手动回写'})['status'], 'ready')

    def test_linked_codex_sends_to_exact_thread_once(self):
        task = self.create()
        self.assertEqual(self.tasks.resume(task['id'], lambda _: 'before-bind')['delivery'], 'manual')
        self.tasks.bind_codex(self.project['id'], 'original')
        with self.assertRaises(Conflict):
            self.tasks.bind_codex(self.project['id'], 'another')
        self.tasks.resume(task['id'], lambda _: 'card')
        self.tasks.pool.shutdown()
        self.assertEqual(self.tasks.get(task['id'])['delivery'], 'queued')
        self.assertEqual(self.tasks.get(task['id'])['status'], 'waiting')
        self.tasks.resume(task['id'], lambda _: 'duplicate')
        self.assertEqual(self.adapter.sent, [({'thread_id': 'original', 'cwd': 'fixture'}, 'card')])

    def test_failed_resume_keeps_work_for_manual_claim(self):
        task = self.create()
        self.adapter.outcome = 'manual'
        self.tasks.bind_codex(self.project['id'], 'original')
        self.tasks.resume(task['id'], lambda _: 'card')
        self.tasks.pool.shutdown()
        self.assertEqual(self.tasks.get(task['id'])['delivery'], 'fallback')
        self.assertEqual(self.tasks.claim({'id': task['id'], 'agent': 'codex'})['status'], 'claimed')

    def test_uncertain_delivery_keeps_card_without_sending_again(self):
        task = self.create()
        self.adapter.outcome = 'unconfirmed'
        self.tasks.bind_codex(self.project['id'], 'original')
        self.tasks.resume(task['id'], lambda _: 'card')
        self.tasks.pool.shutdown()
        self.assertEqual(self.tasks.resume(task['id'], lambda _: 'duplicate')['delivery'], 'unconfirmed')
        self.assertEqual(len(self.adapter.sent), 1)
        self.assertEqual(self.tasks.manual_card(task['id'])['context']['pages'][0]['text'], '初稿')
