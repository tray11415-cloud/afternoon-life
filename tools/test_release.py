from pathlib import Path
import sys,copy,json,tempfile,unittest,threading,urllib.request,urllib.error
from unittest.mock import patch
source=Path(__file__).parent/'release-v19/prototype'
if not source.exists():source=Path(__file__).resolve().parents[1]/'prototype'
sys.path.insert(0,str(source))
from lifebox.pixel import PixelSession
from lifebox.play import make_server
from lifebox.demo_backend import DemoBackend
from lifebox.preferences import Preferences
from lifebox.character_art import CharacterStudio
from lifebox.speech import SpeechStudio
from lifebox.xai import XAIBackend

class ReleaseTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=Path(__file__).parent);self.root=Path(self.tmp.name)
  with patch.object(CharacterStudio,'discover',lambda s,extra=None:s.state()),patch.object(CharacterStudio,'probe',lambda s:s.state()),patch.object(SpeechStudio,'refresh_windows',lambda s:s.state()):self.s=PixelSession(self.root,DemoBackend(),clock=lambda:100)
 def tearDown(self):self.s.close();self.tmp.cleanup()
 def test_language_persists_without_rewriting_world_or_voice(self):
  before=self.s.engine.journal();voice=copy.deepcopy(self.s.speech.config);profiles=copy.deepcopy(self.s.character_setup.profiles)
  for language in ('en','ja','zh-TW'):self.s.preferences.configure({'language':language});self.assertEqual(Preferences(self.root).config['language'],language)
  self.assertEqual(self.s.engine.journal(),before);self.assertEqual(self.s.speech.config,voice);self.assertEqual(self.s.character_setup.profiles,profiles)
 def test_unknown_locale_and_extra_fields_rejected(self):
  for value in ({'language':'fr'},{'language':'en','api_key':'not-a-key'},{'language':['en']}):
   with self.assertRaises((ValueError,TypeError)):self.s.preferences.configure(value)
 def test_demo_dialogue_uses_selected_language_and_no_cloud_calls(self):
  actor='member-01';e=self.s.space.entities[actor];self.s.space.entities['player'].update(scene=e['scene'],x=e['x'],y=e['y']+1,path=[],destination=None)
  for language,fragment in [('en','park'),('ja','公園'),('zh-TW','公園')]:
   self.s.preferences.configure({'language':language});self.s._ai(actor,'玩家說話');event=next(e for e in reversed(self.s.engine._events) if e['kind']=='message_spoken');self.assertIn(fragment,event['data']['text']);self.s.engine.advance(2)
  self.assertEqual(self.s.backend.stats()['calls'],0);self.assertTrue(self.s.backend.stats()['demo'])
 def test_xai_language_and_gender_guidance_without_live_request(self):
  backend=XAIBackend('test-placeholder',self.root/'test-ledger.json',dialogue_model='grok-4.3');context=self.s.engine.view('member-01');context['self']['gender']='male';context['response_language']='ja';old=copy.deepcopy(context);captured=[]
  def respond(path,body):captured.append(body);return {'model':'grok-4.3','usage':{'prompt_tokens':1,'completion_tokens':1},'choices':[{'finish_reason':'stop','message':{'content':'{"kind":"wait","params":{}}'}}]}
  with patch.object(backend,'_request',respond):backend.decide(context,'自然な口調','玩家說話')
  text=captured[0]['messages'][0]['content'];self.assertIn('一位成年男性',text);self.assertIn('自然日文',text);self.assertEqual(context,old)
 def test_locale_catalogue_has_both_translations_and_protected_text(self):
  data=json.loads((source/'web/locales.json').read_text(encoding='utf-8'));self.assertGreater(len(data),700)
  for s in ('遊戲設定','人物設定','語音設定','替換預覽','保存生圖設定'):
   self.assertTrue(data[s]['en']);self.assertTrue(data[s]['ja'])
  script=(source/'web/i18n.js').read_text(encoding='utf-8');self.assertIn('data-user-content',script);self.assertIn('textarea',script);self.assertIn('.social-log',script)
 def test_preferences_http_contract_and_private_routes(self):
  server=make_server(self.s,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{server.server_port}'
  def req(path,body=None,token=None,origin=None):
   headers={};raw=None
   if token:headers['X-Play-Token']=token
   if body is not None:headers['Content-Type']='application/json';headers['Origin']=origin or base;raw=json.dumps(body).encode()
   with urllib.request.urlopen(urllib.request.Request(base+path,raw,headers),timeout=10) as r:return r.read()
  try:
   token=json.loads(req('/api/state'))['token']
   with self.assertRaises(urllib.error.HTTPError) as failure:req('/api/preferences')
   self.assertEqual(failure.exception.code,403)
   with self.assertRaises(urllib.error.HTTPError) as failure:req('/api/preferences',{'language':'en'},token,'https://example.com')
   self.assertEqual(failure.exception.code,403)
   self.assertEqual(json.loads(req('/api/preferences',{'language':'ja'},token))['config']['language'],'ja')
   self.assertTrue(req('/locales.json'));self.assertTrue(req('/i18n.js'));self.assertTrue(req('/assets/LPC-CREDITS.txt'))
   with self.assertRaises(urllib.error.HTTPError):req('/work/private/xai.dpapi')
  finally:server.shutdown();server.server_close()
 def test_English_and_Japanese_replacement_instructions(self):
  target='object:shared:bench';old=self.s.components.get(target)
  for instruction,text in [('description: A quiet bench','A quiet bench'),('説明：静かなベンチ','静かなベンチ')]:
   p=self.s.components.plan({'instruction':instruction,'targets':[target]});self.s.components.apply(p['id']);self.assertEqual(self.s.components.get(target)['description'],text)
   undo=self.s.components.rollback(p['id']);self.s.components.apply(undo['id']);self.assertEqual(self.s.components.get(target),old)
 def test_duplicate_listener_is_rejected(self):
  first=make_server(self.s,0)
  try:
   with self.assertRaises(OSError):make_server(self.s,first.server_port)
  finally:first.server_close()

if __name__=='__main__':unittest.main()
