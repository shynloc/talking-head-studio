"""Dependency diagnostics and optional local installation. Never downloads speech models silently."""
import argparse,importlib.metadata,json,subprocess,sys,shutil,tempfile
from pathlib import Path
from jobs import doctor
from core import ROOT

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--install',action='store_true');ap.add_argument('--speech',action='store_true');ap.add_argument('--smoke',action='store_true');ap.add_argument('--out');a=ap.parse_args()
    if a.install:
        subprocess.run([sys.executable,'-m','pip','install','-r',str(ROOT/'requirements.txt')],check=True)
        subprocess.run([sys.executable,'-m','playwright','install','chromium'],check=True)
    if a.speech:subprocess.run([sys.executable,'-m','pip','install','openai-whisper'],check=True)
    report=doctor();report['packages']={}
    for package in ('playwright','Pillow','numpy','openai-whisper','torch','pypdf','python-pptx'):
        try:report['packages'][package]=importlib.metadata.version(package)
        except importlib.metadata.PackageNotFoundError:pass
    if a.smoke:
        from playwright.sync_api import sync_playwright
        with tempfile.TemporaryDirectory() as temp:
            png=Path(temp)/'alpha.png';out=Path(temp)/'smoke.mp4'
            with sync_playwright() as p:
                b=p.chromium.launch(headless=True);tab=b.new_page(viewport={'width':320,'height':240});tab.set_content('<html style="background:transparent"><div style="width:100px;height:100px;background:#72efcb;border-radius:30px"></div></html>');tab.screenshot(path=str(png),omit_background=True);b.close()
            subprocess.run(['ffmpeg','-nostdin','-v','error','-loop','1','-i',str(png),'-t','0.5','-vf','format=yuv420p','-c:v','libx264','-y',str(out)],check=True)
            subprocess.run(['ffmpeg','-nostdin','-v','error','-i',str(out),'-f','null','-'],check=True)
            report['chromium_ffmpeg_smoke']='PASS'
    if a.out:Path(a.out).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps(report,ensure_ascii=False,indent=2))

if __name__=='__main__':main()
