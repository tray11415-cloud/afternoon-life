from pathlib import Path
import copy,json,sys,tempfile,threading,unittest,urllib.request,urllib.error
from unittest.mock import patch
source=Path(__file__).resolve().parents[1]/'prototype'
sys.path.insert(0,str(source))
from lifebox.pixel import PixelSession
from lifebox.play import make_server
from lifebox.demo_backend import DemoBackend
from lifebox.preferences import Preferences
from lifebox.character_art import CharacterStudio,key
from lifebox.speech import SpeechStudio
from lifebox.looks import validate_look,default_look,look_prompt
from lifebox.xai import XAIBackend,AIError
from lifebox.model import digest
from PIL import Image

class AtelierTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.root=Path(self.tmp.name);self.now=100
  with patch.object(CharacterStudio,'discover',lambda s,extra=None:s.state()),patch.object(CharacterStudio,'probe',lambda s:s.state()),patch.object(SpeechStudio,'refresh_windows',lambda s:s.state()):self.s=PixelSession(self.root,DemoBackend(),clock=lambda:self.now)
 def tearDown(self):self.s.close();self.s.studio.thread.join(2);self.tmp.cleanup()
 def profile(self,actor='player'):
  p=self.s.character_setup.current(self.s,actor);p['look'].update(enabled=True,hair='long',hair_color='#7744aa',top_color='#aa3377',height=190,build='athletic');return p
 def apply(self,p,actor='player'):
  before=digest(self.s.character_setup.current(self.s,actor));q=self.s.character_setup.prepare_current(self.s,actor,p,before);self.s.components.apply(q['id']);return q
 def test_legacy_preferences_and_partial_language_preserve_display(self):
  self.s.preferences.configure({'camera_zoom':1.3,'show_names':False});self.s.preferences.configure({'language':'zh-CN'});self.assertEqual(Preferences(self.root).config,self.s.preferences.config);self.assertEqual(self.s.preferences.config['camera_zoom'],1.3)
  self.assertTrue(Preferences.validate({'language':'en'})['pause_in_settings'])
  for bad in ({'camera_zoom':True},{'camera_zoom':float('nan')},{'show_minimap':1},{'private_key':'x'}):
   with self.assertRaises(ValueError):self.s.preferences.configure(bad)
 def test_look_bounds_and_types(self):
  for changes in ({'height':149},{'height':True},{'hair':'unknown'},{'top_color':'red'},{'enabled':1},{'build':[]}):
   with self.assertRaises((ValueError,TypeError)):validate_look({**default_look(),**changes})
  self.assertIn('purple',look_prompt(self.profile()['look']))
 def test_preview_does_not_write_world_or_templates_and_images_are_real(self):
  journal=self.s.engine.journal();templates=copy.deepcopy(self.s.character_setup.profiles);p=self.profile();result=self.s.look_studio.preview('player',p)
  with Image.open(self.s.look_studio.asset(Path(result['sprite']).name)) as im:self.assertEqual(im.size,(576,256));self.assertIsNotNone(im.getbbox())
  self.assertEqual(journal,self.s.engine.journal());self.assertEqual(templates,self.s.character_setup.profiles);self.assertEqual(self.s.backend.stats()['calls'],0)
  p['look']['top_color']='#33aaff';self.assertNotEqual(result['sprite'],self.s.look_studio.preview('player',p)['sprite']);self.assertIsNone(self.s.look_studio.asset('../pixel-autosave.json'))
 def test_apply_rollback_and_old_profile_preserve_progress_and_look(self):
  old=self.s.character_setup.current(self.s,'player');own=copy.deepcopy(self.s.engine._state['actors']['player']);p=self.profile();q=self.apply(p)
  for field in ('wallet','inventory','location','relationships'):self.assertEqual(own.get(field),self.s.engine._state['actors']['player'].get(field))
  legacy=copy.deepcopy(p);legacy.pop('look');legacy['name']='New player';self.apply(legacy);self.assertEqual(self.s.character_setup.current(self.s,'player')['look'],p['look'])
  # The first proposal cannot be undone over a newer actor edit.
  with self.assertRaises(ValueError):self.s.components.rollback(q['id'])
  self.assertEqual(self.s.character_setup.current(self.s,'member-01')['look']['enabled'],False)
 def test_apply_then_rollback_restores_default_art(self):
  old=self.s.character_setup.current(self.s,'player');q=self.apply(self.profile());u=self.s.components.rollback(q['id']);self.s.components.apply(u['id']);self.assertEqual(old,self.s.character_setup.current(self.s,'player'))
 def test_ui_hold_does_not_save_or_advance(self):
  old=self.s.engine.journal();self.now+=1000;self.s.act({'command':'ui_hold','params':{}});self.s.act({'command':'pulse','params':{'focus':None}});self.assertEqual(old,self.s.engine.journal())
  with self.assertRaises(ValueError):self.s.act({'command':'ui_hold','params':{'tick':99}})
 def test_simplified_replacement_preserves_authored_description(self):
  target='object:shared:bench';q=self.s.components.plan({'instruction':'说明改成这里适合看书。','targets':[target]});self.s.components.apply(q['id']);self.assertEqual(self.s.components.get(target)['description'],'这里适合看书。')
 def test_sd_appearance_stale_look_is_hidden(self):
  p=self.profile();self.apply(p);outfit=self.s.wardrobe.appearance('player');self.s.screen();name='fixture-sprite.png';Image.new('RGBA',(192,256),'green').save(self.s.studio.assets/name)
  active={'sprite':name,'frames':3,'look_signature':key(p['look'])};self.s.studio.config['active']['player:'+outfit['render_key']]=active
  self.assertIn('sprite',self.s.studio.appearance('player',outfit));active['look_signature']='old'
  self.assertEqual(self.s.studio.appearance('player',outfit),{})
 def test_ai_draft_scope_and_accounting(self):
  b=XAIBackend('test-placeholder',self.root/'mock-ledger.json',dialogue_model='grok-4.3');p=self.profile();p['background']='disabled secret';captured=[]
  def respond(path,body):
   captured.append(body);return {'model':body['model'],'usage':{'prompt_tokens':50,'completion_tokens':20},'choices':[{'finish_reason':'stop','message':{'content':json.dumps({'goal':'静かな喫茶店を開く'})}}]}
  with patch.object(b,'_request',respond):result=b.draft_character(p,'one adult cafe owner','ja')
  user=json.loads(captured[0]['messages'][1]['content']);self.assertEqual(set(user),{'profile','brief'});self.assertEqual(user['profile']['background'],'');self.assertNotIn('actors',user);self.assertEqual(result['look'],p['look']);self.assertEqual(result['background'],'');self.assertEqual(b.stats()['calls'],1);self.assertEqual(b.stats()['successes'],1);self.assertEqual(captured[0]['model'],b.model)
 def test_ai_invalid_age_and_budget(self):
  b=XAIBackend('test-placeholder',self.root/'mock-ledger.json',max_calls=1)
  def respond(path,body):return {'model':body['model'],'usage':{'prompt_tokens':1,'completion_tokens':1},'choices':[{'finish_reason':'stop','message':{'content':'{"age":17}'}}]}
  with patch.object(b,'_request',respond):
   with self.assertRaisesRegex(AIError,'invalid_output'):b.draft_character(self.profile(),'adult')
   with self.assertRaisesRegex(AIError,'budget'):b.draft_character(self.profile(),'adult')
  self.assertEqual(b.stats()['calls'],1);self.assertEqual(b.stats()['failures'],1)
 def test_guarded_preview_and_offline_draft_http(self):
  server=make_server(self.s,0);thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start();base=f'http://127.0.0.1:{server.server_port}'
  def req(path,body=None,token=None,origin=None):
   headers={'X-Play-Token':token or ''};data=None
   if body is not None:headers.update({'Content-Type':'application/json','Origin':origin or base});data=json.dumps(body).encode()
   with urllib.request.urlopen(urllib.request.Request(base+path,data,headers),timeout=15) as r:return r.read()
  try:
   token=json.loads(req('/api/state'))['token'];body={'operation':'preview_look','actor':'player','profile':self.profile()}
   for kwargs in ({},{'token':token,'origin':'https://evil.example'}):
    with self.assertRaises(urllib.error.HTTPError) as e:req('/api/characters',body,**kwargs)
    self.assertEqual(e.exception.code,403)
   result=json.loads(req('/api/characters',body,token));self.assertTrue(req(result['sprite']));old=self.s.engine.journal();draft=json.loads(req('/api/characters',{**body,'operation':'draft','brief':'開一家咖啡廳'},token));self.assertEqual(draft['source'],'offline-example');self.assertFalse(draft['applied']);self.assertEqual(old,self.s.engine.journal())
   for path in ('/menu.js','/maker.js','/studio.css','/simplified.json'):self.assertTrue(req(path))
  finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main()
