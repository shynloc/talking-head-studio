import hashlib
from io import BytesIO
import json
from pathlib import Path
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
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
    def test_matching_content_is_reused_across_releases(self):
        with tempfile.TemporaryDirectory() as temp:
            service = vision.LibrarySources(temp)
            service.install(package("1.0.1"))
            data, _ = fixture("1.0.1")
            data["libraryRelease"] = "1.0.2"
            service.save_manifest(data)
            with patch.object(vision, "fetch") as download:
                current = service.for_version("1.0.2").file("visual/catalog.json")
                download.assert_not_called()
            self.assertEqual(current.read_bytes(), json.dumps({"fixture": "1.0.1"}).encode())

    def test_distinct_files_download_in_parallel_and_same_file_once(self):
        with tempfile.TemporaryDirectory() as temp:
            service = vision.LibrarySources(temp)
            data, files = fixture("1.0.2")
            for index, name in enumerate(files):
                body = bytes([index])
                files[name] = body
                data["files"][name] = dict(size=1, sha256=hashlib.sha256(body).hexdigest())
            service.save_manifest(data)
            release = service.for_version("1.0.2")
            barrier = Barrier(2)

            def fetch(url, _):
                barrier.wait(timeout=3)
                return files[url.split("/1.0.2/")[1]]

            with patch.object(vision, "fetch", side_effect=fetch) as network:
                with ThreadPoolExecutor(max_workers=3) as pool:
                    paths = list(pool.map(release.file, ("catalog.json", "catalog.json", "visual/catalog.json")))
                self.assertEqual(network.call_count, 2)
            self.assertEqual([p.read_bytes() for p in paths], [b"\x00", b"\x00", b"\x01"])

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
