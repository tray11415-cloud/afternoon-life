import copy,io,json,tempfile,threading,unittest,wave
from pathlib import Path
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from lifebox.speech import SpeechStudio,DEFAULT,PREVIEW,validate,endpoint,authorized_line
from lifebox.engine import Engine
from lifebox.play import play_world,make_server
from lifebox.model import Action

def wav():
 b=io.BytesIO()
 with wave.open(b,'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(16000);w.writeframes(b'\0\0'*1600)
 return b.getvalue()

def temporary():
 root=Path(__file__).resolve().parents[2]/'work';root.mkdir(exist_ok=True)
 return tempfile.TemporaryDirectory(dir=root)

class SpeechTests(unittest.TestCase):
 def setUp(self):
  self.tmp=temporary();self.patch=patch.object(SpeechStudio,'_windows',return_value=json.dumps({'voices':[{'id':'Hanhan','name':'Hanhan','lang':'zh-TW'}]}));self.patch.start();self.s=SpeechStudio(Path(self.tmp.name))
 def tearDown(self):self.patch.stop();self.tmp.cleanup()
 def enable(self):
  c=copy.deepcopy(DEFAULT);c['enabled']=True;c['provider']='local';c['profiles']={'member-01':{'windows':'Hanhan','browser':'','local':'voice-a'}};self.s.configure(c)
 def test_disabled_by_default_no_network_or_audio(self):
  self.assertFalse(self.s.config['enabled']);self.assertFalse(self.s.config['auto'])
  with self.assertRaises(ValueError):self.s.render('member-01','hi')
  self.assertEqual(list(self.s.cache.iterdir()),[])
 def test_model_settings_and_character_voices_survive_restart(self):
  self.enable();t=SpeechStudio(self.s.root);self.assertEqual(t.config['profiles']['member-01']['local'],'voice-a');self.assertEqual(t.config['model'],'kokoro')
 def test_local_address_only(self):
  for value in ['https://127.0.0.1:8880','http://example.com:80','http://127.0.0.1:80/private','http://user:pass@localhost:88','http://localhost:88?x=1','http://localhost:88#x']:
   with self.assertRaises(ValueError):endpoint(value)
  self.assertEqual(endpoint('http://127.0.0.1:8880/v1/'),'http://127.0.0.1:8880')
 def test_invalid_settings_do_not_replace_saved_choices(self):
  self.enable();before=copy.deepcopy(self.s.config)
  for field,value in [('speed',float('nan')),('volume',2),('enabled',1),('provider','cloud'),('profiles',{'stranger':{}})]:
   c=copy.deepcopy(before);c[field]=value
   with self.assertRaises(ValueError):self.s.configure(c)
   self.assertEqual(before,self.s.config)
 def test_private_line_cannot_be_spoken(self):
  engine=Engine(play_world());engine.dispatch('member-01',Action('say',{'target':'member-02','text':'私密訊息'}),'private')
  private=next(e['id'] for e in reversed(engine._events) if e['kind']=='message_spoken')
  with self.assertRaises(ValueError):authorized_line(engine,private)
  engine.advance()
  engine.dispatch('member-01',Action('say',{'target':'player','text':'玩家能聽到'}),'public')
  public=next(e['id'] for e in reversed(engine._events) if e['kind']=='message_spoken')
  self.assertEqual(authorized_line(engine,public),('member-01','玩家能聽到'))
 def test_non_dialogue_event_cannot_be_spoken(self):
  engine=Engine(play_world())
  with self.assertRaises(ValueError):authorized_line(engine,'event-00000001')
 def test_repeated_voice_uses_cache_and_changed_voice_regenerates(self):
  self.enable()
  with patch.object(self.s,'_request',return_value=wav()) as request:
   a=self.s.render('member-01','你好');b=self.s.render('member-01','你好');self.assertFalse(a['cached']);self.assertTrue(b['cached']);self.assertEqual(request.call_count,1)
   c=copy.deepcopy(self.s.config);c['profiles']['member-01']['local']='voice-b';self.s.configure(c);other=self.s.render('member-01','你好');self.assertNotEqual(a['audio'],other['audio']);self.assertEqual(request.call_count,2)
 def test_invalid_audio_not_cached(self):
  self.enable()
  with patch.object(self.s,'_request',return_value=b'<html>error</html>'):
   with self.assertRaises(ValueError):self.s.render('member-01','hi')
  self.assertEqual(list(self.s.cache.iterdir()),[])
 def test_busy_synthesis_does_not_queue_unbounded_work(self):
  self.enable();self.s.gate.acquire()
  try:
   with self.assertRaises(ValueError):self.s.render('member-01','hi')
  finally:self.s.gate.release()
 def test_asset_whitelist_and_cache_cap(self):
  for i in range(135):(self.s.cache/(f'{i:064x}'+'.wav')).write_bytes(wav())
  self.s._trim();self.assertEqual(len(list(self.s.cache.iterdir())),128)
  self.assertIsNone(self.s.asset('../settings.json'));self.assertIsNone(self.s.asset('0'*64+'.part.wav'))
 def test_no_voice_binding_no_fake_voice(self):
  self.enable()
  with self.assertRaises(ValueError):self.s.render('member-02','hi')

class LocalSpeechContractTests(unittest.TestCase):
 def test_real_http_discovery_speech_auth_and_cache(self):
  calls=[]
  class Handler(BaseHTTPRequestHandler):
   def log_message(self,*a):pass
   def do_GET(self):
    data={'voices':[{'id':'zf_fixture','name':'測試聲線'}]} if self.path=='/v1/audio/voices' else {'data':[{'id':'fixture-tts'}]}
    body=json.dumps(data).encode();self.send_response(200);self.send_header('Content-Length',str(len(body)));self.end_headers();self.wfile.write(body)
   def do_POST(self):
    calls.append(json.loads(self.rfile.read(int(self.headers['Content-Length']))));body=wav();self.send_response(200);self.end_headers();self.wfile.write(body)
  server=ThreadingHTTPServer(('127.0.0.1',0),Handler);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
  try:
   with temporary() as tmp,patch.object(SpeechStudio,'_windows',return_value='{"voices":[]}'):
    s=SpeechStudio(Path(tmp));c=copy.deepcopy(DEFAULT);c.update(enabled=True,provider='local',endpoint=f'http://127.0.0.1:{server.server_port}',model='fixture-tts',profiles={'member-01':{'windows':'','browser':'','local':'zf_fixture'}});s.configure(c)
    self.assertEqual(s.probe()['models'],['fixture-tts']);a=s.render('member-01',PREVIEW);self.assertTrue(s.asset(a['audio'].split('/')[-1]));self.assertEqual(calls[0],{'model':'fixture-tts','voice':'zf_fixture','input':PREVIEW,'speed':1.0,'response_format':'wav'})
    self.assertTrue(s.render('member-01',PREVIEW)['cached']);self.assertEqual(len(calls),1)
  finally:server.shutdown();server.server_close();thread.join()

if __name__=='__main__':unittest.main()
