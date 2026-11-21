import json
import sys
import tempfile
import unittest
from pathlib import Path
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from core import Store, default_project, source
from project_bundle import export_bundle, import_bundle


class ProjectBundleTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.origin = Store(self.root / '原工程')
        self.target = Store(self.root / '另一台电脑')
        original = self.root / '录制 01.mp4'
        original.write_bytes(b'original')
        rough = self.root / '粗剪.mp4'
        rough.write_bytes(b'rough')
        sticker = self.root / '透明贴纸.png'
        sticker.write_bytes(b'sticker')
        project = default_project('工程迁移')
        project.update(source_id='original', media=[
            {'id': 'original', 'kind': 'source', 'name': original.name, 'path': str(original)},
            {'id': 'rough', 'kind': 'rough', 'name': rough.name, 'path': str(rough)},
        ], rough={'media_id': 'rough', 'path': str(rough), 'mapping': []},
            assets=[{'id': 'sticker', 'name': sticker.name, 'path': str(sticker)}],
            approvals={'timeline': {'hash': 'different-machine'}})
        self.project = self.origin.save(project)

    def bundle(self, with_source=False):
        artifact = export_bundle(self.origin, self.project, lambda *_: None, with_source)
        return Path(artifact['path'])

    def test_complete_bundle_restores_source_rough_and_assets(self):
        bundle = self.bundle(True)
        with ZipFile(bundle) as archive:
            snapshot = json.loads(archive.read('project.json'))
            self.assertEqual(source(snapshot)['path'], 'media/source.mp4')
            self.assertNotIn(str(self.root), str(snapshot))
        receipt = import_bundle(self.target, bundle)
        restored = self.target.load(receipt['project_id'])
        self.assertNotEqual(receipt['original_id'], receipt['project_id'])
        self.assertEqual(restored['pages'][0]['id'], self.project['pages'][0]['id'])
        self.assertEqual(Path(source(restored)['path']).read_bytes(), b'original')
        self.assertEqual(Path(restored['rough']['path']).read_bytes(), b'rough')
        self.assertEqual(restored['assets'][0]['id'], 'sticker')
        self.assertEqual(Path(restored['assets'][0]['path']).read_bytes(), b'sticker')
        self.assertEqual(restored['approvals'], {})

    def test_light_bundle_keeps_relink_metadata_without_local_paths(self):
        bundle = self.bundle()
        with ZipFile(bundle) as archive:
            self.assertFalse(any(name.startswith('media/') for name in archive.namelist()))
        restored = self.target.load(import_bundle(self.target, bundle)['project_id'])
        self.assertEqual(source(restored)['name'], '录制 01.mp4')
        self.assertEqual(source(restored)['path'], '')
        self.assertTrue(source(restored)['external'])
        self.assertEqual(restored['rough']['path'], '')

    def test_already_cut_source_is_written_once(self):
        self.project['rough'].update(media_id='original', path=source(self.project)['path'])
        with ZipFile(self.bundle(True)) as archive:
            self.assertEqual([name for name in archive.namelist() if name.startswith('media/')],
                             ['media/source.mp4'])

    def test_legacy_project_retains_assets_but_requires_explicit_relink(self):
        bundle = self.root / 'legacy.zip'
        source(self.project)['external'] = True
        self.project['media'][1]['external'] = True
        self.project['assets'][0]['path'] = 'assets/sticker.png'
        with ZipFile(bundle, 'w') as archive:
            archive.writestr('assets/sticker.png', b'sticker')
            archive.writestr('project.json', json.dumps(self.project))
        restored = self.target.load(import_bundle(self.target, bundle)['project_id'])
        self.assertEqual(source(restored)['path'], '')
        self.assertEqual(Path(restored['assets'][0]['path']).read_bytes(), b'sticker')

    def test_invalid_member_or_reference_does_not_create_partial_project(self):
        bundle = self.root / 'invalid.zip'
        for name in ('assets/../escape.txt', 'assets/.. /escape.txt', 'assets/合法.png'):
            with self.subTest(name=name):
                with ZipFile(bundle, 'w') as archive:
                    archive.writestr(name, b'bad')
                    archive.writestr('project.json', json.dumps(self.project))
                with self.assertRaises(ValueError):
                    import_bundle(self.target, bundle)
                self.assertEqual(list(self.target.root.iterdir()), [])
