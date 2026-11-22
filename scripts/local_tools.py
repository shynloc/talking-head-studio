"""Install a creator-selected, known local media dependency in the running environment."""
import importlib
import os
import shutil
import subprocess
import sys
from pathlib import Path
from core import ROOT
from runtime import refresh_installed_tools


def prepare(action,data,report):
    python=[sys.executable,'-X','utf8']
    if action=='prepare_follow':
        report(.1,'正在准备本地跟读组件和中英文模型…')
        command=python+[str(ROOT/'scripts/setup_speech.py'),'--data',str(data)]
    elif action=='prepare_transcription':
        report(.1,'正在安装本地语音识别组件…')
        command=python+[str(ROOT/'scripts/setup.py'),'--speech']
    elif action=='prepare_video_tools':
        if not (shutil.which('ffmpeg') and shutil.which('ffprobe')):
            report(.1,'正在安装视频处理工具…')
            if os.name=='nt' and shutil.which('winget'):
                install=['winget','install','--exact','--id','Gyan.FFmpeg','--scope','user','--accept-package-agreements','--accept-source-agreements']
            elif sys.platform=='darwin' and shutil.which('brew'):
                install=['brew','install','ffmpeg-full']
            else:
                raise ValueError('需要本机的 winget 或 Homebrew。也可以先安装完整 FFmpeg，再点一次准备视频工具。')
            subprocess.run(install,check=True)
            refresh_installed_tools()
        report(.48,'正在准备视频合成工具…')
        command=python+[str(ROOT/'scripts/setup.py'),'--install','--smoke']
    else:
        raise ValueError('未知工具。')
    subprocess.run(command,check=True)
    importlib.invalidate_caches()
    return {'message':'工具已准备好，可以继续。'}
