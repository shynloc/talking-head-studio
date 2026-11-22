"""Platform paths and the per-data-directory service lock."""

from contextlib import contextmanager
import os
import sys
import shutil
from pathlib import Path


def default_data_dir():
    return Path.home() / 'Documents' / 'TalkingHeadStudio'


def default_app_dir():
    if os.name == 'nt':
        parent = Path(os.environ.get('LOCALAPPDATA') or Path.home() / 'AppData' / 'Local')
    elif sys.platform == 'darwin':
        parent = Path.home() / 'Library' / 'Application Support'
    else:
        parent = Path.home() / '.local' / 'share'
    return parent / 'TalkingHeadStudio' / 'talking-head-studio'


def configure_tool_path():
    if sys.platform != 'darwin':
        return
    prefixes = (Path('/opt/homebrew'), Path('/usr/local'))
    candidates = [prefix / 'opt' / 'ffmpeg-full' / 'bin' for prefix in prefixes]
    candidates.extend(prefix / 'bin' for prefix in prefixes)
    current = os.environ.get('PATH', os.defpath).split(os.pathsep)
    paths = (str(path) for path in candidates if path.is_dir())
    os.environ['PATH'] = os.pathsep.join(dict.fromkeys([*paths, *current]))


def refresh_installed_tools():
    if os.name == 'nt':
        winget=Path(os.environ.get('LOCALAPPDATA') or Path.home()/'AppData/Local')/'Microsoft/WinGet'
        bins=[winget/'Links']
        if not shutil.which('ffprobe'):
            bins.extend(file.parent for file in (winget/'Packages').glob('Gyan.FFmpeg_*/**/bin/ffmpeg.exe'))
        current=os.environ.get('PATH',os.defpath).split(os.pathsep)
        os.environ['PATH']=os.pathsep.join(dict.fromkeys([*current,*(str(p) for p in bins if p.is_dir())]))
        return
    configure_tool_path()


@contextmanager
def data_lock(folder):
    with (folder / '.studio.lock').open('a+b') as lock:
        lock.seek(0)
        try:
            if os.name == 'nt':
                import msvcrt
                msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as exc:
            raise RuntimeError(f'此项目目录已由另一个工作台实例使用：{folder}') from exc
        yield
