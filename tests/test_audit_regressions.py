"""Regression coverage for the seven V2 audit findings; media/JS tests cover pixels and races."""
import copy,sys,tempfile,unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
from core import *
from ai_service import Manuscripts
from jobs import Jobs
import timeline,timeline_render,media,v2_api

class AuditRegressions(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.store=Store(self.tmp.name)
  self.p=default_project('audit fixture');self.p['pages']=[page('连接设备。'),page('开始演示。')]
  self.p['source_id']='source';self.p['media']=[{'id':'source','duration':8,'width':360,'height':640,'fps':12,'video':True,'audio':True,'path':'fixture.mp4'}]
  self.p['edl']=[{'id':'cut','start':0,'end':8,'keep':True}]
  self.p['rough']={'mapping':time_map(self.p['edl']),'edl_hash':digest(self.p['edl'])}
  self.p['transcript']=[{'id':'a','text':'连接设备。','start':0,'end':4,'words':[]},{'id':'b','text':'开始演示。','start':4,'end':8,'words':[]}]
  self.p['captions']=build_captions(self.p);self.p['approvals']['rough']={'fixture':True};timeline.sync(self.p);self.store.save(self.p)
  self.jobs=Jobs(self.store);self.ms=Manuscripts(self.store)
 def tearDown(self):
  self.jobs.pool.shutdown();self.ms.pool.shutdown();self.tmp.cleanup()
 def plan(self):
  self.jobs.action(self.p['id'],'plan',{},lambda *a:None);return self.store.load(self.p['id'])
 def extra(self):
  self.p['timeline']['clips'].append({'id':'extra','track':'main','name':'成品展示','before_page_id':self.p['pages'][0]['id'],'duration':10,'start':0,'asset_id':'image'})
 def test_A1_plan_twice_is_idempotent_and_editable(self):
  p=self.plan();ids=[c['id'] for c in p['timeline']['clips']]
  c=next(c for c in p['timeline']['clips'] if c.get('generated_by'));c['name']='保留手工命名';c['duration']=1.2;self.store.save(p)
  p=self.plan();self.assertEqual(ids,[c['id'] for c in p['timeline']['clips']]);c=next(c for c in p['timeline']['clips'] if c.get('generated_by'));self.assertEqual((c['name'],c['duration']),('保留手工命名',1.2))
  self.store.edit(p['id'],{'version':p['version'],'title':'成功保存'})
 def test_A1_repair_legacy_duplicate_generated_clip(self):
  p=self.plan();c=next(c for c in p['timeline']['clips'] if c.get('generated_by'));c.pop('generated_by');p['timeline']['clips'].append(copy.deepcopy(c));self.store.save(p)
  p=self.plan();self.assertEqual(len({c['id'] for c in p['timeline']['clips']}),len(p['timeline']['clips']));self.store.edit(p['id'],p)
 def test_A2_insert_and_alignment_backup_survive_repeated_calibration(self):
  self.extra();timeline.calibrate(self.p);self.assertEqual(self.p['timeline']['duration'],18)
  backup=copy.deepcopy(self.p['timeline_before_alignment']);timeline.calibrate(self.p)
  self.assertEqual(self.p['timeline']['clips'][0]['id'],'extra');self.assertEqual(backup,self.p['timeline_before_alignment'])
 def test_A2_manual_trim_and_order_survive_calibration(self):
  self.extra();timeline.calibrate(self.p);main=[c for c in self.p['timeline']['clips'] if c['track']=='main'];main[1]['source_in']=1;main[1]['duration']=2
  self.p['timeline']['clips']=[main[2],main[0],main[1]];before=copy.deepcopy(timeline.sync(self.p)['clips'])
  timeline.calibrate(self.p);self.assertEqual([(c['id'],c.get('source_in'),c['duration']) for c in before],[(c['id'],c.get('source_in'),c['duration']) for c in self.p['timeline']['clips']])
 def test_A2_recut_intersects_recording_and_preserves_extra(self):
  self.extra();timeline.calibrate(self.p)
  self.p['edl']=[{'id':'a','start':0,'end':2,'keep':True},{'id':'b','start':2,'end':3,'keep':False},{'id':'c','start':3,'end':8,'keep':True}]
  self.p['rough']={'mapping':time_map(self.p['edl']),'edl_hash':digest(self.p['edl'])};self.p['captions']=build_captions(self.p)
  timeline.calibrate(self.p);self.assertEqual(self.p['timeline']['duration'],17);self.assertEqual(self.p['timeline']['clips'][0]['id'],'extra');timeline.validate(self.p)
 def test_A2_recalibration_refreshes_caption_times_after_recut(self):
  timeline.calibrate(self.p);self.p['edl']=[{'id':'a','start':0,'end':1,'keep':False},{'id':'b','start':1,'end':8,'keep':True}]
  self.p['rough']={'mapping':time_map(self.p['edl']),'edl_hash':digest(self.p['edl'])}
  timeline.calibrate(self.p);self.assertEqual(self.p['captions'][-1]['end'],7);self.assertEqual(timeline_render.caption_map(self.p)[-1]['end'],7)
 def test_A2_presentation_page_is_preserved(self):
  demo=page('',kind='demo',title='展示',duration=10);demo['media_id']='image';self.p['pages'].insert(0,demo)
  timeline.calibrate(self.p);self.assertEqual(self.p['timeline']['clips'][0]['page_id'],demo['id']);self.assertEqual(self.p['timeline']['duration'],18)
 def test_A3_replacing_source_blocks_preview_until_recalibration(self):
  self.extra();timeline.calibrate(self.p);self.store.save(self.p);file=Path(self.tmp.name)/'new.mp4';file.touch()
  with patch.object(media,'probe',return_value={'video':True,'audio':True,'duration':8,'width':360,'height':640,'fps':12}):media.import_media(self.store,self.p['id'],file)
  p=self.store.load(self.p['id']);self.assertTrue(p['timeline']['needs_alignment']);self.assertRaisesRegex(ValueError,'原片已更换',timeline_render.render,self.store,p['id'],lambda *a:None)
  p['rough']={'mapping':time_map(p['edl']),'edl_hash':digest(p['edl'])};p['transcript']=self.p['transcript'];p['captions']=build_captions(p);timeline.calibrate(p)
  self.assertFalse(p['timeline'].get('needs_alignment'));self.assertEqual(p['timeline']['clips'][0]['id'],'extra');self.assertEqual({c['source_id'] for c in p['timeline']['clips'] if c.get('source_id')},{p['source_id']});timeline.validate_output(p)
 def test_A3_legacy_old_source_and_changed_edl_are_blocked(self):
  timeline.calibrate(self.p);self.p['timeline']['clips'][0]['source_id']='older';self.assertRaisesRegex(ValueError,'旧原片',timeline.validate_output,self.p)
  self.p['timeline']['clips'][0]['source_id']='source';self.p['edl'][0]['end']=7;self.assertRaisesRegex(ValueError,'粗剪',timeline.validate_output,self.p)
 def test_A4_append_clones_page_sentence_tag_identity_and_links(self):
  d=self.ms.save({'text':'连接设备。','project_id':self.p['id']});d.update(kind='paginate',status='review',input_hash=digest(d['text']),pages=[copy.deepcopy(self.p['pages'][0])])
  d['pages'][0]['tags']=[{'id':'tag','kind':'title','label':'重点','sentence_id':d['pages'][0]['sentences'][0]['id']}];write_json(self.ms.file(d['id']),d)
  server=SimpleNamespace(store=self.store,manuscripts=self.ms)
  p=v2_api.post(server,'/api/v2/create',{'id':d['id'],'project_id':self.p['id'],'version':self.p['version']})
  for _ in range(2):p=v2_api.post(server,'/api/v2/create',{'id':d['id'],'project_id':p['id'],'version':p['version'],'append':True})
  for values in ([pg['id'] for pg in p['pages']],[pg['sentences'][0]['id'] for pg in p['pages']],[pg['tags'][0]['id'] for pg in p['pages']]):self.assertEqual(len(set(values)),3)
  for pg in p['pages']:self.assertEqual(pg['tags'][0]['sentence_id'],pg['sentences'][0]['id'])
  self.store.edit(p['id'],p)
 def test_A5_captions_follow_inserted_media(self):
  self.extra();timeline.calibrate(self.p);caps=timeline_render.caption_map(self.p);self.assertEqual(caps[0]['start'],10);self.assertEqual(caps[-1]['end'],18)
 def test_A7_disabled_main_is_rejected_but_remains_repairable(self):
  timeline.calibrate(self.p);self.p['timeline']['clips'][0]['enabled']=False;timeline.validate(self.p)
  self.assertRaisesRegex(ValueError,'主轨不支持禁用',timeline.validate_output,self.p)
  self.p['timeline']['clips'][0]['enabled']=True;timeline.validate_output(self.p)
 def test_asr_word_overlapping_silent_cut_is_retained_once(self):
  self.p['edl']=[{'id':'a','start':0,'end':2.8,'keep':True},{'id':'b','start':2.8,'end':5,'keep':False},{'id':'c','start':5,'end':8,'keep':True}]
  self.p['transcript']=[{'id':'a','start':0,'end':8,'text':'电脑删后','words':[{'word':'电','start':1.9,'end':2.2},{'word':'脑','start':2.2,'end':4.68},{'word':'删','start':3,'end':4},{'word':'后','start':5.5,'end':6}]}]
  words=mapped_words(self.p);self.assertEqual(''.join(w['text'] for w in words),'电脑后');self.assertEqual(words[1]['end'],2.8)
  self.p['transcript'][0]['words']=[{'word':'跨边界','start':2,'end':6}]
  self.assertEqual(len(mapped_words(self.p)),1)

if __name__=='__main__':unittest.main()
