import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from zipfile import ZipFile

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import vision_library as vision


def fixture(version):
    files = {"site/" + name: json.dumps({"fixture": version}).encode() for name in vision.SCRIPTS}
    metadata = dict(schemaVersion=1, rendererVersion=1, libraryRelease=version,
                    files={key: dict(size=len(body), sha256=hashlib.sha256(body).hexdigest())
                           for key, body in files.items()})
    return metadata, files


def package(version, corrupt=False):
    data, files = fixture(version)
    result = BytesIO()
    with ZipFile(result, "w") as zip:
        zip.writestr("manifest.json", json.dumps(data))
        for key, body in files.items():
            zip.writestr(key, b"invalid" if corrupt else body)
    result.seek(0)
    return result


class LibrarySourceTests(unittest.TestCase):
    def test_switching_online_release_keeps_the_version_used_by_previous_projects(self):
        with tempfile.TemporaryDirectory() as temp:
            service = vision.LibrarySources(temp, "https://example.invalid")
            service.install(package("1.0.1"))
            data, files = fixture("1.0.2")

            def fetch(url, *_):
                if url.endswith("latest.json"):
                    return b'{"libraryRelease":"1.0.2","manifest":"/releases/1.0.2/manifest.json"}'
                if url.endswith("manifest.json"):
                    return json.dumps(data).encode()
                return files[url.split("/1.0.2/", 1)[1]]

            with patch.object(vision, "fetch", side_effect=fetch):
                self.assertEqual(service.use_online()["libraryRelease"], "1.0.2")
            with vision.using(service.for_version("1.0.1")):
                self.assertEqual(json.loads(vision.data_path("catalog.json").read_bytes())["fixture"], "1.0.1")
            with patch.object(vision, "fetch", side_effect=ValueError("offline")):
                self.assertEqual(service.use_local()["libraryRelease"], "1.0.1")
                self.assertEqual(service.active().file("visual/catalog.json").is_file(), True)

    def test_interrupted_zip_does_not_switch_active_release(self):
        with tempfile.TemporaryDirectory() as temp:
            service = vision.LibrarySources(temp)
            service.install(package("1.0.1"))
            with self.assertRaises(ValueError):
                service.install(package("1.0.2", corrupt=True))
            state = service.status()
            self.assertEqual(state["installed"], "1.0.1")
            self.assertEqual(state["libraryRelease"], "1.0.1")
