import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import core
import cue_review
import preview_edits
import timeline
import timeline_render


class PreviewNotes(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store=core.Store(self.tmp.name)
        p=core.default_project()
        pg=core.page('开场。接下来介绍开发板。')
        p['pages']=[pg]
        p['source_id']='src'
        p['edl']=[{'id':'cut','start':1.,'end':5.,'keep':True}]
        p['rough']={'mapping':core.time_map(p['edl'])}
        sid=pg['sentences'][1]['id']
        p['captions']=[dict(id='cap',start=1.,end=2.,text='介绍开发板',page_id=pg['id'],sentence_id=sid,match_score=.92)]
        pg['tags']=[dict(id='board',kind='product',label='放开发板',sentence_id=sid,review='pending')]
        p['timeline']={'mode':'actual','tracks':{},'clips':[dict(id='insert',track='main',start=0,duration=3),
            dict(id='rec',track='main',source_id='src',page_id=pg['id'],source_in=1.,start=3,duration=4)]}
        timeline.sync(p)
        self.p=self.store.save(p)
        self.pid=p['id']
        self.choice=dict(tag_id='board',caption_id='cap',mode='title',name='开发板',asset_id='')

    def test_try_accept_skip_and_stale_suggestion(self):
        p=self.store.load(self.pid)
        self.assertFalse(p['timeline']['clips'][-1]['enabled'])
        key=cue_review.note_key(p,'board')
        self.assertEqual(cue_review.prepare(p,self.choice),(4.,1.))
        self.assertFalse(self.store.load(self.pid)['timeline']['clips'][-1]['enabled'])
        cue_review.decide(self.store,self.pid,dict(self.choice,baseline=key))
        p=self.store.load(self.pid)
        self.assertEqual(p['timeline']['clips'][-1]['start'],4.)
        self.assertTrue(p['timeline']['clips'][-1]['enabled'])
        with self.assertRaises(core.Conflict):
            cue_review.decide(self.store,self.pid,dict(self.choice,baseline=key))
        cue_review.decide(self.store,self.pid,dict(tag_id='board',skip=True))
        self.assertFalse(self.store.load(self.pid)['timeline']['clips'][-1]['enabled'])

    def test_uncertain_or_removed_sentence_requires_creator_choice(self):
        p=self.p
        for key,val in [('match_score',.45),('ambiguous_match',True)]:
            cap=p['captions'][0].copy()
            p['captions'][0][key]=val
            self.assertEqual(cue_review.summaries(p)[0]['caption_id'],'')
            p['captions'][0]=cap
        p['pages'].append(core.page(p['pages'][0]['text']))
        self.assertTrue(core.match_script(p,'接下来介绍开发板。')['ambiguous_match'])
        p['captions']=[]
        with self.assertRaises(ValueError):
            cue_review.prepare(p,self.choice)

    def test_imported_cues_keep_each_line_and_its_end(self):
        p=self.p
        p['transcript']=[dict(id=str(i),start=1+i,end=1.9+i,text=line,subtitle_cue=True)
                         for i,line in enumerate(('ESP32','继续介绍'))]
        result=core.build_captions(p)
        self.assertEqual([(c['text'],c['start'],c['end']) for c in result],
                         [('ESP32',0.,.9),('继续介绍',1.,1.9)])

    def test_partial_preview_uses_rendered_clock(self):
        spans=timeline_render.caption_map(self.p)
        state=dict(sample=dict(start=3.8,duration=2),caption_spans=spans,duration=7)
        req=dict(operation='caption',caption_id='cap',time=4.5,text='开发板改字')
        with patch('timeline_render.require_sample',return_value=state):
            with self.assertRaises(ValueError):
                preview_edits.edit(self.store,self.pid,dict(req,time=.7))
            preview_edits.edit(self.store,self.pid,req)
            self.assertEqual(self.store.load(self.pid)['captions'][0]['text'],req['text'])
            with self.assertRaises(ValueError):
                preview_edits.edit(self.store,self.pid,dict(req,time=3.9))
            preview_edits.edit(self.store,self.pid,dict(req,operation='visual',name='板子'))
        added=next(c for c in self.store.load(self.pid)['timeline']['clips'] if c.get('name')=='板子')
        self.assertEqual((added['start'],added['duration']),(4.,1.))

    def test_subtitles_only_preserves_planned_layers(self):
        p=self.p
        cue_review.prepare(p,self.choice)
        clip=p['timeline']['clips'][-1]
        self.assertTrue(clip['enabled'])
        p['settings']['caption_only']=True
        self.assertEqual(timeline_render.layers(p,p['timeline'],0,7),([],[]))
        p['settings']['caption_only']=False
        self.assertEqual(timeline_render.layers(p,p['timeline'],0,7)[0][0]['name'],'开发板')
