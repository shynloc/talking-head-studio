import json
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from agent_tasks import AgentTasks
from core import Conflict, Store, default_project
from project_bundle import export_bundle, import_bundle


class LocalCodex:
    def __init__(self):
        self.sent = []
        self.delivery = 'queued'

    def available(self):
        return True

    def verify(self, thread):
        if thread not in ('source-chat', 'target-chat'):
            raise ValueError('未知对话')
        return {'thread_id': thread, 'cwd': 'test'}

    def queue(self, binding, card):
        self.sent.append((binding['thread_id'], card))
        return self.delivery


class AgentPortableTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.origin = Store(Path(temp.name) / 'source')
        self.target = Store(Path(temp.name) / 'target')
        self.source_host = LocalCodex()
        self.target_host = LocalCodex()
        self.a = AgentTasks(self.origin,self.source_host)
        self.b = AgentTasks(self.target,self.target_host)
        for service in (self.a,self.b):
            self.addCleanup(service.pool.shutdown)
        self.project = self.origin.save(default_project('工程'))

    def create(self, agent, instruction):
        return self.a.create({'project_id':self.project['id'], 'agent':agent, 'instruction':instruction,
                              'included':['pages'], 'request_id':instruction})

    def package(self, include_tasks):
        return Path(export_bundle(self.origin,self.origin.load(self.project['id']),lambda *_:None,
                                  include_tasks=include_tasks)['path'])

    def test_explicit_snapshot_restores_suggestions_and_reauthorizes_waiting_tasks(self):
        codex = self.create('codex','原对话续接')
        source_bind = self.a.bind_codex(self.project['id'],'source-chat')
        self.assertTrue(source_bind['connected'])
        workbuddy = self.create('workbuddy','继续校对')
        old_claim = self.a.claim({'id':workbuddy['id'],'agent':'workbuddy'})
        done = self.create('workbuddy','已返回的建议')
        self.a.complete_manually({'id':done['id'],'result':'之前的建议'})
        self.create('workbuddy','chatcut-ephemeral')
        with ZipFile(self.package(False)) as archive:
            self.assertNotIn('agent-tasks.json',archive.namelist())
        latest = self.origin.load(self.project['id'])
        latest['pages'][0]['text'] = '迁移前修改过的稿件'
        self.origin.save(latest)
        archive = self.package(True)
        with ZipFile(archive) as bundle:
            raw = bundle.read('agent-tasks.json').decode('utf8')
            self.assertNotIn('source-chat',raw)
            self.assertNotIn(old_claim['receipt'],raw)
            self.assertNotIn(workbuddy['id'],raw)
            self.assertNotIn('chatcut-ephemeral',raw)
        target_id = import_bundle(self.target,archive)['project_id']
        self.assertFalse(self.b.connection(target_id)['codex_bound'])
        restored = {task['instruction']:task for task in self.b.listing(target_id)}
        pending = restored['继续校对']
        self.assertTrue(pending['needs_handoff'])
        with self.assertRaises(Conflict): self.b.claim({'id':pending['id'],'agent':'workbuddy'})
        self.b.reactivate(pending['id'])
        new_claim = self.b.claim({'id':pending['id'],'agent':'workbuddy'})
        self.assertNotEqual(old_claim['receipt'],new_claim['receipt'])
        with self.assertRaises(Conflict):
            self.b.complete({'id':pending['id'],'agent':'workbuddy','receipt':old_claim['receipt'],'result':'迟到'})
        self.assertEqual(self.a.get(workbuddy['id'])['status'],'claimed')
        suggestion = self.b.get(restored['已返回的建议']['id'])
        self.assertEqual(suggestion['result'],'之前的建议')
        self.assertTrue(suggestion['project_changed'])

        target_codex = restored['原对话续接']
        with self.assertRaises(Conflict): self.b.resume(target_codex['id'],lambda _: 'card')
        with self.assertRaises(ValueError): self.b.bind_codex(target_id,'wrong-chat')
        self.b.reactivate(target_codex['id'])
        self.b.bind_codex(target_id,'target-chat')
        self.b.resume(target_codex['id'],lambda task: task['id'])
        self.b.pool.shutdown()
        self.b.resume(target_codex['id'],lambda task: task['id'])
        self.assertEqual(self.target_host.sent,[('target-chat',target_codex['id'])])
        self.assertEqual(self.b.get(target_codex['id'])['delivery'],'queued')
        self.assertNotEqual(target_codex['id'],codex['id'])

    def test_invalid_task_snapshot_rolls_back_project_and_tasks(self):
        self.create('workbuddy','测试任务')
        original = self.package(True)
        corrupted = self.origin.root / 'invalid-agent.zip'
        with ZipFile(original) as old, ZipFile(corrupted,'w') as new:
            for name in old.namelist():
                if name == 'agent-tasks.json':
                    snapshot = json.loads(old.read(name))
                    snapshot['tasks'].append({'agent':'unknown'})
                    new.writestr(name,json.dumps(snapshot))
                else:
                    new.writestr(name,old.read(name))
        with self.assertRaisesRegex(ValueError,'无法识别的助手'):
            import_bundle(self.target,corrupted)
        self.assertEqual(self.target.listing(),[])
        self.assertEqual(self.b.listing(),[])
