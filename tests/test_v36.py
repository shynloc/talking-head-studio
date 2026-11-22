import copy
import sys
import unittest
import tempfile
from types import SimpleNamespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))

import timeline
import timeline_render
import v2_api
from ai_service import Manuscripts
from core import Store, default_project, time_map, aligned_with_cuts, digest, edl_digest, matches_edl, rough_current


class RoughApprovalTests(unittest.TestCase):
    def test_old_browser_roundtrip_preserves_both_approvals(self):
        original = [dict(id='first', start=0.0, end=1.25, keep=True),
                    dict(id='pause', start=1.25, end=3.0, keep=False)]
        restored = [dict(original[0], start=0), dict(original[1], end=3)]
        project = {'edl': restored, 'rough': {'edl_hash': digest(original)}, 'source_id': 'source',
                   'timeline': {'alignment': {'edl_hash': digest(original), 'source_id': 'source'}}}
        self.assertEqual(edl_digest(original), edl_digest(restored))
        self.assertTrue(rough_current(project))
        self.assertTrue(aligned_with_cuts(project))
        for prop,value in [('keep',True),('end',3.01)]:
            edited = copy.deepcopy(project)
            edited['edl'][1][prop] = value
            self.assertFalse(rough_current(edited))
            self.assertFalse(aligned_with_cuts(edited))
        project['source_id'] = 'replacement'
        self.assertFalse(aligned_with_cuts(project))

    def test_already_cut_legacy_hash(self):
        row = dict(id='whole',start=0,end=4.0,keep=True)
        self.assertTrue(matches_edl(digest([row]), [dict(row,end=4)]))


class ProjectRecoveryTests(unittest.TestCase):
    def test_existing_draft_can_recover_its_created_project(self):
        with tempfile.TemporaryDirectory() as root:
            store=Store(root)
            drafts=Manuscripts(store)
            server=SimpleNamespace(store=store,manuscripts=drafts)
            draft=drafts.save({'title':'原稿','text':'先读这句话。'})
            created=v2_api.post(server,'/api/v2/create',{'id':draft['id']})
            repeated=v2_api.post(server,'/api/v2/create',{'id':draft['id']})
            self.assertEqual((repeated['id'],drafts.get(draft['id'])['project_id']),(created['id'],created['id']))

    def test_unmatched_annotation_can_be_omitted_or_repositioned(self):
        p=default_project()
        p['source_id']='video'
        p['media']=[dict(id='video',video=True,path=__file__,duration=3)]
        p['edl']=[dict(id='cut',start=0,end=3,keep=True)]
        p['rough']=dict(media_id='video',path=__file__,edl_hash=edl_digest(p['edl']),mapping=time_map(p['edl']))
        p['approvals']['rough']={'kind':'already_cut'}
        pg=p['pages'][0]
        pg['tags']=[dict(id='mark',label='重点',kind='title',sentence_id='removed')]
        timeline.calibrate(p)
        self.assertEqual(timeline_render.review_state(p)['state'],'placement')
        clip=next(c for c in p['timeline']['clips'] if c.get('tag_id')=='mark')
        clip['enabled']=False
        self.assertEqual(timeline_render.review_state(p)['state'],'ready')
        clip.update(enabled=True,anchor='absolute',start=.4)
        self.assertEqual(timeline_render.review_state(p)['state'],'ready')
        self.assertAlmostEqual(clip['start'],.4)


class ComponentAndHostTests(unittest.TestCase):
    def test_origin_and_scoped_card(self):
        from agent_hosts import destination
        from agent_tasks import AgentTasks
        from agent_api import task_card
        with tempfile.TemporaryDirectory() as tmp:
            store=Store(tmp)
            project=store.save(default_project('例子'))
            tasks=AgentTasks(store,None)
            data=dict(project_id=project['id'],agent='chatgpt',instruction='看看这句',request_id='1',included=['captions'])
            item=tasks.create(data)
            card=tasks.manual_card(item['id'])
            self.assertEqual(set(card['context']),{'title','captions'})
            self.assertNotIn('studio.py',task_card(card,'http://127.0.0.1:8765'))
            self.assertEqual(destination('https://chatgpt.com/c/abcd?x=1','chatgpt'),'https://chatgpt.com/c/abcd')
            with self.assertRaises(ValueError):destination('https://claude.ai/chat/abcd','chatgpt')
            with self.assertRaises(ValueError):destination('https://chatgpt.com/share/abcd','chatgpt')

    def test_material_properties_round_trip(self):
        import materials
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            path=Path(tmp)/'贴纸.png'
            Image.new('RGBA',(18,24),'#faa2').save(path)
            store=Store(tmp)
            pid=store.save(default_project())['id']
            item=materials.add(store,pid,path,'贴纸','测试')
            self.assertEqual((item['width'],item['height'],item['alpha_capable']),(18,24,True))
            self.assertEqual(store.load(pid)['assets'][0]['id'],item['id'])
            self.assertTrue(materials.components()['gif-factory']['available'])
