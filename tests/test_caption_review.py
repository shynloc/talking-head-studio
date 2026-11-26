import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import caption_review
import core
import media
import timeline
from timeline_render import caption_map


class CaptionQuality(unittest.TestCase):
    def test_long_token_punctuation_and_soft_breaks(self):
        p=core.default_project()
        p['edl']=[dict(id='keep',start=0,end=20,keep=True)]
        parts=[('成果',1,2),('﹗',2,2.1),('以上',5.8,6.9),('是',6.98,14.26),('我的',14.26,14.6),('设备。',14.6,15)]
        p['transcript']=[dict(id='asr',start=1,end=15,text='',words=[
            dict(word=t,start=a,end=b,probability=.9) for t,a,b in parts])]
        caps=core.build_captions(p)
        self.assertEqual([c['text'] for c in caps],['成果！','以上是','我的设备。'])
        self.assertLess(caps[1]['end'],8)
        self.assertIn('listen_reason',caps[1])
        self.assertTrue(all(not c['start']<10<c['end'] for c in caps))
        caps[1]['text']='以上就是'
        p['captions']=caps
        self.assertIn('以上就是',[c['text'] for c in core.build_captions(p)])
        self.assertEqual(media.silence_ranges('silence_start: 9.00\nsilence_end: 13.04',20),[(9,13.04)])

    def test_prefixed_punctuation_is_attached_to_prior_sentence(self):
        p=core.default_project()
        p['edl']=[dict(id='k',start=0,end=5,keep=True)]
        p['transcript']=[dict(id='s',text='',words=[dict(word=w,start=i,end=i+.5)
                         for i,w in enumerate(('﹗第一句','！第二句','。'))])]
        caps=core.build_captions(p)
        self.assertEqual([c['text'] for c in caps],['第一句！','第二句。'])
        self.assertLess(caps[-1]['end'],2)

    def test_real_word_with_point_timestamp_survives_but_deleted_points_do_not(self):
        p=core.default_project()
        p['edl']=[dict(id='k',start=0,end=4,keep=True),dict(id='cut',start=4,end=6,keep=False)]
        p['transcript']=[dict(id='s',text='那失望。删',words=[
            dict(word='那',start=1,end=1),dict(word='失',start=1,end=2),dict(word='望。',start=2,end=2),
            dict(word='删',start=5,end=5)])]
        self.assertEqual(''.join(c['text'] for c in core.build_captions(p)),'那失望。')

    def test_break_prefers_clause_and_keeps_final_words_together(self):
        p=core.default_project()
        text='我们先把刚收到的设备连到电脑，然后再打开配套的软件检查声音是否正常。'
        p['edl']=[dict(id='k',start=0,end=15,keep=True)]
        p['transcript']=[dict(id='s',start=0,end=len(text)*.16,text=text)]
        caps=core.build_captions(p)
        self.assertEqual(''.join(c['text'] for c in caps),text)
        self.assertTrue(caps[0]['text'].endswith('，'))
        self.assertTrue(all(3<=len(c['text'])<=26 for c in caps))


class ReviewChanges(unittest.TestCase):
    def setUp(self):
        tmp=tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.store=core.Store(tmp.name)
        p=core.default_project()
        p['source_id']='src'
        p['edl']=[dict(id='a',start=0,end=5,keep=True),dict(id='b',start=5,end=10,keep=False),dict(id='c',start=10,end=15,keep=True)]
        p['rough']=dict(media_id='rough',edl_hash=core.edl_digest(p['edl']),mapping=core.time_map(p['edl']))
        p['approvals']['rough']={'actor':'user'}
        p['captions']=[dict(id=i,text='设备叫 X.',start=a,end=a+1,listen_reason='听听原话') for i,a in [('a',1),('b',5.5)]]
        timeline.calibrate(p)
        self.store.save(p);self.pid=p['id']
        self.key=caption_review.layout_key(p,caption_map(p,audition=True))

    def apply(self,op,edits,layout=None):
        return caption_review.apply(self.store,self.pid,dict(operation=op,edits=edits,layout=layout or self.key))

    def test_bulk_undo_and_conflict_are_atomic(self):
        edits=[dict(id=k,before='设备叫 X.',after='设备叫 Y.') for k in ('a','b')]
        with self.assertRaises(core.Conflict):
            self.apply('bulk',[edits[0],dict(edits[1],before='旧字幕')])
        self.assertEqual(self.store.load(self.pid)['captions'][0]['text'],'设备叫 X.')
        result=self.apply('bulk',edits)
        self.assertTrue(result['review']['can_undo'])
        self.assertEqual(result['review']['issues'],{})
        self.assertEqual(self.apply('undo',[])['texts'],{'a':'设备叫 X.','b':'设备叫 X.'})
        with self.assertRaises(core.Conflict):self.apply('save',edits,'other timeline')
        result=self.apply('keep',[dict(id='a',before='设备叫 X.',after='设备叫 X.')])
        self.assertEqual(list(result['review']['issues']),['b'])
        self.assertFalse(result['review']['pending'])
        self.assertFalse(result['project']['exports'])

    def test_insert_and_reorder_link_to_correct_cut_audio(self):
        p=self.store.load(self.pid)
        p['timeline']['clips']=[dict(track='main',source_id='src',source_in=10,start=2,duration=4),
                                dict(track='main',source_id='src',source_in=0,start=6,duration=5)]
        spans=caption_map(p,audition=True)
        self.assertEqual([s['id'] for s in spans],['b','a'])
        self.assertEqual(spans[0]['start'],2.5)
        self.assertAlmostEqual(spans[0]['listen_start'],5.08)
        self.assertAlmostEqual(spans[1]['listen_start'],.58)


if __name__=='__main__':unittest.main()
