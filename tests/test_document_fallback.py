import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
import media


class DocumentFallbackTests(unittest.TestCase):
    def test_docx_keeps_paragraph_and_table_order_without_optional_component(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / '稿件.docx'
            with ZipFile(path, 'w') as archive:
                archive.writestr('word/document.xml', '''
                    <w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
                      <w:body>
                        <w:p><w:r><w:t>先连接</w:t></w:r><w:r><w:t>设备。</w:t></w:r></w:p>
                        <w:tbl><w:tr><w:tc><w:p><w:r><w:t>检查声音。</w:t></w:r></w:p></w:tc></w:tr></w:tbl>
                        <w:p><w:r><w:t>开始录制。</w:t></w:r></w:p>
                      </w:body>
                    </w:document>''')
            with patch.object(media, 'HCS_DIR', Path(temp) / 'not-installed'):
                self.assertEqual(media.extract_document(path), '先连接设备。\n检查声音。\n开始录制。')
