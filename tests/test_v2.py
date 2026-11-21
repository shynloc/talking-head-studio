import sys, tempfile, unittest, copy
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from core import *
from ai_service import Manuscripts, balanced_pages
import timeline

class V2Tests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name);self.p=default_project();self.p['pages']=[page('先连接设备。然后开始录制。',title='连接'),page('最后检查声音和画面。',title='检查')];self.store.save(self.p)
 def tearDown(self):self.tmp.cleanup()
 def test_paging_preserves_long_sentences_and_order(self):
  text='一个完整的长句'+('这里是内容，'*35)+'结束。下一句。';pages=balanced_pages(text);self.assertEqual(''.join(p['text'] for p in pages),text);self.assertIn(text.split('。')[0]+'。',[p['text'] for p in pages])
 def test_insert_ripples_main_and_tag(self):
  pg=self.p['pages'][1];pg['tags']=[{'id':'t','kind':'title','label':'重点','sentence_id':'','asset_id':''}];a=copy.deepcopy(timeline.sync(self.p));self.p['timeline']['clips'].append({'id':'x','track':'main','name':'演示','before_page_id':pg['id'],'start':0,'duration':10});b=timeline.sync(self.p);self.assertAlmostEqual(next(c['start'] for c in b['clips'] if c['id']=='tag_t'),next(c['start'] for c in a['clips'] if c['id']=='tag_t')+10)
 def test_tag_identity_and_name(self):
  pg=self.p['pages'][0];pg['tags']=[{'id':'t','kind':'flow','label':'流程','sentence_id':'','asset_id':''}];timeline.sync(self.p);pg['tags'][0]['label']='改名';timeline.sync(self.p);self.assertEqual([c['name'] for c in self.p['timeline']['clips'] if c.get('tag_id')=='t'],['改名']);pg['tags']=[];self.assertFalse(any(c.get('tag_id') for c in timeline.sync(self.p)['clips']))
 def test_deleted_sentence_orphan(self):
  pg=self.p['pages'][0];pg['tags']=[{'id':'t','kind':'title','label':'重点','sentence_id':pg['sentences'][0]['id']}];timeline.sync(self.p);pg['text']='完全不同的话。';sync_sentences(pg);self.assertTrue(next(c for c in timeline.sync(self.p)['clips'] if c.get('tag_id'))['orphaned'])
 def test_timeline_persists_and_undo_uses_versions(self):
  p=self.store.load(self.p['id']);p['timeline']['clips'].append({'id':'music','track':'music','name':'背景乐','start':0,'duration':2});saved=self.store.edit(p['id'],p);self.assertEqual(len(self.store.load(p['id'])['timeline']['clips']),3);self.assertRaises(Conflict,self.store.edit,p['id'],p|{'version':saved['version']-1})
 def test_reject_nonfinite_time(self):
  timeline.sync(self.p)['clips'].append({'id':'x','track':'pip','name':'x','start':float('nan'),'duration':1});self.assertRaises(ValueError,timeline.validate,self.p)
 def test_ai_proposal_requires_adoption(self):
  ms=Manuscripts(self.store);d=ms.save({'text':'原稿。'});d=ms.start({'id':d['id'],'kind':'rewrite'});self.assertEqual(d['status'],'pending_host');d=ms.accept_result(d,'润色稿。');self.assertEqual(ms.get(d['id'])['text'],'原稿。');ms.apply({'id':d['id']});self.assertEqual(ms.get(d['id'])['text'],'润色稿。')
 def test_ai_pages_reject_missing_duplicate_reordered(self):
  ms=Manuscripts(self.store);d=ms.save({'text':'第一句。第二句。第三句。'});d=ms.start({'id':d['id'],'kind':'paginate'});
  for groups in ([[0,1]],[[0,1,1,2]],[[1,0,2]]):self.assertRaises(ValueError,ms.accept_result,d,{'pages':[{'sentences':g} for g in groups]})
  result=ms.accept_result(d,{'pages':[{'title':'完整主题','sentences':[0,1,2]}]});self.assertEqual(result['pages'][0]['text'],d['text'])
 def test_edit_invalidates_pending_result(self):
  ms=Manuscripts(self.store);d=ms.save({'text':'旧稿。'});ms.start({'id':d['id'],'kind':'rewrite'});d=ms.save({'id':d['id'],'text':'修改后的稿件。'});self.assertEqual(d['status'],'editing');self.assertRaises(ValueError,ms.apply,{'id':d['id']})
 def test_markdown_preserves_identifier_and_removes_nonspoken_blocks(self):
  from ai_service import spoken_markdown
  text='# 连接 ESP32_S3\n**使用设备。**\n![图片](/image.png)\n```python\nprint(123)\n```'
  result=spoken_markdown(text);self.assertIn('ESP32_S3',result);self.assertIn('使用设备。',result);self.assertNotIn('print',result);self.assertNotIn('image.png',result)
 def test_settings_never_return_key(self):
  ms=Manuscripts(self.store);r=ms.configure({'url':'http://127.0.0.1:1234/v1/chat/completions','model':'local','key':'example-placeholder'});self.assertNotIn('key',r);self.assertTrue(r['has_key']);self.assertRaises(ValueError,ms.configure,{'url':'http://example.com','model':'x'})

if __name__=='__main__':unittest.main()
