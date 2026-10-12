from pathlib import Path
import sys,unittest,tempfile,json,copy,base64,io
from unittest.mock import patch
from PIL import Image
source=Path(__file__).parent/'life-upgrade/prototype'
if not source.is_dir():source=Path(__file__).resolve().parents[1]/'prototype'
sys.path.insert(0,str(source))
from lifebox.pixel import PixelSession
from lifebox.engine import Engine
from lifebox.model import Action
from lifebox.neighborhood import NPCS
from lifebox.character_art import CharacterStudio,TEMPLATES,key
from lifebox import speech
from tests.test_play import FakeBackend

class PairBackend(FakeBackend):
 def decide(self,context,profile,trigger):
  self.contexts.append(copy.deepcopy(context));target=context['conversation_target']['id'];return Action('say',{'target':target,'text':'今天這裡很熱鬧，想一起逛逛嗎？'})
class TownTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).parent);self.root=Path(self.temp.name);self.backend=PairBackend()
  with patch.object(CharacterStudio,'discover',lambda s,extra=None:s.state()),patch.object(CharacterStudio,'probe',lambda s:s.state()),patch.object(speech.SpeechStudio,'refresh_windows',lambda s:s.state()):self.s=PixelSession(self.root,self.backend,clock=lambda:100)
 def tearDown(self):self.s.close();self.temp.cleanup()
 def at(self,actor,venue,x,y):
  previous=self.s.engine._state['actors'][actor]['location']
  if previous!=venue:self.s.engine._emit('actor_moved',actor,{'from':previous,'to':venue},[],remember=False)
  self.s.engine._state['actors'][actor].update(location=venue,busy_until=0,activity='idle');self.s.space.entities[actor].update(scene=venue,x=x,y=y,path=[],destination=None)
 def test_defaults_and_no_background_model_calls(self):
  self.assertEqual(self.s.screen()['player']['gender'],'male');self.assertEqual(len(self.s.screen()['town']['npcs']),6);self.assertFalse(self.s.screen()['town']['policy']['auto_ai'])
  for _ in range(20):self.s._native_step()
  self.assertEqual(self.backend.contexts,[])
 def test_npcs_have_independent_private_views(self):
  self.assertEqual(len(self.s.engine.agent_ids()),10);self.assertNotIn('npc-cafe',self.s.engine.agent_ids());self.assertEqual(self.s.engine.view('npc-cafe')['self']['role'],'npc')
  self.s.engine._emit('message_spoken','npc-cafe',{'text':'私人資料','target':'member-01'},['npc-cafe','member-01'])
  self.assertFalse(any(e['data'].get('text')=='私人資料' for e in self.s.engine.view('member-02')['memories']))
 def test_recurrence_and_reload_not_duplicate_event(self):
  self.s.engine.advance(180);active=self.s.neighborhood.active();self.assertTrue(any(e['title']=='河岸小祭典' for e in active));count=len([e for e in self.s.engine._events if e['kind']=='city_event_opened']);self.s.neighborhood.clock();self.assertEqual(count,len([e for e in self.s.engine._events if e['kind']=='city_event_opened']))
  self.s._save();self.s._load_pixel(self.s.auto_path);self.assertEqual(count,len([e for e in self.s.engine._events if e['kind']=='city_event_opened']))
  self.s.engine.advance(180);self.assertFalse(any(e['id']=='river-festival-0' for e in self.s.neighborhood.active()))
 def test_pool_requires_swimwear_for_walk_and_action(self):
  self.at('player','pool',8,8);self.assertFalse(self.s.space.step('player','right'));self.assertFalse(self.s.space.walk_to('player',12,8))
  self.assertFalse(self.s._do('player',Action('pool_swim',{})).accepted)
 def test_locker_cost_and_swimming_completion(self):
  self.at('player','pool',5,14);wallet=self.s.engine._state['actors']['player']['wallet'];previous=self.s.wardrobe.appearance('player')['id'];self.s.neighborhood.change_swimwear('player')
  self.assertEqual(self.s.engine._state['actors']['player']['wallet'],wallet-12);self.assertEqual(self.s.wardrobe.appearance('player')['id'],'swim-trunks')
  self.at('player','pool',12,8);self.s.neighborhood.swim('player');self.s.engine.advance(15)
  self.assertTrue(any(e['kind']=='venue_completed' and e['data']['item']=='pool-swim' for e in self.s.engine.view('player',100)['memories']))
  self.at('player','district',3,18);self.s.neighborhood.clock();self.assertEqual(self.s.wardrobe.appearance('player')['id'],previous)
 def test_no_charge_when_change_not_at_locker_or_no_money(self):
  self.at('player','pool',2,2);wallet=self.s.engine._state['actors']['player']['wallet']
  with self.assertRaises(ValueError):self.s.neighborhood.change_swimwear('player')
  self.assertEqual(wallet,self.s.engine._state['actors']['player']['wallet']);self.at('player','pool',5,14);self.s.engine._state['actors']['player']['wallet']=0
  with self.assertRaises(ValueError):self.s.neighborhood.change_swimwear('player')
 def test_scripted_dialogue_does_not_call_model(self):
  npc=self.s.space.entities['npc-cafe'];self.at('player','cafe',npc['x']-1,npc['y']);self.s.act({'command':'talk','params':{'target':'npc-cafe','text':'你好'}})
  self.assertEqual(self.backend.contexts,[]);self.assertTrue(any(e['actor']=='npc-cafe' and e['kind']=='message_spoken' for e in self.s.engine.view('player')['memories']))
 def test_two_ai_contexts_are_separate_and_observed(self):
  self.at('player','shared',18,17);self.at('member-01','shared',18,16);self.at('member-02','shared',19,16);self.s._town_pair('member-01','member-02')
  self.assertEqual([c['self']['id'] for c in self.backend.contexts],['member-01','member-02']);self.assertTrue(any(e['kind']=='city_spoken' for e in self.s.engine.view('player')['memories']))
  for c in self.backend.contexts:self.assertNotIn('actors',c)
 def test_ai_and_npc_one_model_call(self):
  self.at('player','cafe',10,10);self.at('member-01','cafe',11,10);self.at('npc-cafe','cafe',12,10);self.s._town_pair('member-01','npc-cafe');self.assertEqual(len(self.backend.contexts),1)
  self.assertTrue(any(e['kind']=='city_spoken' and e['data']['provider']=='scripted' for e in self.s.engine.view('player')['memories']))
 def test_far_pair_rejected_before_model(self):
  with self.assertRaises(ValueError):self.s._town_pair('member-01','member-09')
  self.assertEqual(self.backend.contexts,[])
 def test_auto_limit_one_speaker_per_turn(self):
  self.at('member-01','shared',18,16);self.at('member-02','shared',19,16);self.s.neighborhood.policy({'auto_ai':True,'interval':30,'daily_limit':1});self.s._auto_town_pair();count=len(self.backend.contexts);self.s.engine.advance(40);self.s._auto_town_pair();self.assertEqual(len(self.backend.contexts),count);self.assertEqual(count,1)
 def test_save_keeps_npcs_pool_outfit_and_original_genesis(self):
  genesis=copy.deepcopy(self.s.engine.journal()['genesis']);self.at('player','pool',5,14);self.s.neighborhood.change_swimwear('player');self.s._save();self.s._load_pixel(self.s.auto_path)
  self.assertEqual(self.s.engine.journal()['genesis'],genesis);self.assertEqual(self.s.wardrobe.appearance('player')['id'],'swim-trunks');self.assertEqual(len(self.s.space.entities),17)
 def png(self,size):
  buf=io.BytesIO();Image.new('RGBA',size,'#416383').save(buf,format='PNG');return base64.b64encode(buf.getvalue()).decode()
 def test_art_upload_outfit_scope_and_restore(self):
  before=copy.deepcopy(self.s.engine.journal());outfit=self.s.wardrobe.appearance('player');p={'kind':'portrait','target':'player','expression':'happy','scope':'outfit','frames':9,'image':self.png((128,256)),'hide_decor':False}
  self.s.art_assets.upload(p,self.s);self.assertIn('portrait',self.s.art_assets.appearance('player',outfit,'happy'));self.assertNotIn('portrait',self.s.art_assets.appearance('player',{'render_key':'other'},'happy'));self.assertEqual(before,self.s.engine.journal())
  slot=next(iter(self.s.art_assets.entries));self.s.art_assets.remove(slot);self.assertEqual(self.s.art_assets.appearance('player',outfit,'happy'),{})
 def test_art_size_validation_and_asset_paths(self):
  p={'kind':'sprite','target':'player','expression':'neutral','scope':'all','frames':9,'image':self.png((192,256)),'hide_decor':False}
  with self.assertRaises(ValueError):self.s.art_assets.upload(p,self.s)
  self.assertIsNone(self.s.art_assets.asset('../settings.json'))
 def test_background_exact_dimensions(self):
  p={'kind':'background','target':'pool','expression':'neutral','scope':'all','frames':9,'image':self.png((896,640)),'hide_decor':True};self.s.art_assets.upload(p,self.s);self.assertTrue(self.s.art_assets.backgrounds()['pool']['hide_decor'])

class LanguageTests(unittest.TestCase):
 def test_old_settings_migrate_without_enable(self):
  c={k:v for k,v in copy.deepcopy(speech.DEFAULT).items() if k not in {'language','language_mode'}};r=speech.validate(c);self.assertEqual(r['language'],'auto');self.assertFalse(r['enabled'])
 def test_unknown_language_rejected(self):
  c=copy.deepcopy(speech.DEFAULT);c['language']='unknown'
  with self.assertRaises(ValueError):speech.validate(c)
 def test_kokoro_codes_and_preview(self):
  self.assertEqual(speech.KOKORO_LANG['ja-JP'],'j');self.assertEqual(speech.KOKORO_LANG['en-US'],'a');self.assertIn('こんにちは',speech.PREVIEWS['ja-JP'])
 def test_local_language_sent_and_cache_language_scoped(self):
  import wave
  buf=io.BytesIO()
  with wave.open(buf,'wb') as w:w.setnchannels(1);w.setsampwidth(2);w.setframerate(22050);w.writeframes(b'\0\0'*100)
  with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root,patch.object(speech.SpeechStudio,'refresh_windows',lambda s:s.state()):
   s=speech.SpeechStudio(root);c=copy.deepcopy(speech.DEFAULT);c.update(enabled=True,provider='kokoro',language='ja-JP',profiles={'player':{'windows':'','browser':'','local':'jf_alpha'}});s.configure(c);captured=[]
   s._request=lambda base,path,payload:(captured.append(payload) or buf.getvalue());first=s.render('player','こんにちは');self.assertEqual(captured[0]['lang_code'],'j');self.assertTrue(s.render('player','こんにちは')['cached'])
   c['language']='en-US';s.configure(c);second=s.render('player','こんにちは');self.assertNotEqual(first['audio'],second['audio']);self.assertEqual(captured[-1]['lang_code'],'a')
 def test_windows_wrong_language_fails_before_synthesis(self):
  with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as root,patch.object(speech.SpeechStudio,'refresh_windows',lambda s:s.state()):
   s=speech.SpeechStudio(root);s.windows=[{'id':'Hanhan','lang':'zh-TW'}];c=copy.deepcopy(speech.DEFAULT);c.update(enabled=True,language='en-US',profiles={'player':{'windows':'Hanhan','browser':'','local':''}});s.configure(c)
   with self.assertRaisesRegex(ValueError,'語言'):s.render('player','hello')

class PortraitTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).parent);self.root=Path(self.temp.name)
  with patch.object(CharacterStudio,'discover',lambda s,extra=None:s.state()),patch.object(CharacterStudio,'probe',lambda s:s.state()):self.s=CharacterStudio(self.root)
  self.s.closed=True;self.s.thread.join(2);self.s.closed=False;self.s.folders=[{'id':'f','backend':'a1111','path':str(self.root)}]
  self.s.resources={}
  for ident,category,name in [('c','checkpoint','base'),('l','lora','person'),('sw','lora','sport-swimsuit')]:
   path=self.root/(name+'.safetensors');path.write_bytes(b'x');self.s.resources[ident]={'id':ident,'category':category,'name':path.name,'path':str(path),'selectable':True,'installations':['f'],'base':'sdxl'}
  self.s.configure({'installation':'f','backend':'a1111','checkpoint':'c','pixel_guide':'identity','auto':False,'remove_background':False,'expressions':['neutral'],'profiles':{'player':{'identity':'short brown hair','trigger':'hero','lora':'l','weight':.8,'clothes_lora':'','clothes_weight':.6,'seed':123,'auto':False,'expression':'neutral'}}})
  self.s.services[self.s.config['url']]={'ready':True,'models':[],'loras':[],'vaes':[]};self.outfit={'id':'coat','title':'外套','render_key':'outfit-coat'};self.calls=[]
  b=io.BytesIO();Image.new('RGB',(256,320),'#416383').save(b,format='PNG');raw=b.getvalue()
  self.s._render=lambda recipe,t,prompt,seed,*a,**kw:(self.calls.append((prompt,seed)) or raw)
 def tearDown(self):self.s.closed=True;self.temp.cleanup()
 def generate(self,kind='portrait',scene=None):
  j=self.s.submit('player',self.outfit,'opaque navy coat',kind,scene);job=self.s.jobs[j['id']];self.s._generate(job);job['status']='ready';return job
 def test_library_only_portraits_and_reused_for_cg(self):
  self.generate();self.assertEqual(len(self.calls),1);self.assertEqual(len(self.s.portrait_library),1)
  j=self.generate('cg',{'scene':'park','place_name':'公園','description':'a sunny public park'});self.assertEqual(len(self.calls),2);self.assertEqual(j['reused_portraits'],1);self.assertTrue(all(e['expression']=='neutral' for e in self.s.portrait_library.values()))
  self.assertTrue(self.calls[0][0].startswith('high quality'));self.assertIn('adult man',self.calls[0][0]);self.assertNotIn('adult woman',self.calls[0][0])
 def test_new_expression_reuses_existing_neutral(self):
  self.generate();self.s.config['expressions']=['neutral','happy'];job=self.generate();self.assertEqual(len(self.calls),2);self.assertEqual(job['reused_portraits'],1);self.assertEqual(len(self.s.portrait_library),2)
 def test_outfit_or_identity_changes_do_not_reuse(self):
  self.generate();self.outfit={**self.outfit,'render_key':'other-outfit'};self.generate();self.assertEqual(len(self.calls),2)
  self.s.config['profiles']['player']['identity']='short black hair';self.generate();self.assertEqual(len(self.calls),3)
 def test_swimwear_requires_clothing_lora_and_adds_it(self):
  swimsuit={**self.outfit,'id':'swim-trunks','render_key':'swim-trunks'}
  with self.assertRaisesRegex(ValueError,'泳池生圖'):self.s.recipe('player',swimsuit,'athletic swim trunks','portrait')
  self.s.configure({'outfit_loras':{'swim-trunks':{'lora':'sw','weight':.6,'trigger':'athletic swimming clothes'}}});r=self.s.recipe('player',swimsuit,'athletic swim trunks','portrait');self.assertEqual(r['loras'][1]['id'],'sw');self.assertTrue(r['swim'])
 def test_cg_requested_twice_is_not_library_cache(self):
  scene={'scene':'park','place_name':'公園','description':'a sunny public park'};a=self.generate('cg',scene);b=self.generate('cg',scene);self.assertNotEqual(a['id'],b['id']);self.assertEqual(len(self.calls),3)

if __name__=='__main__':unittest.main()
