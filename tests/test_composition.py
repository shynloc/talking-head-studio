import unittest
from tempfile import TemporaryDirectory
from pathlib import Path
import sys

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from core import Store, default_project
import timeline, timeline_render, visionbuddy_timeline

class CompositionTest(unittest.TestCase):
    def test_project_default_and_explicit_segment(self):
        with TemporaryDirectory() as tmp:
            store = Store(tmp)
            p = store.save(default_project())
            pid = p['id']
            original = timeline_render.signature(store.load(pid))
            p = store.edit(pid, {'version':p['version'],'settings':{**p['settings'],'composition':'demo'}})
            self.assertNotEqual(timeline_render.signature(p),original)
            p = store.load(pid)
            clip = {'track':'pip'}
            self.assertTrue(timeline.demo_first(p,clip))
            self.assertFalse(timeline.demo_first(p,{**clip,'composition':'presenter'}))
            self.assertFalse(timeline.demo_first(p,{'track':'title','kind':'title'}))
            self.assertFalse(timeline.demo_first(p,{'track':'sfx','composition':'demo'}))
            with self.assertRaises(ValueError):
                store.edit(pid,{'version':p['version'],'settings':{**p['settings'],'composition':'bad'}})
            self.assertEqual(store.load(pid)['settings']['composition'],'demo')

    def test_mixed_context_and_pins(self):
        p = default_project()
        p['settings'].update(composition='mixed',page_compositions={'outro':'presenter'})
        operation = {'track':'pip','kind':'demo'}
        self.assertTrue(timeline.demo_first(p,operation))
        self.assertFalse(timeline.demo_first(p,{**operation,'page_id':'outro','suggested_composition':'demo'}))
        self.assertTrue(timeline.demo_first(p,{**operation,'page_id':'outro','composition':'demo'}))
        self.assertFalse(timeline.demo_first(p,{**operation,'suggested_composition':'presenter'}))
        self.assertFalse(timeline.demo_first(p,{'track':'sticker','kind':'product'}))
        self.assertFalse(timeline.demo_first(p,{'track':'caption','composition':'demo'}))
        p['timeline'] = {'clips':[{'track':'main','page_id':'outro','start':2,'duration':2}]}
        self.assertFalse(timeline.demo_first(p,{**operation,'start':2.1}))
        p['settings']['composition']='presenter'
        self.assertTrue(timeline.demo_first(p,{**operation,'composition':'demo'}))

    def test_inherit_import_direction_for_legacy_project(self):
        p = default_project()
        clip = {'track':'sticker','visionbuddyRow':'r','bundle_composition':'demo'}
        self.assertTrue(timeline.demo_first(p,clip))
        self.assertFalse(timeline.demo_first(p,{'track':'pip'}))
        p['settings']['composition']='presenter'
        self.assertFalse(timeline.demo_first(p,clip))
