"""Build desktop distributions around the same verified Skill archive."""
import argparse
import json
import os
import plistlib
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0,str(HERE.parent/'scripts'))
from core import VERSION, file_digest
from package_release import verify

PYTHON = '3.13.14'
RUNTIMES = {
    'windows': ('python-3.13.14-amd64.exe','c54d9b9bbb8a36e6489363ddd01139707fd781d72f1f9e90c7ec65d0061368e0'),
    'macos': ('python-3.13.14-macos11.pkg','8e58affb218c155a1dfdc27b291f817129669f8760e7a297adb2e4439ba5d2e8'),
}
APP = '口播导演工作台'

def run(*args):
    subprocess.run(args,check=True)

def runtime(platform,cache):
    name,checksum=RUNTIMES[platform]
    cache.mkdir(parents=True,exist_ok=True)
    result=cache/name
    if result.is_file() and file_digest(result)==checksum:return result
    with tempfile.TemporaryDirectory(dir=cache) as tmp:
        candidate=Path(tmp)/name
        with urllib.request.urlopen('https://www.python.org/ftp/python/'+PYTHON+'/'+name,timeout=90) as response, candidate.open('wb') as out:
            shutil.copyfileobj(response,out)
        if file_digest(candidate)!=checksum:raise ValueError('Python 安装包校验失败。')
        candidate.replace(result)
    return result

def notarize(submission,staple,profile):
    result=subprocess.check_output(['xcrun','notarytool','submit',str(submission),'--keychain-profile',profile,'--wait','--output-format','json'])
    reply=json.loads(result)
    if reply.get('status')!='Accepted':raise RuntimeError('Apple 公证状态 '+str(reply.get('status'))+' '+str(reply.get('id')))
    run('xcrun','stapler','staple',staple)
    run('xcrun','stapler','validate',staple)

def build(platform,archive,out,cache,identity,profile):
    manifest=verify(archive)
    if manifest['version']!=VERSION:raise ValueError('工作台和安装包版本不一致。')
    installer=runtime(platform,cache)
    stem=f'talking-head-studio-v{VERSION}'
    if platform=='windows':
        result=out/(stem+'-windows-x64.zip')
        with zipfile.ZipFile(result,'w') as bundle:
            bundle.write(archive,'setup/workbench.zip')
            bundle.write(installer,'setup/'+installer.name)
            bundle.write(HERE/'bootstrap.py','setup/bootstrap.py')
            cmd=(HERE/'windows/Install.cmd').read_text(encoding='ascii').replace('\n','\r\n')
            bundle.writestr('安装并打开工作台.cmd',cmd.encode('ascii'))
        return result
    if sys.platform!='darwin':raise ValueError('请在装有 Xcode 命令行工具的 Mac 上构建 DMG。')
    if bool(identity)!=bool(profile):raise ValueError('签名发布需要同时提供 Developer ID 身份和 notarytool 配置。')
    with tempfile.TemporaryDirectory() as tmp:
        work=Path(tmp)
        volume=work/'disk';app=volume/(APP+'.app')
        binary=app/'Contents/MacOS/Studio';resources=app/'Contents/Resources'
        binary.parent.mkdir(parents=True);resources.mkdir()
        for arch in ('arm64','x86_64'):
            run('xcrun','swiftc','-O','-target',arch+'-apple-macos11.0','-o',work/arch,HERE/'macos/Studio.swift')
        run('lipo','-create',work/'arm64',work/'x86_64','-output',binary)
        with (app/'Contents/Info.plist').open('wb') as info:
            plistlib.dump(dict(CFBundleIdentifier='com.talkingheadstudio.desktop',CFBundleName=APP,CFBundleDisplayName=APP,
                CFBundleExecutable='Studio',CFBundlePackageType='APPL',CFBundleShortVersionString=VERSION,CFBundleVersion=VERSION,
                LSMinimumSystemVersion='11.0',NSHighResolutionCapable=True),info)
        shutil.copy2(installer,resources/installer.name)
        shutil.copy2(archive,resources/'workbench.zip')
        shutil.copy2(HERE/'bootstrap.py',resources)
        run('codesign','--force','--options','runtime',*(['--timestamp'] if identity else []),'--sign',identity or '-',app)
        run('codesign','--verify','--strict',app)
        if identity:
            sealed=work/'application.zip'
            run('ditto','-c','-k','--keepParent',app,sealed)
            notarize(sealed,app,profile)
        (volume/'Applications').symlink_to('/Applications')
        result=out/(stem+('-macos.dmg' if identity else '-macos-preview.dmg'))
        run('hdiutil','create','-ov','-fs','HFS+','-volname',APP,'-srcfolder',volume,'-format','UDZO',result)
        if identity:
            run('codesign','--timestamp','--sign',identity,result)
            notarize(result,result,profile)
        return result

if __name__=='__main__':
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('platform',choices=RUNTIMES)
    ap.add_argument('--archive',type=Path,required=True)
    ap.add_argument('--out',type=Path,required=True)
    ap.add_argument('--cache',type=Path,default=Path.home()/'.cache/talking-head-studio-build')
    ap.add_argument('--identity',default=os.getenv('STUDIO_SIGN_IDENTITY',''))
    ap.add_argument('--notary-profile',default=os.getenv('STUDIO_NOTARY_PROFILE',''))
    args=ap.parse_args()
    args.out.mkdir(parents=True,exist_ok=True)
    package=build(args.platform,args.archive,args.out,args.cache,args.identity,args.notary_profile)
    (package.parent/(package.name+'.sha256')).write_text(file_digest(package)+'  '+package.name+'\n',encoding='ascii')
    print(package)
