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

 def resource(self,rid,category='lora',base='sdxl'):
  path=self.root/(rid+'.safetensors');path.write_bytes(b'test only');self.s.studio.resources[rid]={'id':rid,'name':path.name,'path':str(path),'category':category,'selectable':True,'installations':['fixture'],'base':base};return self.s.studio.resources[rid]
 def styled(self):
  self.resource('alternate','checkpoint');self.resource('style');self.resource('clothes');p=self.params();p['sd'].update(checkpoint='alternate',style_lora='style',style_weight=.55,style_trigger='watercolor texture',lora='hero',clothes_lora='clothes');return p
 def test_character_checkpoint_style_reach_all_recipes_and_reload(self):
  p=self.styled();pack=self.save(p);self.assertEqual(self.s.studio.config['checkpoint'],'base');self.assertNotIn('member-02',self.s.studio.config['profiles'])
  for kind in ('portrait','pixel','both','cg'):
   r=self.s.studio.recipe('member-01',self.s.wardrobe.appearance('member-01'),'daily clothes',kind,{'scene':'cafe','place_name':'cafe','description':'quiet afternoon'} if kind=='cg' else None);self.assertEqual(r['checkpoint']['id'],'alternate');self.assertEqual([l['id'] for l in r['loras']],['hero','clothes','style']);self.assertEqual(r['loras'][2]['weight'],.55);self.assertIn('watercolor texture',r['profile']['identity'])
  with patch.object(CharacterStudio,'discover',lambda s,extra=None:s.state()),patch.object(CharacterStudio,'probe',lambda s:s.state()):restored=CharacterStudio(self.s.studio.root,self.s.studio.project)
  restored.closed=True;restored.thread.join(2);self.assertEqual(restored.config['profiles']['member-01']['style_lora'],'style');self.assertEqual(restored.config['profiles']['member-01']['checkpoint'],'alternate')
 def test_empty_overrides_preserve_legacy_recipe_and_binding(self):
  from lifebox.character_art import validate_binding
  self.save();old=copy.deepcopy(self.s.studio.config['profiles']['member-01']);new=validate_binding({**old,'checkpoint':'','style_lora':'','style_weight':.8,'style_trigger':''});self.assertEqual(new,old);r=self.s.studio.recipe('member-01',self.s.wardrobe.appearance('member-01'),'clothes','both');self.s.studio.config['profiles']['member-01']=new;self.assertEqual(r,self.s.studio.recipe('member-01',self.s.wardrobe.appearance('member-01'),'clothes','both'))
 def test_changed_model_or_style_does_not_reuse_old_pack(self):
  p=self.styled();pack=self.save(p);self.ready(pack,'both');self.ready(pack,'cg');self.s.art_atelier.pipeline.reconcile();p=self.params();p['sd']['style_weight']=.9;new=self.save(p);self.assertNotEqual(new['jobs']['both'],pack['jobs']['both']);self.assertNotEqual(new['jobs']['cg'],pack['jobs']['cg'])
 def test_bad_model_style_or_weight_rejected_without_mutation(self):
  for field,value in [('checkpoint','hero'),('style_lora','base'),('style_weight',True),('style_weight',float('nan')),('style_weight',1.6),('style_trigger','<lora:bad:1>'),('checkpoint','missing')]:
   p=self.params();p['sd'][field]=value;old=copy.deepcopy(self.s.studio.config);world=self.s.engine.journal()
   with self.assertRaises(ValueError):self.save(p)
   self.assertEqual(old,self.s.studio.config);self.assertEqual(world,self.s.engine.journal())
 def test_style_family_mismatch_blocks_render_but_saves_choice(self):
  p=self.styled();self.s.studio.resources['style']['base']='sd1.5';pack=self.save(p);self.assertEqual(pack['status'],'blocked');self.assertEqual(pack['jobs'],{});self.assertIn('不相容',pack['message']);self.assertEqual(self.s.studio.config['profiles']['member-01']['style_lora'],'style')
 def test_webui_request_uses_actor_model_and_three_separate_loras(self):
  import base64,io
  import lifebox.character_art as module
  pack=self.save(self.styled());r=self.s.studio.jobs[pack['jobs']['both']]['recipe'];r['api_models']=[{'filename':r['checkpoint']['path'],'title':'alternate model'}];r['api_loras']=[{'path':l['path'],'name':l['id']} for l in r['loras']];buf=io.BytesIO();Image.new('RGB',(16,16),'white').save(buf,format='PNG');captured=[]
  def reply(url,path,payload,**kw):captured.append(payload);return {'images':[base64.b64encode(buf.getvalue()).decode()]}
  with patch.object(module,'api',reply):self.s.studio._render(r,r['config']['templates']['portrait'],'watercolor portrait',1)
  out=captured[0];self.assertEqual(out['override_settings']['sd_model_checkpoint'],'alternate model');self.assertTrue(out['override_settings_restore_afterwards']);self.assertIn('<lora:hero:0.8>',out['prompt']);self.assertIn('<lora:clothes:0.6>',out['prompt']);self.assertIn('<lora:style:0.55>',out['prompt'])
 def test_native_comfy_missing_style_binding_blocks_preflight(self):
  p=self.styled();self.s.studio.config['backend']='comfyui';self.s.studio.config['native_selected']['portrait']='native';self.s.studio.native_templates['native']={'title':'mock native','output':'1','installation':'fixture','backend':'comfyui','bindings':{'lora':[], 'lora_weight':[]}}
  pack=self.save(p);self.assertEqual(pack['status'],'blocked');self.assertIn('畫風',pack['message']);self.assertEqual(pack['jobs'],{})
 def test_native_comfy_style_mapping_keeps_clothing_separate(self):
  import io
  import lifebox.character_art as module
  pack=self.save(self.styled());r=self.s.studio.jobs[pack['jobs']['both']]['recipe'];r['config']['backend']='comfyui';r['api_models']=['alternate.safetensors'];r['api_loras']=['hero.safetensors','clothes.safetensors','style.safetensors'];buf=io.BytesIO();Image.new('RGB',(16,16),'white').save(buf,format='PNG')
  t=copy.deepcopy(r['config']['templates']['portrait']);t['_native']={'backend':'comfyui','payload':{'1':{'inputs':{'role':'old','role_weight':0,'clothes':'old','clothes_weight':0,'style':'old','style_weight':0,'reference':'old','denoise':0}}},'bindings':{k:['/1/inputs/'+v] for k,v in {'lora':'role','lora_weight':'role_weight','clothes_lora':'clothes','clothes_weight':'clothes_weight','style_lora':'style','style_weight':'style_weight','reference':'reference','denoise':'denoise'}.items()},'output':'1'};captured=[]
  def reply(url,path,payload=None,**kw):
   if path=='/upload/image':return {'name':'reference.png'}
   if path=='/object_info':return {}
   if path=='/prompt':captured.append(payload['prompt']);return {'prompt_id':'mock'}
   return {'mock':{'outputs':{'1':{'images':[{'filename':'mock.png','subfolder':'','type':'output'}]}}}}
  class Response:
   def __enter__(self):return self
   def __exit__(self,*args):pass
   def read(self,*args):return buf.getvalue()
  with patch.object(module,'api',reply),patch.object(module.sd_templates,'validate'),patch.object(module.request,'build_opener') as opener:
   opener.return_value.open.return_value=Response();self.s.studio._render_native_comfy(r,t,'prompt','negative',1,None,None)
  i=captured[0]['1']['inputs'];self.assertEqual((i['role'],i['clothes'],i['style']),('hero.safetensors','clothes.safetensors','style.safetensors'));self.assertEqual((i['role_weight'],i['clothes_weight'],i['style_weight']),(.8,.6,.55));self.assertEqual(t['_native']['payload']['1']['inputs']['style'],'old')

 def test_cleared_style_zeros_native_webui_binding(self):
  import base64,io
  import lifebox.character_art as module
  pack=self.save();r=self.s.studio.jobs[pack['jobs']['both']]['recipe'];r['api_models']=[{'filename':r['checkpoint']['path'],'title':'base model'}];t=copy.deepcopy(r['config']['templates']['portrait']);t['_native']={'payload':{'alwayson_scripts':{'Style':{'args':[.9]}}},'bindings':{'style_weight':['/alwayson_scripts/Style/args/0']}};original=copy.deepcopy(t['_native']);buf=io.BytesIO();Image.new('RGB',(16,16),'white').save(buf,format='PNG');captured=[]
  def reply(url,path,payload,**kw):captured.append(payload);return {'images':[base64.b64encode(buf.getvalue()).decode()]}
  with patch.object(module,'api',reply):self.s.studio._render(r,t,'portrait',1)
  self.assertEqual(captured[0]['alwayson_scripts']['Style']['args'][0],0.0);self.assertEqual(t['_native'],original)

if __name__=='__main__':unittest.main()
