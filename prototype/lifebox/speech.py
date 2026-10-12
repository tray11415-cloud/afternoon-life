"""Optional local speech, separate from world state, private memory and paid LLMs."""
from __future__ import annotations
import copy, hashlib, json, math, os, re, subprocess, threading
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, build_opener, ProxyHandler, HTTPRedirectHandler

from .neighborhood import NPCS
ACTORS={'player',*(f'member-{i:02d}' for i in range(1,11)),*NPCS}
DEFAULT={'enabled':False,'provider':'windows','endpoint':'http://127.0.0.1:8880',
         'model':'kokoro','auto':False,'speed':1.0,'pitch':1.0,'volume':0.8,'profiles':{},'language':'auto','language_mode':'voice'}
PREVIEW='你好，今天想一起去公園走走嗎？'
LANGUAGES={'auto':'跟隨聲線','zh-TW':'繁體中文','zh-CN':'普通話','en-US':'英語（美國）','en-GB':'英語（英國）','ja-JP':'日語','ko-KR':'韓語','es-ES':'西班牙語','fr-FR':'法語','it-IT':'義大利語','pt-BR':'葡萄牙語','hi-IN':'印地語'}
PREVIEWS={'en-US':'Hello. Would you like to visit the park together?','en-GB':'Hello. Would you like to visit the park together?','ja-JP':'こんにちは。今日は一緒に公園へ行きませんか。','ko-KR':'안녕하세요. 오늘 함께 공원에 갈까요?','es-ES':'Hola. ¿Vamos juntos al parque?','fr-FR':'Bonjour. Allons-nous au parc ensemble ?','it-IT':'Ciao. Andiamo al parco insieme?','pt-BR':'Olá. Vamos juntos ao parque?','hi-IN':'नमस्ते। क्या हम साथ में पार्क जाएँ?'}
KOKORO_LANG={'zh-TW':'z','zh-CN':'z','en-US':'a','en-GB':'b','ja-JP':'j','es-ES':'e','fr-FR':'f','it-IT':'i','pt-BR':'p','hi-IN':'h'}
LIMIT=12*1024*1024

class NoRedirect(HTTPRedirectHandler):
 def redirect_request(self,*args,**kwargs):raise ValueError('TTS 不允許轉址')

def endpoint(value):
 if not isinstance(value,str):raise ValueError('無效本機 TTS 地址')
 p=urlsplit(value)
 if p.scheme!='http' or p.hostname not in {'127.0.0.1','localhost','::1'} or p.username or p.password or p.query or p.fragment or p.path not in {'','/','/v1','/v1/'} or not p.port:
  raise ValueError('TTS 地址需為本機 HTTP 與連接埠，可附 /v1')
 return value.rstrip('/').removesuffix('/v1')

def identifier(value,empty=False):
 if not isinstance(value,str) or len(value)>200 or (not empty and not value.strip()) or any(ord(c)<32 for c in value):raise ValueError('無效模型或聲線名稱')
 return value.strip()

def validate(data):
 if not isinstance(data,dict) or set(data)-set(DEFAULT) or not (set(DEFAULT)-{'language','language_mode'})<=set(data):raise ValueError('無效語音設定')
 data={**DEFAULT,**data}
 if data['language'] not in LANGUAGES or data['language_mode'] not in {'voice','language','lang_code'}:raise ValueError('無效語音語言')
 result=copy.deepcopy(data)
 if data['provider'] not in {'windows','browser','kokoro','local'}:raise ValueError('未知 TTS 類型')
 for name in ('enabled','auto'):
  if type(data[name]) is not bool:raise ValueError('無效語音開關')
 for name,lo,hi in [('speed',0.5,2.0),('pitch',0.5,2.0),('volume',0,1)]:
  if type(data[name]) not in (int,float) or not math.isfinite(data[name]) or not lo<=data[name]<=hi:raise ValueError('語音數值超出範圍')
 result['endpoint']=endpoint(data['endpoint']);result['model']=identifier(data['model'])
 if not isinstance(data['profiles'],dict) or not set(data['profiles'])<=ACTORS:raise ValueError('未知語音角色')
 for p in data['profiles'].values():
  if not isinstance(p,dict) or set(p)!={'windows','browser','local'}:raise ValueError('無效角色聲線')
  for v in p.values():identifier(v,True)
 return result

def authorized_line(engine,event_id):
 # Resolve from authoritative events. Caller cannot supply another person's text.
 event=next((e for e in reversed(engine._events) if e['id']==event_id),None)
 if not event or event['kind'] not in {'message_spoken','group_spoken','city_spoken'} or 'player' not in event['audience'] or event['actor'] not in ACTORS:
  raise ValueError('這句話不在玩家可聽見的對話中')
 return event['actor'],event['data']['text']

class SpeechStudio:
 def __init__(self,root):
  self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True)
  self.cache=self.root/'audio';self.cache.mkdir(exist_ok=True)
  self.lock=threading.RLock();self.gate=threading.Semaphore(1)
  self.config=copy.deepcopy(DEFAULT);self.windows=[];self.voices=[];self.models=[];self.service='尚未檢查本機服務';self.windows_error=''
  self.catalog_endpoint=None
  try:self.config=validate(json.loads((self.root/'settings.json').read_text(encoding='utf-8')))
  except (OSError,ValueError,TypeError,KeyError):pass
  self.refresh_windows()

 def _windows(self,payload):
  if os.name!='nt':raise ValueError('此電腦沒有 Windows 語音')
  shell=Path(os.environ.get('SystemRoot','C:/Windows'))/'System32/WindowsPowerShell/v1.0/powershell.exe'
  proc=subprocess.run([str(shell),'-NoProfile','-NonInteractive','-ExecutionPolicy','Bypass','-File',str(Path(__file__).with_name('windows-speech.ps1'))],
   input=json.dumps(payload,ensure_ascii=False).encode('utf-8'),stdout=subprocess.PIPE,stderr=subprocess.PIPE,timeout=60,creationflags=subprocess.CREATE_NO_WINDOW)
  if proc.returncode:raise ValueError('Windows 語音暫時無法使用；請重新整理聲線')
  return proc.stdout.decode('utf-8-sig')

 def refresh_windows(self):
  try:self.windows=json.loads(self._windows({'operation':'voices'}))['voices'];self.windows_error=''
  except (OSError,ValueError,KeyError,subprocess.TimeoutExpired):self.windows=[];self.windows_error='Windows 聲線目前無法讀取'
  return self.state()

 def state(self):
  with self.lock:return {'config':copy.deepcopy(self.config),'windows':copy.deepcopy(self.windows),'windows_error':self.windows_error,
   'models':copy.deepcopy(self.models),'voices':copy.deepcopy(self.voices),'service':self.service,'catalog_endpoint':self.catalog_endpoint,
   'cache_files':len(list(self.cache.glob('*.wav'))),'preview':PREVIEWS.get(self.config['language'],PREVIEW),'languages':LANGUAGES}

 def configure(self,data):
  value=validate(data)
  with self.lock:
   if value['endpoint']!=self.config['endpoint']:self.models=[];self.voices=[];self.catalog_endpoint=None;self.service='地址已變更，請檢查服務'
   tmp=self.root/'settings.tmp';tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(tmp,self.root/'settings.json');self.config=value
  return self.state()

 def _request(self,base,path,payload=None):
  req=Request(endpoint(base)+path,data=json.dumps(payload,ensure_ascii=False).encode('utf-8') if payload is not None else None,
   headers={'Content-Type':'application/json'} if payload is not None else {})
  try:
   with build_opener(ProxyHandler({}),NoRedirect()).open(req,timeout=60 if payload else 5) as response:
    data=response.read(LIMIT+1)
    if len(data)>LIMIT:raise ValueError('TTS 回應過大')
    return data
  except OSError as exc:raise ValueError('本機 TTS 未連線或請求失敗；請確認服務與聲線') from exc

 def probe(self):
  base=self.config['endpoint'];models=[];voices=[]
  try:
   rows=json.loads(self._request(base,'/v1/audio/voices'))['voices']
   for v in rows[:300]:
    if isinstance(v,str):voices.append({'id':identifier(v),'name':v})
    elif isinstance(v,dict):voices.append({'id':identifier(v['id']),'name':str(v.get('name',v['id']))[:200]})
  except (ValueError,TypeError,KeyError):pass
  try:
   rows=json.loads(self._request(base,'/v1/models'))['data']
   models=[identifier(v['id']) for v in rows[:200] if isinstance(v,dict)]
  except (ValueError,TypeError,KeyError):pass
  with self.lock:
   self.models=models;self.voices=voices;self.catalog_endpoint=base
   self.service='已讀取服務目錄；仍需試聽驗證' if models or voices else '未讀取到目錄；可填入服務實際模型／聲線，再試聽'
  return self.state()

 def _trim(self):
  files=sorted(self.cache.glob('*.wav'),key=lambda p:p.stat().st_mtime,reverse=True);total=0
  for i,p in enumerate(files):
   total+=p.stat().st_size
   if i>=128 or total>256*1024*1024:p.unlink(missing_ok=True)

 def render(self,actor,text,preview=False):
  with self.lock:c=copy.deepcopy(self.config);voices=copy.deepcopy(self.windows)
  if actor not in ACTORS:raise ValueError('未知語音角色')
  if not preview and not c['enabled']:raise ValueError('請先啟用語音')
  if c['provider']=='browser':raise ValueError('瀏覽器聲線由前端播放')
  if not isinstance(text,str) or not text.strip() or len(text)>2400:raise ValueError('語音文字過長或空白')
  p=c['profiles'].get(actor,{})
  voice=p.get('windows' if c['provider']=='windows' else 'local','')
  if c['provider']=='windows':
   candidates=voices if c['language']=='auto' else [v for v in voices if v.get('lang','').split('-')[0]==c['language'].split('-')[0]]
   voice=voice or next((v['id'] for v in candidates if v.get('lang')==c['language']),candidates[0]['id'] if candidates else '')
   if not any(v['id']==voice for v in voices):raise ValueError('所選 Windows 聲線未安裝')
   if c['language']!='auto' and not any(v['id']==voice and v.get('lang','').split('-')[0]==c['language'].split('-')[0] for v in voices):raise ValueError('這個聲線不支援所選語言，請重新選擇聲線')
  elif not voice:raise ValueError('請為此角色選擇或填入本機模型的聲線 ID')
  key=hashlib.sha256(json.dumps([c['provider'],c['endpoint'],c['model'],voice,c['speed'],c['language'],c['language_mode'],text],ensure_ascii=False).encode()).hexdigest()
  target=self.cache/(key+'.wav')
  if target.exists():return {'audio':'/speech-audio/'+target.name,'cached':True,'voice':voice}
  if not self.gate.acquire(blocking=False):raise ValueError('正在生成另一句語音，請稍後試聽')
  try:
   temporary=self.cache/(key+'.part.wav')
   if c['provider']=='windows':
    self._windows({'operation':'render','voice':voice,'text':text,'rate':max(-10,min(10,round(math.log2(c['speed'])*5))),'output':str(temporary.resolve())})
    data=temporary.read_bytes()
   else:
    payload={'model':c['model'],'voice':voice,'input':text,'speed':c['speed'],'response_format':'wav'}
    if c['language']!='auto':
     if c['provider']=='kokoro':
      if c['language'] not in KOKORO_LANG:raise ValueError('Kokoro 不支援所選語言，請改選其他模型')
      payload['lang_code']=KOKORO_LANG[c['language']]
     elif c['language_mode']!='voice':payload[c['language_mode']]=c['language']
    data=self._request(c['endpoint'],'/v1/audio/speech',payload)
   if len(data)<44 or len(data)>LIMIT or data[:4]!=b'RIFF' or data[8:12]!=b'WAVE':raise ValueError('TTS 沒有回傳有效 WAV 音訊')
   temporary.write_bytes(data);os.replace(temporary,target);self._trim()
   return {'audio':'/speech-audio/'+target.name,'cached':False,'voice':voice}
  finally:
   if 'temporary' in locals():temporary.unlink(missing_ok=True)
   self.gate.release()

 def asset(self,name):
  if not re.fullmatch(r'[a-f0-9]{64}\.wav',name):return None
  p=self.cache/name
  return p if p.is_file() else None
