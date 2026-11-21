"""Install/update this skill with an idle-server check and reversible code backup."""
import argparse,json,os,shutil,subprocess,sys,time,urllib.request
from pathlib import Path
from core import ROOT,VERSION

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--target',default=str(Path.home()/'.codex/skills/talking-head-studio'));ap.add_argument('--data',default=str(Path.home()/'Documents/TalkingHeadStudio'));ap.add_argument('--no-browser',action='store_true');a=ap.parse_args();target=Path(a.target).resolve();data=Path(a.data).resolve();data.mkdir(parents=True,exist_ok=True)
 if target==ROOT:raise SystemExit('当前已经在安装目录，请直接运行启动工作台.cmd')
 if target.name!='talking-head-studio':raise SystemExit('目标目录名必须为 talking-head-studio')
 record=data/'server.json'
 if record.exists():
  state=json.loads(record.read_text(encoding='utf-8'));url=state['url']
  if not url.startswith('http://127.0.0.1:'):raise SystemExit('服务记录不是本机地址')
  try:
   boot=json.load(urllib.request.urlopen(url+'/api/bootstrap',timeout=3))
  except Exception:boot=None
  if boot:
   for p in boot['projects']:
    jobs=json.load(urllib.request.urlopen(url+'/api/jobs?id='+p['id'],timeout=3))
    if any(j['status'] in ('running','queued') for j in jobs):raise SystemExit('媒体任务正在进行，请完成后重试安装')
   try:
    drafts=json.load(urllib.request.urlopen(url+'/api/v2/drafts',timeout=3))
    if any(d['status']=='running' for d in drafts):raise SystemExit('AI 任务正在进行，请完成后重试安装')
   except urllib.error.HTTPError:pass
   pid=int(state['pid'])
   if os.name!='nt':raise SystemExit('请先停止工作台服务再更新')
   cmd=f'(Get-CimInstance Win32_Process -Filter "ProcessId={pid}").CommandLine | ConvertTo-Json -Compress'
   raw=subprocess.check_output(['powershell','-NoProfile','-Command',cmd],text=True,encoding='utf-8',errors='replace').strip();line=json.loads(raw) if raw else ''
   if not line or 'server.py' not in line or str(target).lower().replace('\\','/') not in line.lower().replace('\\','/'):
    raise SystemExit('无法确认运行中服务属于目标 Skill，未停止任何进程')
   subprocess.run(['powershell','-NoProfile','-Command',f'Stop-Process -Id {pid} -ErrorAction Stop'],check=True)
 if target.exists():
  backup=data/'install-backups'/time.strftime('%Y%m%d-%H%M%S');shutil.copytree(target,backup,ignore=shutil.ignore_patterns('__pycache__','*.pyc'));print('Code backup:',backup)
 shutil.copytree(ROOT,target,dirs_exist_ok=True,ignore=shutil.ignore_patterns('.git','.venv','venv','__pycache__','*.pyc','.pytest_cache','.env','.env.*'))
 cmd=[sys.executable,str(target/'scripts/launch.py'),'--data',str(data)]
 if a.no_browser:cmd.append('--no-browser')
 subprocess.run(cmd,check=True);print('Installed Talking Head Studio',VERSION)
if __name__=='__main__':main()
