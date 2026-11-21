"""Shared release contents and reversible installation of application code."""

import json
import os
import shutil
import tempfile
import time
from pathlib import Path

from core import ROOT, uid
from runtime import data_lock


PACKAGE_DIRS = ('agents', 'assets', 'scripts', 'vendor')
PACKAGE_FILES = (
    'README.md', 'SKILL.md', 'requirements.txt', 'install_macos.command', 'launch_macos.command',
    '安装工作台.cmd', '安装更新Skill.cmd', '安装依赖.cmd', '安装语音模型.cmd', '启动工作台.cmd',
)
IGNORE = shutil.ignore_patterns('__pycache__', '*.pyc', '.venv', '.git', '.env', '.env.*', '.DS_Store', 'Thumbs.db', 'html-creator-studio')


def check_paths(target, data):
    if target == ROOT or target in ROOT.parents or ROOT in target.parents:
        raise ValueError('请选择与解压目录分开的安装位置。')
    if target == data or target in data.parents or data in target.parents:
        raise ValueError('安装位置与项目数据目录需要分开。')


def move_app(source, target):
    deadline = time.monotonic() + 6
    while True:
        try:
            source.replace(target)
            return
        except OSError as exc:
            if getattr(exc, 'winerror', None) not in (5, 32) or time.monotonic() >= deadline:
                raise
            time.sleep(.15)


def replace_code(target, backup_dir, prepare, stop, start, recover):
    """Stage the full tree before stopping the old service and replacing code."""
    target.parent.mkdir(parents=True, exist_ok=True)
    backup = None
    with data_lock(target.parent), tempfile.TemporaryDirectory(prefix='.studio-install-', dir=target.parent) as tmp:
        staged = Path(tmp) / 'source'
        staged.mkdir()
        for name in PACKAGE_DIRS:
            shutil.copytree(ROOT / name, staged / name, ignore=IGNORE)
        for name in PACKAGE_FILES:
            shutil.copy2(ROOT / name, staged / name)
        if (ROOT / 'PACKAGE-MANIFEST.json').is_file():
            shutil.copy2(ROOT / 'PACKAGE-MANIFEST.json', staged / 'PACKAGE-MANIFEST.json')
        prepare(staged)
        stop()
        installed = False
        try:
            if target.exists():
                backup_dir.mkdir(parents=True, exist_ok=True)
                backup = backup_dir / uid('studio')
                move_app(target, backup)
            move_app(staged, target)
            installed = True
            start()
        except (OSError, RuntimeError, ValueError) as exc:
            if installed:
                move_app(target, staged)
            if backup and backup.exists():
                move_app(backup, target)
            recover()
            raise RuntimeError(f'安装未生效，已恢复先前的应用代码。{exc}') from exc
    return backup


def saved_settings(target):
    try:
        payload = json.loads((target / '.studio-deployment.json').read_text(encoding='utf-8'))
        if (isinstance(payload.get('data'), str) and Path(payload['data']).is_absolute()
                and isinstance(payload.get('port'), int) and 0 <= payload['port'] <= 65535):
            return payload
    except (OSError, ValueError, AttributeError):
        pass
    return {}
