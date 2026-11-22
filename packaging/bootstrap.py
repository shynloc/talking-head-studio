"""Install from the unmodified portable Skill archive beside this launcher."""
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

if __name__ == '__main__':
    with tempfile.TemporaryDirectory(prefix='talking-head-install-') as temp:
        with zipfile.ZipFile(Path(__file__).with_name('workbench.zip')) as archive:
            archive.extractall(temp)
        installer = Path(temp) / 'talking-head-studio/scripts/install_app.py'
        sys.exit(subprocess.call([sys.executable,'-X','utf8',str(installer),*sys.argv[1:]]))
