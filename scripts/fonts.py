"""One bundled Chinese font for browser, Pillow, and ASS rendering."""

import os
import shutil
from pathlib import Path

from core import ROOT


FONT_FAMILY = 'Noto Sans CJK SC'
FONT_DIR = ROOT / 'assets/workbench/fonts'
FONT_FILE = FONT_DIR / 'NotoSansCJKsc-Regular.otf'
ASS_FILTER = 'ass=filename=captions.ass:fontsdir=fonts'


def render_font():
    if not FONT_FILE.is_file():
        raise RuntimeError('未找到随工作台提供的 Noto Sans CJK SC，请重新安装完整工作台。')
    return FONT_FILE


def stage_font(work):
    directory = Path(work) / 'fonts'
    directory.mkdir(exist_ok=True)
    source = render_font()
    target = directory / source.name
    if not target.is_file():
        try:
            os.link(source, target)
        except OSError:
            shutil.copy2(source, target)
    for name in ('font.css', 'OFL.txt'):
        shutil.copy2(FONT_DIR / name, directory / name)


def load_browser_font(page):
    loaded = page.evaluate("""async (family) => {
        const fonts = await document.fonts.load(`400 16px "${family}"`, '中文字幕');
        return fonts.some(font => font.status === 'loaded');
    }""", FONT_FAMILY)
    if not loaded:
        raise RuntimeError('Chromium 未加载内置中文字体。')
