"""Fixed references shared by searchable cards, Agent replies and portable library media."""
import json
import re
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import motion_recommend as recommend
import motion_samples as samples
import motion_treatments as treatments


class MaterialNumberTests(unittest.TestCase):
    def test_every_catalogue_entry_has_one_public_id(self):
        visual = samples.catalog()
        html = (samples.LIBRARY / 'index.html').read_text(encoding='utf8')
        embedded = re.search(r'<script id="catalog" type="application/json">(.*?)</script>', html, re.S)
        self.assertEqual(json.loads(embedded[1]), visual)
        groups = [('FX', recommend.catalog()['terms']), ('DEMO', treatments.catalog().values())]
        groups.extend((prefix, visual[group]) for prefix, group in
                      [('OBJ', 'objects'), ('STK', 'stickers'), ('WEB', 'styles'), ('PAL', 'palettes')])
        ids = set()
        for prefix, entries in groups:
            for entry in entries:
                code = entry['assetId']
                self.assertRegex(code, '^' + prefix + r'-[0-9]{3}$')
                self.assertNotIn(code, ids)
                ids.add(code)
        self.assertEqual(samples.selection({'objects': 'obj-017'}), {'objects': 'mic'})
        self.assertEqual(samples.selection({'objects':'OBJ-017@PAL-013'}), {'objects':'mic','palettes':'tidal'})
        with self.assertRaises(ValueError):
            samples.selection({'objects':'OBJ-017@PAL-013','palettes':'PAL-002'})
        with self.assertRaises(ValueError):
            samples.selection({'stickers': 'OBJ-017'})

    def test_new_artwork_is_real_and_has_alpha_in_every_palette(self):
        data = samples.catalog()
        for kind in ('objects', 'stickers'):
            for entry in data[kind]:
                for palette, variant in entry['variants'].items():
                    if entry['id'] not in data['recent'][kind] and palette not in data['recent']['palettes']:
                        continue
                    with self.subTest(kind=kind, name=entry['id'], palette=palette):
                        with Image.open(samples.LIBRARY / variant['preview']) as png:
                            low, high = png.getchannel('A').getextrema()
                            self.assertEqual(low, 0)
                            self.assertGreater(high, 120)
                        if kind == 'objects':
                            raw = (samples.LIBRARY / variant['model']).read_bytes()
                            self.assertEqual(raw[:4], b'glTF')
                            end = 20 + int.from_bytes(raw[12:16], 'little')
                            self.assertGreater(len(json.loads(raw[20:end])['meshes']), 0)
                        else:
                            svg = ET.parse(samples.LIBRARY / variant['vector'])
                            self.assertTrue(svg.getroot().tag.endswith('svg'))

    def test_agent_numbers_resolve_to_same_export_as_legacy_keys(self):
        chosen = dict(styles='WEB-012', palettes='PAL-013', objects='OBJ-017', stickers='STK-026')
        quote = '录播客时把麦克风放在手边。'
        ctx = recommend.snapshot(quote, [quote], chosen)
        row = dict(route='library', sentence=0, title='播客收音', reason='让观众看清收音设备。',
                   brief='透明麦克风和声音波形', visual=chosen)
        plan = recommend.recommendations(ctx, {'recommendations': [row]})[0]
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            master = samples.from_library(root, plan['visual'])
            self.assertEqual(master, samples.from_library(root, chosen))
            local = samples.folder(root, master['id'])
            self.assertEqual((local/'media.png').read_bytes(), samples.overlay_png(samples.brief(chosen)))
            self.assertEqual(json.loads((local/'sources/asset-ids.json').read_bytes()), chosen)
            self.assertIn('signalcard', (local/'sources/layout.html').read_text(encoding='utf8'))
        first = ctx['catalog'][0]
        row.update(route='catalog', ids=[first['assetId'].lower()])
        self.assertEqual(recommend.recommendations(ctx, {'recommendations': [row]})[0]['ids'], [first['id']])
        self.assertEqual(treatments.alternatives(['DEMO-001', 'cup-mark']), ['cup-mark'])
