"""Explicit, resumable download of pinned local streaming models. No credentials needed."""
import argparse,hashlib,subprocess,sys,urllib.request,time
from pathlib import Path
FILES={
 'tokens.txt':(56317,'a8e0e4ec53810e433789b54a5c0134a7eaa2ffca595a6334d54c00da858841d3'),
 'encoder-epoch-99-avg-1.int8.onnx':(181895032,'8fa764187a261844f859d7143ebaa563af5d10adfece4c18a8f414c88cba2a9b'),
 'decoder-epoch-99-avg-1.onnx':(13876452,'2e3b5ec371f8899ee6acd829fd753ba45772df57a91bdf37cde3136354e7db7d'),
 'joiner-epoch-99-avg-1.int8.onnx':(3228404,'1ed689c5ed19dbaa725d9d191bb4822b5f4855a39e1ffd28cbc1f340d25b2ee0')}
BASE='https://huggingface.co/csukuangfj/sherpa-onnx-streaming-zipformer-bilingual-zh-en-2023-02-20/resolve/main/'
def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  while x:=f.read(1024*1024):h.update(x)
 return h.hexdigest()
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--data',default=str(Path.home()/'Documents/TalkingHeadStudio'));ap.add_argument('--skip-pip',action='store_true');a=ap.parse_args()
 if not a.skip_pip:subprocess.run([sys.executable,'-m','pip','install','sherpa-onnx==2.0.2'],check=True)
 root=Path(a.data).resolve()/'models/streaming-zh-en';root.mkdir(parents=True,exist_ok=True)
 for name,(size,expected) in FILES.items():
  target=root/name
  if target.exists() and target.stat().st_size==size and sha(target)==expected:print(name,'verified',flush=True);continue
  partial=root/(name+'.download')
  for attempt in range(8):
   n=partial.stat().st_size if partial.exists() else 0
   if n==size:
    if sha(partial)==expected:partial.replace(target);break
    partial.unlink();n=0
   try:
    req=urllib.request.Request(BASE+name+'?download=true&offset='+str(n),headers={'Range':f'bytes={n}-'})
    with urllib.request.urlopen(req,timeout=120) as r:
     append=r.status==206 and r.headers.get('Content-Range','').startswith(f'bytes {n}-')
     if r.status not in (200,206):raise ValueError('Unexpected download response')
     with partial.open('ab' if append else 'wb') as f:
      while chunk:=r.read(1024*1024):f.write(chunk)
    print(name,partial.stat().st_size,'/',size,flush=True)
    if partial.stat().st_size==size and sha(partial)==expected:partial.replace(target);break
   except Exception as e:print('retry',attempt+1,type(e).__name__,flush=True);time.sleep(1)
  if not target.exists() or target.stat().st_size!=size or sha(target)!=expected:raise SystemExit('Download verification failed: '+name)
 from speech_live import LiveSpeech
 speech=LiveSpeech(Path(a.data));speech.root=root;session=speech.start();speech.stop(session['id']);print('Local streaming recognizer load: PASS')
if __name__=='__main__':main()
