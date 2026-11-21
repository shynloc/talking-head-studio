import argparse,json,os,subprocess,sys,time,urllib.request,webbrowser
from pathlib import Path
from core import ROOT

def open_browser(url):
    if os.name=='nt':
        for base in (os.environ.get('PROGRAMFILES(X86)',''),os.environ.get('PROGRAMFILES','')):
            edge=Path(base)/'Microsoft/Edge/Application/msedge.exe'
            if edge.is_file():
                subprocess.Popen([str(edge),'--new-window',url],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
                return
    webbrowser.open(url)

def main():
    a=argparse.ArgumentParser();a.add_argument('--data',default=str(Path.home()/'Documents'/'TalkingHeadStudio'));a.add_argument('--port',type=int,default=8765);a.add_argument('--no-browser',action='store_true');args=a.parse_args()
    data=Path(args.data).resolve();data.mkdir(parents=True,exist_ok=True);url=f'http://127.0.0.1:{args.port}'
    try:
        with urllib.request.urlopen(url+'/api/bootstrap',timeout=2) as r:json.load(r)
        if not args.no_browser:open_browser(url)
        print(url);return
    except Exception:pass
    flags=getattr(subprocess,'CREATE_NO_WINDOW',0)
    with (data/'server.stdout.log').open('ab') as stdout,(data/'server.stderr.log').open('ab') as stderr:
        subprocess.Popen([sys.executable,'-u',str(ROOT/'scripts/server.py'),'--data',str(data),'--port',str(args.port)],cwd=ROOT,stdout=stdout,stderr=stderr,stdin=subprocess.DEVNULL,creationflags=flags,start_new_session=os.name!='nt')
    for _ in range(40):
        try:
            with urllib.request.urlopen(url+'/api/bootstrap',timeout=1) as r:json.load(r)
            if not args.no_browser:open_browser(url)
            print(url);return
        except Exception:time.sleep(.25)
    raise SystemExit('工作台启动失败，请检查 '+str(data/'server.stderr.log'))

if __name__=='__main__':main()
