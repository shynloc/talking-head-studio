import json
import plistlib
import shlex
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from deployment import replace_code
from install_app import mac_shortcut
from launch import running_instance, stop_instance


class RuntimeTests(unittest.TestCase):
    def test_port_reuse_requires_matching_instance_identity(self):
        with tempfile.TemporaryDirectory() as temp:
            data = Path(temp)
            state = {'url': 'http://127.0.0.1:8765', 'id': 'saved-instance'}
            (data / 'server.json').write_text(json.dumps(state), encoding='utf-8')
            with patch('launch.request_json', return_value={'id': 'another-instance'}):
                self.assertIsNone(running_instance(data))
            with patch('launch.request_json', return_value={'id': state['id']}):
                self.assertEqual(running_instance(data), state)

    def test_upgrade_cannot_stop_another_apps_server(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            state = {'url': 'http://127.0.0.1:8765', 'code_root': str(root / 'other-app')}
            with patch('launch.running_instance', return_value=state), patch('launch.request_json') as post:
                with self.assertRaises(RuntimeError):
                    stop_instance(root / 'projects', root / 'current-app')
                post.assert_not_called()

    def test_mac_launcher_preserves_arguments_with_spaces_apostrophes_and_chinese(self):
        with tempfile.TemporaryDirectory() as temp:
            directory = Path(temp)
            command = ['/Users/Test/Library/Application Support/runtime/bin/python',
                       '/Users/Test/应用 源码/scripts/launch.py', '--data', "/Users/Test's 中文工程"]
            app = mac_shortcut(directory, command, directory)
            info = plistlib.loads((app / 'Contents/Info.plist').read_bytes())
            self.assertEqual(info['CFBundlePackageType'], 'APPL')
            launcher = app / 'Contents/MacOS' / info['CFBundleExecutable']
            line = launcher.read_text(encoding='utf-8').splitlines()[1]
            self.assertEqual(shlex.split(line.split(' >> ', 1)[0]), ['exec', *command])

    def test_failed_start_restores_prior_installation(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / 'source'
            installed = root / 'install' / 'talking-head-studio'
            backups = root / 'backups'
            source.mkdir()
            installed.mkdir(parents=True)
            (source / 'entry').write_text('new')
            (installed / 'entry').write_text('old')
            transitions = []

            def cannot_start():
                self.assertEqual((installed / 'entry').read_text(), 'new')
                raise RuntimeError('simulated start failure')

            def recover():
                transitions.append((installed / 'entry').read_text())

            with (
                patch('deployment.ROOT', source),
                patch('deployment.PACKAGE_DIRS', ()),
                patch('deployment.PACKAGE_FILES', ('entry',)),
            ):
                with self.assertRaisesRegex(RuntimeError, 'simulated start failure'):
                    replace_code(installed, backups, lambda stage: None,
                                 lambda: transitions.append('stop'), cannot_start, recover)
            self.assertEqual(transitions, ['stop', 'old'])
            self.assertEqual((installed / 'entry').read_text(), 'old')
