import copy, tempfile, unittest, sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from core import *

class ProjectTests(unittest.TestCase):
    def test_stable_sentence_ids_and_orphan_marker(self):
        p=page('先连接设备。然后打开电脑。');sid=p['sentences'][0]['id'];p['tags']=[{'sentence_id':sid}]
        p['text']='先连接设备。然后打开电脑。最后测试。';sync_sentences(p)
        self.assertEqual(p['sentences'][0]['id'],sid);self.assertFalse(p['tags'][0]['orphaned'])
        p['text']='最后测试。';sync_sentences(p);self.assertTrue(p['tags'][0]['orphaned'])

    def test_revision_conflict_and_atomic_restore_source(self):
        with tempfile.TemporaryDirectory() as root:
            s=Store(root);p=s.save(default_project());old=copy.deepcopy(p);p['title']='新版本';s.save(p)
            with self.assertRaises(Conflict):s.save(old,expected=0)
            self.assertEqual(s.load(p['id'])['title'],'新版本')
            self.assertTrue((s.folder(p['id'])/'revisions/000000.json').exists())

    def test_mapping_after_deletion_and_restore(self):
        p=default_project();p['pages']=[page('连接设备。')]
        p['edl']=[{'id':'a','start':0,'end':2,'keep':False},{'id':'b','start':2,'end':5,'keep':True}]
        p['transcript']=[{'id':'s','start':2,'end':3,'text':'连接设备。','words':[{'word':'连接','start':2,'end':2.4},{'word':'设备。','start':2.4,'end':3}]}]
        c=build_captions(p);self.assertEqual(c[0]['start'],0);self.assertEqual(c[0]['sentence_id'],p['pages'][0]['sentences'][0]['id'])
        p['edl'][0]['keep']=True;self.assertEqual(build_captions(p)[0]['start'],2)

    def test_deleted_sentence_does_not_attach_to_next(self):
        p=default_project();pg=page('连接设备。打开网页。');p['pages']=[pg]
        pg['tags']=[{'id':'t','kind':'product','sentence_id':pg['sentences'][0]['id'],'label':'设备'}]
        p['captions']=[{'page_id':pg['id'],'sentence_id':pg['sentences'][1]['id'],'start':0,'end':2}]
        sc=scene_plan(p)[0];self.assertTrue(sc['orphaned']);self.assertFalse(sc['enabled'])

    def test_edl_rejects_gaps_overlap_and_empty_output(self):
        for rows in [[{'start':0,'end':2,'keep':True},{'start':1,'end':4,'keep':True}], [{'start':0,'end':4,'keep':False}]]:
            with self.assertRaises(ValueError):validate_edl(rows,4)

    def test_approval_hash_changes_with_asset_and_caption(self):
        p=default_project();a=plan_hash(p);p['captions']=[{'text':'改字'}];self.assertNotEqual(a,plan_hash(p))
        p['scenes']=[{'id':'s','enabled':True,'asset_id':'a'}];a=plan_hash(p)
        p['assets']=[{'id':'a','path':'different.png'}];self.assertNotEqual(a,plan_hash(p))

    def test_unused_assets_and_prompter_settings_keep_render_approval(self):
        p=default_project();a=plan_hash(p);p['assets']=[{'id':'unused','path':'unused.png'}];p['settings']['font_size']=76
        self.assertEqual(a,plan_hash(p))

    def test_asset_file_change_invalidates_approval(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'asset.png';path.write_bytes(b'original')
            p=default_project();p['assets']=[{'id':'a','path':str(path)}];p['scenes']=[{'id':'s','enabled':True,'asset_id':'a'}]
            a=plan_hash(p);path.write_bytes(b'changed');self.assertNotEqual(a,plan_hash(p))

    def test_protection_rejects_overlay_overlap(self):
        p=default_project();p['rough']={'duration':10};p['settings']['overlay_y']=.4
        p['scenes']=[{'enabled':True,'start':0,'end':3,'kind':'title'}]
        with self.assertRaisesRegex(ValueError,'保护区'):validate_plan(p)

    def test_dont_invent_text_when_paging(self):
        text='我的设备使用数据线连接。这个步骤需要等待。'
        self.assertEqual(''.join(p['text'] for p in script_pages(text)),text)

    def test_caption_correction_survives_front_cut(self):
        p=default_project();p['pages']=[page('连接 Type-C 数据线。')]
        p['transcript']=[{'id':'s','start':2,'end':4,'text':'连接TypeC数据线。','words':[{'word':'连接','start':2,'end':2.5},{'word':'TypeC','start':2.5,'end':3},{'word':'数据线。','start':3,'end':4}]}]
        p['edl']=[{'id':'a','start':0,'end':5,'keep':True}];p['captions']=build_captions(p);cid=p['captions'][0]['id'];p['captions'][0]['text']='连接 Type-C 数据线。'
        p['edl']=[{'id':'a','start':0,'end':1,'keep':False},{'id':'b','start':1,'end':5,'keep':True}]
        result=build_captions(p);self.assertEqual(result[0]['id'],cid);self.assertEqual(result[0]['text'],'连接 Type-C 数据线。');self.assertEqual(result[0]['start'],1)

    def test_manual_scene_moves_with_source_anchor(self):
        p=default_project();p['edl']=[{'id':'a','start':0,'end':1,'keep':False},{'id':'b','start':1,'end':8,'keep':True}]
        p['scenes']=[{'id':'custom','title':'我的图','kind':'title','start':3,'end':5,'source_start':3,'source_end':5,'manual_timing':True,'enabled':True}]
        result=scene_plan(p);self.assertEqual(result[-1]['start'],2);self.assertEqual(result[-1]['end'],4)

    def test_overlap_is_not_silently_dropped(self):
        p=default_project();p['rough']={'duration':10};p['scenes']=[{'kind':'title','enabled':True,'start':0,'end':4},{'kind':'flow','enabled':True,'start':2,'end':5}]
        with self.assertRaisesRegex(ValueError,'重叠'):validate_plan(p)

if __name__=='__main__':unittest.main()
