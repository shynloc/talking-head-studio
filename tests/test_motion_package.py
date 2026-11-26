import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import motion_package as motion


def block(data):
    return len(data).to_bytes(4, 'big') + data


class MotionExport(unittest.TestCase):
    def test_truncated_or_oversize_block(self):
        for body in (b'\x00', block(b'xyz')[:-1], block(b'abcd')):
            with self.subTest(body=body), self.assertRaises(ValueError):
                motion.Packet(io.BytesIO(body), len(body)).block(3)

    def test_incomplete_export_leaves_no_partial_pack(self):
        clip = dict(quote='一句话。', ids=['fade'], title='标题', seconds=1, poster=12)
        header = block(json.dumps(dict(format='talking-head-motion/1',items=[clip])).encode())
        for stream in [header, header+block(b'not a png')]:
            with tempfile.TemporaryDirectory() as tmp, patch.object(motion, 'status', return_value={'ready':True}):
                with self.assertRaises(ValueError):
                    motion.export(Path(tmp), io.BytesIO(stream), len(stream))
                self.assertFalse(list((Path(tmp)/'motion-packs').iterdir()))

    def test_only_known_media_package_names(self):
        with self.assertRaises(ValueError):
            motion.download(Path('.'), '../example')
        with self.assertRaises(ValueError):
            motion.validate({'format':'talking-head-motion/1','items':[]})
