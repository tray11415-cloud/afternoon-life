from pathlib import Path
import copy,json,sys,tempfile,unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'prototype'))
from lifebox.pixel import PixelSession
from lifebox.character_art import CharacterStudio
from lifebox.speech import SpeechStudio
from lifebox.demo_backend import DemoBackend
from lifebox.character_pipeline import CharacterPipeline
from lifebox.model import digest
from PIL import Image

class CharacterPipelineTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
  with patch.object(CharacterStudio,'discover',lambda s,extra=None:s.state()),patch.object(CharacterStudio,'probe',lambda s:s.state()),patch.object(SpeechStudio,'refresh_windows',lambda s:s.state()):self.s=PixelSession(self.root,DemoBackend(),clock=lambda:100)
  self.s.art_atelier.pipeline.close();self.s.studio.closed=True;self.s.studio.thread.join(2)
  studio=self.s.studio;studio.folders=[{'id':'fixture','backend':'a1111','path':str(self.root)}]
  for rid,category in [('base','checkpoint'),('hero','lora')]:
   path=self.root/(rid+'.safetensors');path.write_bytes(b'test fixture');studio.resources[rid]={'id':rid,'name':path.name,'path':str(path),'category':category,'selectable':True,'installations':['fixture'],'base':'sdxl'}
  studio.configure({'installation':'fixture','backend':'a1111','checkpoint':'base','pixel_guide':'identity'});studio.services[studio.config['url']]={'ready':True,'models':[],'loras':[],'vaes':[]}
 def tearDown(self):self.s.close();self.temp.cleanup()
 def params(self,actor='member-01',mode='current'):
  state=self.s.art_atelier.state();p=copy.deepcopy(self.s.character_setup.current(self.s,actor) if mode=='current' else self.s.character_setup.profiles[actor]);p.update(name='測試角色'+actor,appearance='adult woman, dark hair, everyday clothes')
  return {'command':'save_character','actor':actor,'mode':mode,'profile':p,'before':state['atelier']['pipeline']['fingerprints' if mode=='current' else 'template_fingerprints'][actor],'sd':copy.deepcopy(state['config']['profiles'][actor]),'binding_before':state['atelier']['bindings'][actor],'scene':'cafe','description':'quiet afternoon'}
 def save(self,p=None):return self.s.art_atelier.operation(p or self.params())['atelier']['pipeline']['packs']['member-01']
 def ready(self,pack,kind):
  job=self.s.studio.jobs[pack['jobs'][kind]];prefix=job['id'];files={}
  if kind=='both':
   files={'sprite':prefix+'-sprite.png','portraits':{'neutral':prefix+'-portrait-neutral.png'}}
   for name in [files['sprite'],*files['portraits'].values()]:Image.new('RGBA',(192,256),'green').save(self.s.studio.assets/name)
  else:files={'cg':prefix+'-cg.png'};Image.new('RGB',(64,64),'green').save(self.s.studio.assets/files['cg'])
  job.update(status='ready',files=files,done=job['total'],message='mock pipeline fixture');return job
 def test_save_name_profile_and_prompt_only_queues_complete_pack(self):
  old=self.s.engine.journal();own=copy.deepcopy(self.s.engine._state['actors']['member-01']);pack=self.save();new=self.s.engine.journal();self.assertEqual(new['events'][:-1],old['events']);self.assertEqual(self.s.engine.tick,0)
  current=self.s.character_setup.current(self.s,'member-01');self.assertEqual(current['name'],'測試角色member-01');self.assertEqual(own['wallet'],self.s.engine._state['actors']['member-01']['wallet']);self.assertEqual(set(pack['jobs']),{'both','cg'});recipe=self.s.studio.jobs[pack['jobs']['both']]['recipe'];self.assertEqual(recipe['loras'],[]);self.assertEqual(recipe['profile']['identity'],current['appearance']);self.assertEqual(self.s.backend.stats()['calls'],0)
 def test_complete_outputs_auto_apply_without_new_world_events(self):
  pack=self.save();before=self.s.engine.journal();self.ready(pack,'both');self.ready(pack,'cg');self.s.art_atelier.pipeline.reconcile();pack=self.s.art_atelier.pipeline.packs['member-01'];self.assertEqual(pack['status'],'complete');self.assertTrue(self.s.art_atelier.prefers('member-01',self.s.wardrobe.appearance('member-01')));self.assertEqual(self.s.art_atelier.selected_cg()['actor'],'member-01');self.assertEqual(before,self.s.engine.journal());self.assertIn('sprite',self.s.studio.appearance('member-01',self.s.wardrobe.appearance('member-01')))
 def test_offline_saves_character_with_visible_block_and_retry(self):
  self.s.studio.services[self.s.studio.config['url']]['ready']=False;pack=self.save();self.assertEqual(pack['status'],'blocked');self.assertEqual(pack['jobs'],{});self.assertEqual(self.s.character_setup.current(self.s,'member-01')['name'],pack['name']);self.s.studio.services[self.s.studio.config['url']]['ready']=True;self.s.art_atelier.operation({'command':'retry_character','actor':'member-01','id':pack['id']});self.assertEqual(len(self.s.art_atelier.pipeline.packs['member-01']['jobs']),2)
 def test_bad_or_stale_save_leaves_world_and_sd_unchanged(self):
  for field,value in [('before','old'),('binding_before','old')]:
   p=self.params();p[field]=value;old=self.s.engine.journal();sd=copy.deepcopy(self.s.studio.config)
   with self.assertRaises(ValueError):self.save(p)
   self.assertEqual(old,self.s.engine.journal());self.assertEqual(sd,self.s.studio.config)
  p=self.params();p['profile']['age']=17
  with self.assertRaises(ValueError):self.save(p)
 def test_duplicate_name_rejected_before_sd_write(self):
  p=self.params();p['profile']['name']=self.s.character_setup.current(self.s,'member-02')['name'];old=copy.deepcopy(self.s.studio.config)
  with self.assertRaises(ValueError):self.save(p)
  self.assertEqual(old,self.s.studio.config)
 def test_background_and_look_fields_retained_without_sharing(self):
  p=self.params();p['profile'].update(background_enabled=True,background='private authored background',voice='quiet and practical',goal='open a flower shop');p['profile']['look'].update(enabled=True,hair='wavy',height=180);self.save(p);current=self.s.character_setup.current(self.s,'member-01');self.assertEqual(current['background'],p['profile']['background']);self.assertEqual(current['look'],p['profile']['look']);self.assertNotIn('private authored background',json.dumps(self.s.engine.view('member-02'),ensure_ascii=False))
 def test_inline_lora_resolves_exact_local_resource(self):
  p=self.params();p['profile']['appearance']+=' <lora:hero:0.75>';self.save(p);binding=self.s.studio.config['profiles']['member-01'];self.assertEqual(binding['lora'],'hero');self.assertEqual(binding['weight'],.75);self.assertNotIn('<lora:',binding['identity'])
 def test_missing_inline_lora_has_no_side_effects(self):
  p=self.params();p['profile']['appearance']+=' <lora:missing:0.75>';old=self.s.engine.journal()
  with self.assertRaises(ValueError):self.save(p)
  self.assertEqual(old,self.s.engine.journal())
 def test_changed_character_blocks_old_auto_application(self):
  pack=self.save();self.ready(pack,'both');self.ready(pack,'cg');p=self.s.character_setup.current(self.s,'member-01');p['appearance']='new identity';q=self.s.character_setup.prepare_current(self.s,'member-01',p,digest(self.s.character_setup.current(self.s,'member-01')));self.s.components.apply(q['id']);self.s.art_atelier.pipeline.reconcile();self.assertEqual(self.s.art_atelier.pipeline.packs['member-01']['status'],'stale');self.assertFalse(self.s.art_atelier.prefers('member-01',self.s.wardrobe.appearance('member-01')))
 def test_retry_retains_completed_outputs(self):
  pack=self.save();self.ready(pack,'both');self.s.studio.jobs[pack['jobs']['cg']].update(status='failed',message='mock error');self.s.art_atelier.pipeline.reconcile();old_both=pack['jobs']['both'];old_cg=pack['jobs']['cg'];self.s.art_atelier.operation({'command':'retry_character','actor':'member-01','id':pack['id']});new=self.s.art_atelier.pipeline.packs['member-01'];self.assertEqual(new['jobs']['both'],old_both);self.assertNotEqual(new['jobs']['cg'],old_cg)
 def test_cancel_does_not_cancel_another_actor(self):
  first=self.save();self.s.art_atelier.operation(self.params('member-02'));other=self.s.art_atelier.pipeline.packs['member-02'];self.s.art_atelier.operation({'command':'cancel_character','actor':'member-01','id':first['id']});self.assertEqual(self.s.art_atelier.pipeline.packs['member-01']['status'],'cancelled');self.assertTrue(all(not self.s.studio.jobs[j]['cancel'] for j in other['jobs'].values()))
 def test_template_save_does_not_change_world_or_render(self):
  old=self.s.engine.journal();result=self.s.art_atelier.operation(self.params(mode='template'));self.assertEqual(self.s.character_setup.profiles['member-01']['name'],'測試角色member-01');self.assertEqual(old,self.s.engine.journal());self.assertEqual(self.s.studio.jobs,{});self.assertEqual(result['atelier']['pipeline']['packs'],{})
 def test_pack_state_persists(self):
  pack=self.save();restored=CharacterPipeline(self.s.art_atelier);self.assertEqual(restored.packs['member-01']['id'],pack['id'])
 def test_name_only_save_reuses_complete_art(self):
  pack=self.save();self.ready(pack,'both');self.ready(pack,'cg');self.s.art_atelier.pipeline.reconcile();p=self.params();p['profile']['name']='新的名字';new=self.save(p);self.assertEqual(new['jobs'],pack['jobs']);self.assertEqual(new['status'],'complete');self.assertEqual(self.s.character_setup.current(self.s,'member-01')['name'],'新的名字')
 def test_full_queue_waits_and_resumes_automatically(self):
  self.s.studio.pending.extend(['unrelated']*12);pack=self.save();self.assertEqual(pack['status'],'waiting');self.s.studio.pending.clear();self.s.art_atelier.pipeline.reconcile();self.assertEqual(len(self.s.art_atelier.pipeline.packs['member-01']['jobs']),2)
 def test_new_game_saved_profile_build_does_not_write_world(self):
  self.s.art_atelier.operation(self.params(mode='template'));self.s.character_setup.initialize(self.s.engine);old=self.s.engine.journal();result=self.s.art_atelier.operation({'command':'build_saved_character','actor':'member-01'});self.assertEqual(old,self.s.engine.journal());self.assertEqual(len(result['atelier']['pipeline']['packs']['member-01']['jobs']),2)
 def test_restore_prevents_pending_automatic_reapplication(self):
  pack=self.save();self.s.art_atelier.operation({'command':'restore','actor':'member-01'});self.ready(pack,'both');self.ready(pack,'cg');self.s.art_atelier.pipeline.reconcile();self.assertEqual(self.s.art_atelier.pipeline.packs['member-01']['status'],'restored');self.assertFalse(self.s.art_atelier.prefers('member-01',self.s.wardrobe.appearance('member-01')))
 def test_name_only_save_without_sd_installation(self):
  self.s.studio.folders=[];self.s.studio.resources={};self.s.studio.config.update(installation='',checkpoint='');p=self.params();p['profile'].update(name='離線也能改名',appearance='');pack=self.save(p);self.assertEqual(self.s.character_setup.current(self.s,'member-01')['name'],'離線也能改名');self.assertEqual(pack['status'],'blocked');self.assertEqual(pack['jobs'],{})
 def test_adetailer_payload_follows_identity_without_changing_other_values(self):
  from lifebox.sd_templates import follow_adetailer
  payload={'alwayson_scripts':{'ADetailer':{'args':[True,False,{'ad_prompt':'old identity','ad_model':'face_yolov8n.pt','ad_negative_prompt':'keep this','ad_mask_blur':4}]}}};old=copy.deepcopy(payload);result=follow_adetailer(payload,'new identity, happy face');arg=result['alwayson_scripts']['ADetailer']['args'][2];self.assertEqual(arg['ad_prompt'],'new identity, happy face');self.assertEqual(arg['ad_model'],'face_yolov8n.pt');self.assertEqual(arg['ad_negative_prompt'],'keep this');self.assertEqual(arg['ad_mask_blur'],4);self.assertEqual(payload,old)
 def test_adetailer_png_info_preserves_quoted_commas_and_negative_prompt(self):
  from lifebox.sd_templates import follow_adetailer
  info='adult woman\nNegative prompt: bad anatomy\nSteps: 20, ADetailer model: face.pt, ADetailer prompt: "old identity, brown eyes", ADetailer negative prompt: "bad face, blurry", ADetailer prompt 2: "old second", Seed: 42';result=follow_adetailer({'infotext':info},'new identity, happy face')['infotext'];self.assertNotIn('old identity',result);self.assertNotIn('old second',result);self.assertEqual(result.count('new identity, happy face'),2);self.assertIn('ADetailer negative prompt: "bad face, blurry"',result);self.assertIn('Seed: 42',result);self.assertIn('ADetailer model: face.pt',result)
 def test_native_render_request_uses_unified_face_prompt(self):
  import base64,io
  import lifebox.character_art as module
  pack=self.save();recipe=self.s.studio.jobs[pack['jobs']['both']]['recipe'];self.assertTrue(recipe['follow_identity']);recipe['api_models']=[{'filename':self.s.studio.resources['base']['path'],'title':'base model'}];t=copy.deepcopy(recipe['config']['templates']['portrait']);t['_expression']='happy face';native={'payload':{'alwayson_scripts':{'ADetailer':{'args':[True,{'ad_prompt':'old person','ad_model':'face.pt','ad_mask_blur':6}]}},'steps':7},'bindings':{}};t['_native']=native;original=copy.deepcopy(native);buffer=io.BytesIO();Image.new('RGB',(16,16),'white').save(buffer,format='PNG');captured=[]
  def respond(url,path,payload,**kw):captured.append(payload);return {'images':[base64.b64encode(buffer.getvalue()).decode()]}
  with patch.object(module,'api',respond):self.s.studio._render(recipe,t,'full body portrait',123)
  arg=captured[0]['alwayson_scripts']['ADetailer']['args'][1];self.assertIn('dark hair',arg['ad_prompt']);self.assertIn('happy face',arg['ad_prompt']);self.assertNotIn('old person',arg['ad_prompt']);self.assertEqual(arg['ad_mask_blur'],6);self.assertEqual(captured[0]['steps'],7);self.assertEqual(native,original)

if __name__=='__main__':unittest.main()
