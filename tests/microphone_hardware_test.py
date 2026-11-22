"""Optional Windows/Edge physical-device smoke test; does not save microphone audio."""
import argparse,json
from pathlib import Path
from playwright.sync_api import sync_playwright

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--url',required=True);ap.add_argument('--out',required=True);a=ap.parse_args();out=Path(a.out);out.mkdir(parents=True,exist_ok=True)
 with sync_playwright() as pw:
  browser=pw.chromium.launch(channel='msedge',headless=False)
  context=browser.new_context(permissions=['microphone'],viewport={'width':1280,'height':900});page=context.new_page();errors=[];page.on('pageerror',lambda e:errors.append(str(e)))
  page.goto(a.url);page.click('#settings');page.click('[data-v2="mic"]');page.wait_for_selector('#mic-level-only')
  page.evaluate('window.levelSamples=0;window.levelPeak=0;const prior=micTester.onLevel;micTester.onLevel=n=>{levelSamples++;levelPeak=Math.max(levelPeak,n);prior(n)}')
  page.click('#mic-level-only');page.wait_for_function('micTester?.run?.processor && levelSamples>5',timeout=15000);page.wait_for_timeout(3000)
  result=page.evaluate('({active:micTester.active,device:micTester.stream.getAudioTracks()[0].label,track:micTester.stream.getAudioTracks()[0].readyState,levelSamples,levelPeak})')
  assert result['active'] and result['track']=='live'
  page.evaluate('window.observedTrack=micTester.stream.getAudioTracks()[0]');page.click('#mic-stop');page.wait_for_function('!micTester.active && observedTrack.readyState==="ended"');result['released']=True
  page.click('#mic-start');page.wait_for_function('micTester?.run?.processor && !!micTester.session',timeout=30000);result['recognizer_connected']=True
  page.click('#mic-stop');page.wait_for_function('!micTester.active && !micTester.session');page.screenshot(path=str(out/'physical-microphone.png'))
  browser.close();assert not errors,errors
 (out/'results.json').write_text(json.dumps({'status':'PASS',**result,'audio_saved':False,'human_read_along_verified':False},ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(result,ensure_ascii=False))
if __name__=='__main__':main()
