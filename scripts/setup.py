"""Dependency diagnostics and optional local installation. Never downloads speech models silently."""
import argparse,importlib.metadata,json,subprocess,sys,shutil,tempfile
from pathlib import Path
from jobs import doctor
from core import ROOT, default_project
import fonts
import media
from runtime import configure_tool_path


def check_ffmpeg():
    if not all(shutil.which(tool) for tool in ('ffmpeg', 'ffprobe')):
        raise SystemExit('请先安装 FFmpeg 和 ffprobe。macOS 可使用 brew install ffmpeg-full。')
    filters = media.run(['ffmpeg', '-hide_banner', '-filters'])
    if not any(line.split()[1:2] == ['ass'] for line in filters.splitlines()):
        raise SystemExit('当前 FFmpeg 缺少 libass。请安装包含 libass 和 libx264 的完整构建。')


def smoke_test():
    from PIL import ImageFont
    from playwright.sync_api import sync_playwright

    test_font = ImageFont.truetype(fonts.render_font(), 24)
    if test_font.getname()[0] != fonts.FONT_FAMILY:
        raise RuntimeError('Pillow 未识别内置中文字体。')
    with tempfile.TemporaryDirectory(prefix='工作台 字体校验-') as temp:
        work = Path(temp)
        html = work / 'preview.html'
        fonts.stage_font(work)
        html.write_text(
            '<meta charset="utf-8"><link rel="stylesheet" href="fonts/font.css">'
            '<style>body{margin:0;background:transparent;font:24px "Noto Sans CJK SC"}</style>'
            '<div style="width:190px;padding:12px;background:#72efcb">中文动画和字幕</div>',
            encoding='utf-8',
        )
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True, args=['--allow-file-access-from-files'])
            page = browser.new_page(viewport={'width': 320, 'height': 240})
            page.goto(html.as_uri())
            fonts.load_browser_font(page)
            page.screenshot(path=str(work / 'alpha.png'), omit_background=True)
            browser.close()
        project = default_project()
        project['captions'] = [{'text': '简体中文：口播导演工作台', 'start': 0, 'end': .5}]
        media.subtitles(project, work, 320, 240)
        media.run(['ffmpeg', '-nostdin', '-v', 'info', '-loop', '1', '-i', 'alpha.png', '-t', '0.5',
                   '-vf', fonts.ASS_FILTER + ',format=yuv420p', '-c:v', 'libx264', '-y', 'smoke.mp4'],
                  work / 'encode.log', cwd=work)
        log = (work / 'encode.log').read_text(encoding='utf-8', errors='replace')
        if not any('NotoSansCJKsc-Regular' in line for line in log.splitlines() if 'fontselect' in line):
            raise RuntimeError('FFmpeg 未使用内置中文字体。')
        media.run(['ffmpeg', '-v', 'error', '-i', work / 'smoke.mp4', '-f', 'null', '-'])

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--install',action='store_true');ap.add_argument('--writing-only',action='store_true');ap.add_argument('--speech',action='store_true');ap.add_argument('--smoke',action='store_true');ap.add_argument('--out');a=ap.parse_args()
    configure_tool_path()
    if a.smoke:
        check_ffmpeg()
    if a.writing_only:
        subprocess.run([sys.executable,'-m','pip','install','pypdf>=5,<7','python-pptx>=1,<2'],check=True)
    if a.install:
        subprocess.run([sys.executable,'-m','pip','install','-r',str(ROOT/'requirements.txt')],check=True)
        subprocess.run([sys.executable,'-m','playwright','install','chromium'],check=True)
    if a.speech:subprocess.run([sys.executable,'-m','pip','install','openai-whisper'],check=True)
    report=doctor();report['packages']={}
    for package in ('playwright','Pillow','numpy','openai-whisper','torch','pypdf','python-pptx'):
        try:report['packages'][package]=importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:pass
    if a.smoke:
        smoke_test()
        report['chromium_ffmpeg_smoke']='PASS'
        report['chinese_font_smoke']='PASS (Chromium, Pillow, libass)'
    if a.out:Path(a.out).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
