"""Bounded local streaming recognition, independent of rendering jobs."""
import base64, importlib.util, os, threading, time
from pathlib import Path
from core import uid

class LiveSpeech:
    def __init__(self,root):
        self.root=Path(os.environ.get('STUDIO_SPEECH_MODEL',str(root/'models'/'streaming-zh-en')))
        self.lock=threading.RLock();self.recognizer=None;self.sessions={}
    def status(self):
        from setup_speech import FILES
        ready=all((self.root/n).is_file() and (self.root/n).stat().st_size==meta[0] for n,meta in FILES.items())
        return {'installed':bool(importlib.util.find_spec('sherpa_onnx')),'model_ready':ready,'engine':'本地流式识别 · 中文/英文','ready':ready and bool(importlib.util.find_spec('sherpa_onnx'))}
    def start(self):
        with self.lock:
            self.sessions={k:v for k,v in self.sessions.items() if time.time()-v['at']<120}
            if len(self.sessions)>=4:raise ValueError('已有四个语音会话，请关闭不用的提词器')
            if not self.status()['ready']:raise ValueError('本地语音模型未就绪，请运行语音安装脚本')
            if self.recognizer is None:
                import sherpa_onnx
                self.recognizer=sherpa_onnx.OnlineRecognizer.from_transducer(tokens=str(self.root/'tokens.txt'),encoder=str(self.root/'encoder-epoch-99-avg-1.int8.onnx'),decoder=str(self.root/'decoder-epoch-99-avg-1.onnx'),joiner=str(self.root/'joiner-epoch-99-avg-1.int8.onnx'),num_threads=2,sample_rate=16000,feature_dim=80,enable_endpoint_detection=True,rule1_min_trailing_silence=1.8,rule2_min_trailing_silence=.8,rule3_min_utterance_length=30)
            id=uid('speech');self.sessions[id]={'stream':self.recognizer.create_stream(),'at':time.time(),'sequence':0}
            return {'id':id,'status':'ready'}
    def audio(self,data):
        import numpy as np
        with self.lock:
            s=self.sessions.get(data['id'])
            if not s:raise ValueError('语音会话已结束，请重新启动')
            if data.get('sequence')!=s['sequence']:raise ValueError('音频片段顺序错误，请重启语音跟随')
            rate=int(data['rate'])
            if rate not in (8000,16000,22050,24000,32000,44100,48000,96000):raise ValueError('不支持的采样率')
            raw=base64.b64decode(data['pcm'],validate=True)
            if len(raw)>rate*4*2:raise ValueError('音频块不能超过两秒')
            samples=np.frombuffer(raw,dtype='<f4').copy()
            if not np.isfinite(samples).all():raise ValueError('音频包含非法采样')
            s['stream'].accept_waveform(rate,samples)
            while self.recognizer.is_ready(s['stream']):self.recognizer.decode_stream(s['stream'])
            text=self.recognizer.get_result(s['stream']);endpoint=self.recognizer.is_endpoint(s['stream'])
            if endpoint:self.recognizer.reset(s['stream'])
            s.update(at=time.time(),sequence=s['sequence']+1)
            return {'text':text,'endpoint':endpoint,'sequence':s['sequence']}
    def stop(self,id):
        with self.lock:self.sessions.pop(id,None)
        return {'stopped':True}
