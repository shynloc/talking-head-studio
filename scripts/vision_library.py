"""Select and resolve immutable VisionBuddy releases for the workbench."""
from contextlib import contextmanager
from contextvars import ContextVar
from functools import lru_cache
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import tempfile
from threading import Lock, RLock
import time
from urllib.error import URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from zipfile import BadZipFile, ZipFile

from core import ROOT, write_json

ORIGIN = "https://videobuddy.acks.com.cn"
GITHUB = "https://github.com/shynloc/acks-video-visionbuddy"
GITHUB_API = "https://api.github.com/repos/shynloc/acks-video-visionbuddy/releases/latest"
BUNDLED = "1.0.0"
SCRIPTS = ("catalog.json", "visual/catalog.json", "visual/treatments.json")
MAX_MANIFEST = 8 * 1024**2
MAX_PACK = 384 * 1024**2
VERSION = re.compile(r"\d{1,5}\.\d{1,5}\.\d{1,5}\Z")
ACTIVE = ContextVar("visionbuddy_release", default=None)


def valid_version(version):
    if not isinstance(version, str) or not VERSION.fullmatch(version):
        raise ValueError("无效的素材库版本。")
    return version


def valid_path(name):
    path = PurePosixPath(name)
    return name.startswith("site/") and path.as_posix() == name and all(
        part not in (".", "..") and not part.endswith((" ", ".")) and "\\" not in part and ":" not in part
        for part in path.parts
    )


def manifest(raw, version=None):
    data = json.loads(raw)
    if (not isinstance(data, dict) or data.get("schemaVersion") != 1
            or data.get("rendererVersion") not in (1, 2)):
        raise ValueError("此素材库需要兼容的工作台版本。")
    if valid_version(data.get("libraryRelease")) != (version or data["libraryRelease"]):
        raise ValueError("素材清单的版本不一致。")
    files = data.get("files")
    if not isinstance(files, dict) or any("site/" + f not in files for f in SCRIPTS):
        raise ValueError("素材版缺少目录文件。")
    seen = set()
    for name, record in files.items():
        if (not valid_path(name) or name.casefold() in seen or not isinstance(record, dict)
                or type(record.get("size")) is not int or not 0 <= record["size"] <= MAX_PACK
                or not isinstance(record.get("sha256"), str) or not re.fullmatch(r"[0-9a-f]{64}", record["sha256"])):
            raise ValueError("素材清单包含无效文件。")
        seen.add(name.casefold())
    if sum(f["size"] for f in files.values()) > MAX_PACK:
        raise ValueError("整库超过当前工作台的离线包大小上限。")
    return data


def verify(content, record):
    if len(content) != record["size"] or hashlib.sha256(content).hexdigest() != record["sha256"]:
        raise ValueError("素材文件校验失败，请重试。")
    return content


def fetch(url, limit, timeout=12):
    try:
        req = Request(url, headers={"User-Agent": "TalkingHeadStudio-VisionBuddy/1"})
        with urlopen(req, timeout=timeout) as response:
            body = response.read(limit + 1)
    except (OSError, URLError) as exc:
        raise ValueError("暂时连不上素材库。可继续使用本地库，或稍后重试。") from exc
    if len(body) > limit:
        raise ValueError("素材下载超过预期大小。")
    return body


@lru_cache(maxsize=24)
def read_manifest(path):
    return manifest(path.read_bytes(), path.parent.name)


class Release:
    def __init__(self, sources, version):
        self.sources = sources
        self.version = valid_version(version)
        self.root = sources.root / "releases" / version if sources else None

    def file(self, name):
        key = "site/" + name
        if not valid_path(key):
            raise ValueError("无效的素材文件路径。")
        if not self.root or not (self.root / "manifest.json").is_file():
            if self.version == BUNDLED:
                return ROOT / "assets/workbench/motion" / name
            raise ValueError("找不到此项目采用的素材库版本。")
        files = read_manifest(self.root / "manifest.json")["files"]
        if key not in files:
            raise FileNotFoundError(name)
        local = self.root / key
        if local.is_file():
            return local
        record = files[key]
        digest = record["sha256"]
        shared = self.sources.root / "files" / (digest + Path(name).suffix)
        with self.sources.file_lock(digest):
            if local.is_file():
                return local
            if shared.is_file():
                return shared
            existing = self.sources.find_matching_file(name, key, record)
            if existing is not None:
                return existing
            remote = f"{self.sources.origin}/releases/{self.version}/{quote(key)}"
            content = verify(fetch(remote, record["size"]), record)
            shared.parent.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(dir=shared.parent, delete=False) as temp:
                temp.write(content)
            os.replace(temp.name, shared)
            return shared


def current():
    return ACTIVE.get() or Release(None, BUNDLED)


@contextmanager
def using(release):
    saved = ACTIVE.set(release)
    try:
        yield
    finally:
        ACTIVE.reset(saved)


def data_path(name):
    return current().file(name)


class LibrarySources:
    def __init__(self, root, origin=ORIGIN):
        self.root = Path(root) / "visionbuddy"
        self.origin = origin.rstrip("/")
        self.settings_path = self.root / "source.json"
        self.lock = RLock()
        self._file_locks = {}
        self._file_locks_guard = Lock()

    def file_lock(self, digest):
        with self._file_locks_guard:
            return self._file_locks.setdefault(digest, Lock())

    def find_matching_file(self, name, key, record):
        bundled = ROOT / "assets/workbench/motion" / name
        releases = self.root / "releases"
        candidates = [bundled, *(path / key for path in releases.iterdir() if VERSION.fullmatch(path.name))]
        for path in candidates:
            try:
                if path.stat().st_size == record["size"] and hashlib.sha256(path.read_bytes()).hexdigest() == record["sha256"]:
                    return path
            except (FileNotFoundError, IsADirectoryError):
                continue
        return None

    def settings(self):
        if self.settings_path.is_file():
            return json.loads(self.settings_path.read_bytes())
        return {"mode": "local", "online": "", "local": ""}

    def for_version(self, version):
        return Release(self, version or BUNDLED)

    def active(self):
        settings = self.settings()
        return self.for_version(settings[settings["mode"]])

    def status(self):
        settings = self.settings()
        return {
            "mode": settings["mode"],
            "libraryRelease": settings[settings["mode"]] or BUNDLED,
            "installed": settings["local"] or None,
            "cachedOnline": settings["online"] or None,
            "offlineUpdate": settings.get("offlineUpdate"),
            "website": self.origin,
        }

    def save_manifest(self, data):
        dest = self.root / "releases" / data["libraryRelease"] / "manifest.json"
        if dest.is_file():
            if read_manifest(dest) != data:
                raise ValueError("同版本素材清单发生变化，请保留当前版本并联系发布者。")
        else:
            write_json(dest, data)

    def use_online(self):
        with self.lock:
            pointer = json.loads(fetch(self.origin + "/latest.json", 32768, 6))
            version = valid_version(pointer["libraryRelease"])
            path = f"/releases/{version}/manifest.json"
            if pointer.get("manifest") != path:
                raise ValueError("在线素材更新入口格式不正确。")
            if not (self.root / "releases" / version / "manifest.json").is_file():
                self.save_manifest(manifest(fetch(self.origin + path, MAX_MANIFEST), version))
            release = self.for_version(version)
            for name in SCRIPTS:
                release.file(name)
            settings = self.settings()
            settings.update(mode="online", online=version)
            write_json(self.settings_path, settings)
            return self.status()

    def use_local(self):
        with self.lock:
            settings = self.settings()
            settings["mode"] = "local"
            write_json(self.settings_path, settings)
            return self.status()

    def install(self, archive):
        with self.lock, tempfile.TemporaryDirectory() as work:
            try:
                bundle = ZipFile(archive)
            except BadZipFile as exc:
                raise ValueError("请选择 VisionBuddy 发布的 ZIP 文件。") from exc
            with bundle:
                names = bundle.namelist()
                if len(names) > 25000 or len(names) != len({x.casefold() for x in names}):
                    raise ValueError("素材包文件列表不正确。")
                names = set(names)
                entry = bundle.getinfo("manifest.json")
                if entry.file_size > MAX_MANIFEST:
                    raise ValueError("素材包清单过大。")
                data = manifest(bundle.read(entry))
                for name, record in data["files"].items():
                    if name not in names or bundle.getinfo(name).file_size != record["size"]:
                        raise ValueError("素材包文件大小与清单不一致。")
                    content = verify(bundle.read(name), record)
                    file = Path(work) / name
                    file.parent.mkdir(parents=True, exist_ok=True)
                    file.write_bytes(content)
            self.save_manifest(data)
            release = self.for_version(data["libraryRelease"])
            for name in data["files"]:
                target = release.root / name
                if target.is_file():
                    continue
                target.parent.mkdir(parents=True, exist_ok=True)
                content = (Path(work) / name).read_bytes()
                with tempfile.NamedTemporaryFile(dir=target.parent, delete=False) as temp:
                    temp.write(content)
                os.replace(temp.name, target)
            settings = self.settings()
            settings.update(mode="local", local=release.version, offlineUpdate=None, checkedLocal=time.time())
            write_json(self.settings_path, settings)
            return self.status()

    def github_release(self):
        release = json.loads(fetch(GITHUB_API, 1024**2, 12))
        version = valid_version(release.get("tag_name", "").removeprefix("v"))
        target = f"{GITHUB}/releases/download/v{version}/visionbuddy-v{version}.zip"
        if not any(asset.get("browser_download_url") == target for asset in release.get("assets", [])):
            raise ValueError("离线素材下载地址不正确。")
        return version, target

    def check_local(self):
        with self.lock:
            settings = self.settings()
            if settings["local"] and time.time() - settings.get("checkedLocal", 0) >= 86400:
                version, _ = self.github_release()
                available = tuple(map(int, version.split("."))) > tuple(map(int, settings["local"].split(".")))
                settings.update(checkedLocal=time.time(), offlineUpdate=version if available else None)
                write_json(self.settings_path, settings)
            return self.status()

    def update_local(self):
        version, target = self.github_release()
        if self.settings()["local"] == version:
            return self.use_local()
        with tempfile.TemporaryFile() as file:
            file.write(fetch(target, MAX_PACK, 90))
            file.seek(0)
            return self.install(file)
