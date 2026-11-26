import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import core
import guided_preview
from subtitle_input import read_segments


class GuidedPreview(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name)
        self.jobs=Mock()
        self.project=core.default_project()
        self.project.update(source_id='src',media=[{'id':'src','audio':True}],edl=[{'start':0,'end':24,'keep':True}])
        self.project['rough']={'edl_hash':core.edl_digest(self.project['edl'])}
        self.project['approvals']['rough']={'actor':'user'}
        self.jobs.store.load.return_value=self.project
        self.info={'models':[], 'modules':{'whisper':False,'torch':False}, 'tools':{'ffmpeg':True,'ffprobe':True}}
        self.doctor=patch.object(guided_preview,'doctor',return_value=self.info)
        self.doctor.start()
        self.addCleanup(self.doctor.stop)

    def resume(self, **args):
        return guided_preview.prepare(self.jobs,'pid',{'entry':'resume','source_id':'src',**args},Mock())

    def test_first_download_requires_consent_and_continues_after_consent(self):
        self.assertEqual(self.resume()['next'],'setup')
        self.jobs.action.assert_not_called()
        self.jobs.action.side_effect=[{}, {'engine':'base','device':'cpu','segments':0}]
        self.assertEqual(self.resume(allow_download=True)['next'],'subtitles')
        self.assertEqual([c.args[1] for c in self.jobs.action.call_args_list],['prepare_transcription','transcribe'])

    def test_missing_video_tools_keep_chosen_inputs_without_import(self):
        self.info['tools']['ffmpeg']=False
        result=guided_preview.prepare(self.jobs,'pid',dict(entry='import',path='talk.mp4',subtitle_path='talk.vtt'),Mock())
        self.assertEqual((result['next'],result['options']['subtitle_path']),('tools','talk.vtt'))
        self.jobs.action.assert_not_called()

    def test_silent_or_replaced_recording(self):
        self.project['media'][0]['audio']=False
        self.assertEqual(self.resume()['next'],'subtitles')
        with self.assertRaises(ValueError): self.resume(source_id='old-file')
        self.jobs.action.assert_not_called()

    def test_stale_cut_selection_cannot_be_approved(self):
        with self.assertRaises(core.Conflict):
            self.resume(entry='use_cuts',edl=[{'start':0,'end':22,'keep':True}])
        self.jobs.action.assert_not_called()

    def test_analysis_returns_review_only_for_removed_intervals(self):
        self.project['edl'] = [{'start':0,'end':20,'keep':True},{'start':20,'end':24,'keep':False}]
        self.assertEqual(self.resume(entry='find_cuts')['next'],'cuts')
        self.assertEqual([c.args[1] for c in self.jobs.action.call_args_list],['analyze_cuts'])

    def test_no_cuts_continues_without_an_extra_confirmation(self):
        self.project['media'][0]['audio'] = False
        self.assertEqual(self.resume(entry='find_cuts')['next'],'subtitles')
        self.assertEqual([c.args[1] for c in self.jobs.action.call_args_list],['analyze_cuts'])

        self.assertEqual(self.project['approvals']['rough']['kind'],'no_cuts')

    def test_vtt_short_times_and_invalid_or_outside_cue(self):
        sidecar=self.folder/'take.vtt'
        sidecar.write_text('WEBVTT\n\n00:02.100 --> 00:03.850 align:start\n保留此句。\n',encoding='utf8')
        cue,=read_segments(sidecar,5)
        self.assertEqual((cue['start'],cue['end'],cue['text']),(2.1,3.85,'保留此句。'))
        with self.assertRaises(ValueError): read_segments(sidecar,2)

    @patch.object(guided_preview,'review_state')
    def test_resume_uses_first_retained_caption_without_overwriting_edits(self, review):
        self.project['captions']=[{'text':'我的修改'}]
        review.return_value={'state':'ready','duration':24,'caption_spans':[{'start':13.4}],'sample':None}
        self.jobs.action.return_value={'id':'sample'}
        self.assertEqual(self.resume()['sample_id'],'sample')
        call=self.jobs.action.call_args
        self.assertEqual(call.args[1],'timeline_sample')
        self.assertAlmostEqual(call.args[2]['start'],13.2)
        self.assertEqual(call.args[2]['duration'],10)
        self.jobs.action.reset_mock()
        review.return_value['sample']={'start':13.2,'duration':10,'id':'cached'}
        self.assertEqual(self.resume()['sample_id'],'cached')
        self.jobs.action.assert_not_called()


if __name__=='__main__':
    unittest.main()
