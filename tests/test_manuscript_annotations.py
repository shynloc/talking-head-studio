import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from ai_service import balanced_pages
from manuscript_annotations import analyze
from motion_recommend import annotation_review, recommendations, snapshot


class ManuscriptAnnotations(unittest.TestCase):
    def test_paragraph_and_inline_have_distinct_scopes(self):
        raw = (
            '开头（顺便说一句）。\r\n\r\n'
            '🧪先试麦克风。再播一段（画面：无）。\r\n'
            '（画面：用麦克风 OBJ-017@PAL-013（原款）。）\r\n'
            '（画面：慢慢显出来 FX-001。）\r\n\r\n'
            '再换一个位置。'
        )
        with tempfile.TemporaryDirectory() as root:
            review = annotation_review(Path(root), raw)
        self.assertEqual([b["mode"] for b in review["bindings"]], ["specified", "none"])
        first = review["bindings"][0]
        self.assertEqual(first["sentences"], [1])
        self.assertEqual(first["visual"], {"objects": "mic", "palettes": "tidal"})
        self.assertEqual(first["ids"], ["fade"])
        self.assertTrue(first["overlay"])
        # The emoji occurs before the third sentence and occupies two DOM code units.
        third = review["units"][2]
        self.assertEqual(third["offset"], len(review["text"].split("再播")[0].encode("utf-16-le")) // 2)
        self.assertIn("（顺便说一句）", review["text"])
        self.assertFalse(any("画面：" in page["text"] for page in balanced_pages(raw)))

    def test_invalid_and_incomplete_marks_remain_excluded(self):
        raw = ('第一段有正文。\n（画面：用 OBJ-999）\n\n我再补充一句。\n（画面：用 FX-001\n\n最后再说明。')
        with tempfile.TemporaryDirectory() as root:
            review = annotation_review(Path(root), raw)
        self.assertEqual([b['mode'] for b in review['bindings']], ['error', 'error'])
        ctx = snapshot(review['text'], [unit['quote'] for unit in review['units']], marked_script=raw)
        self.assertEqual(ctx['eligibleSentences'], [2])
        rows = [{'sentence': i, 'ids': ['FX-001'], 'title': '新画面', 'reason': '对应原话。'} for i in range(3)]
        self.assertEqual([row['sentence'] for row in recommendations(ctx, {'recommendations': rows})], [2])
        self.assertIn('最后再说明。', review['text'])

    def test_orphan_cue_and_two_sentences_under_one_paragraph(self):
        raw = '（画面：无）\n开口说一句。再试一段声音。\n（画面：用 OBJ-017@PAL-013 、FX-001，时长 2 秒，说到「试一段声音」时出现。）'
        clean, units, bindings, errors = analyze(raw)
        self.assertEqual(len(errors), 1)
        self.assertEqual(bindings[0]['sentences'], [0, 1])
        with tempfile.TemporaryDirectory() as root:
            first = annotation_review(Path(root), raw)['bindings'][0]
        self.assertEqual(first['cue'], '试一段声音')
        self.assertEqual(first['seconds'], 2)
        self.assertEqual(first['quote'], clean)
