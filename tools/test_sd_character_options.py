"""Request-level tests: no real GPU render, paid request or native UI changes."""
import base64,copy,io,json,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'prototype'))
from test_character_pipeline import CharacterPipelineTests as Fixture
from lifebox import character_art as module,sd_options
from lifebox.character_art import validate_binding
from PIL import Image

class AdvancedTests(unittest.TestCase):
 setUp=Fixture.setUp;tearDown=Fixture.tearDown;params=Fixture.params;save=Fixture.save;resource=Fixture.resource
 def advanced(self):
  self.resource('refine','checkpoint');self.resource('style');self.resource('line')
  self.s.studio.services[self.s.studio.config['url']].update(advanced_fields=['refiner_checkpoint','refiner_switch_at','enable_hr'],upscalers=['Lanczos','Nearest'],samplers=['Euler'],adetailer_models=['face.pt','hand.pt'],adetailer_slots=4,scripts={'txt2img':['adetailer']})
  p=self.params();p['sd'].update(style_lora='style',style_weight=.6,style_trigger='watercolor',style_loras=[{'lora':'line','weight':.3,'trigger':'ink lines','enabled':True}],render_options=copy.deepcopy(sd_options.DEFAULTS))
  p['sd']['render_options']['refiner'].update(mode='on',checkpoint='refine',switch=.75)
  p['sd']['render_options']['hires'].update(mode='on',denoise=.25,scale=1.5)
  p['sd']['render_options']['adetailer'].update(mode='on',passes=[{**copy.deepcopy(sd_options.AD_DEFAULT),'model':model,'prompt':'detailed face','parameters':{'ad_clip_skip':2,'ad_use_clip_skip':True}} for model in ('face.pt','hand.pt')])
  return p
 def recipe(self,p=None):
  pack=self.save(p or self.advanced());self.assertEqual(pack['status'],'running');r=self.s.studio.jobs[pack['jobs']['both']]['recipe'];r['api_models']=[{'filename':res['path'],'title':res['id']+' model'} for res in self.s.studio.resources.values() if res['category']=='checkpoint'];r['api_loras']=[{'path':l['path'],'name':l['id']} for l in r['loras']];return r
 def render(self,r,reference=None,t=None):
  buf=io.BytesIO();Image.new('RGB',(64,64),'white').save(buf,format='PNG');calls=[]
  def reply(url,path,payload,**kw):calls.append((path,copy.deepcopy(payload)));return {'images':[base64.b64encode(buf.getvalue()).decode()]}
  with patch.object(module,'api',reply):self.s.studio._render(r,t or {**r['config']['templates']['portrait'],'_kind':'portrait','_expression':'happy smile'},'portrait',123,reference)
  return calls,buf.getvalue()
 def test_multi_styles_capture_order_weight_prompt_and_disabled(self):
  p=self.advanced();p['sd']['style_loras'].append({'lora':'hero','weight':.7,'trigger':'unused trigger','enabled':False});r=self.recipe(p);self.assertEqual([l['id'] for l in r['loras']],['style','line']);self.assertEqual([l['weight'] for l in r['loras']],[.6,.3]);self.assertIn('ink lines',r['profile']['identity']);self.assertNotIn('unused trigger',r['profile']['identity'])
 def test_unmodified_defaults_preserve_old_binding(self):
  p=self.params()['sd'];self.assertEqual(validate_binding(p),validate_binding({**p,'style_loras':[],'render_options':copy.deepcopy(sd_options.DEFAULTS)}))
 def test_webui_request_refiner_hires_two_ad_passes(self):
  r=self.recipe();calls,_=self.render(r);self.assertEqual(len(calls),1);path,out=calls[0];self.assertEqual(path,'/sdapi/v1/txt2img');self.assertEqual(out['refiner_checkpoint'],'refine model');self.assertEqual(out['refiner_switch_at'],.75);self.assertTrue(out['enable_hr']);self.assertEqual(out['hr_scale'],1.5);self.assertEqual(out['hr_second_pass_steps'],20);self.assertIn('<lora:line:0.3>',out['hr_prompt']);args=out['alwayson_scripts']['adetailer']['args'];self.assertEqual(args[:2],[True,False]);self.assertEqual([a['ad_model'] for a in args[2:] if a.get('ad_tab_enable')],['face.pt','hand.pt']);self.assertIn('happy smile',args[2]['ad_prompt']);self.assertIn('ink lines',args[2]['ad_prompt']);self.assertEqual(args[2]['ad_clip_skip'],2);self.assertTrue(out['override_settings_restore_afterwards'])
 def test_img2img_hires_really_runs_second_pass_with_final_ad(self):
  r=self.recipe();calls,raw=self.render(r,b'identity reference');self.assertEqual([p for p,_ in calls],['/sdapi/v1/img2img','/sdapi/v1/img2img']);first,final=[o for _,o in calls];self.assertFalse(first['enable_hr']);self.assertFalse(first['alwayson_scripts']['adetailer']['args'][0]);self.assertEqual(first['denoising_strength'],r['config']['templates']['portrait']['denoise']);self.assertEqual(final['denoising_strength'],.25);self.assertTrue(final['alwayson_scripts']['adetailer']['args'][0]);image=Image.open(io.BytesIO(base64.b64decode(final['init_images'][0])));self.assertEqual(image.size,(final['width'],final['height']));self.assertEqual(final['seed'],123)
 def test_off_really_overrides_native_on_without_modifying_template(self):
  p=self.advanced()
  for name in p['sd']['render_options']:p['sd']['render_options'][name]['mode']='off'
  r=self.recipe(p);t={**r['config']['templates']['portrait'],'_kind':'portrait','_native':{'payload':{'refiner_checkpoint':'old','enable_hr':True,'alwayson_scripts':{'ADetailer':{'args':[True,False,{'ad_model':'face.pt'}]},'FreeU':{'args':[True]}}},'bindings':{}}};old=copy.deepcopy(t);calls,_=self.render(r,t=t);out=calls[0][1];self.assertIsNone(out['refiner_checkpoint']);self.assertFalse(out['enable_hr']);self.assertFalse(out['alwayson_scripts']['ADetailer']['args'][0]);self.assertEqual(out['alwayson_scripts']['FreeU'],old['_native']['payload']['alwayson_scripts']['FreeU']);self.assertEqual(t,old)
 def test_pixel_untargeted_keeps_native_parameters(self):
  r=self.recipe();t={**r['config']['templates']['pixel'],'_kind':'pixel','_native':{'payload':{'enable_hr':True,'hr_scale':1.2},'bindings':{}}};calls,_=self.render(r,t=t);self.assertEqual(calls[0][1]['hr_scale'],1.2);self.assertNotIn('refiner_checkpoint',calls[0][1])
 def test_inherit_keeps_native_quality_parameters(self):
  p=self.advanced()
  for name in p['sd']['render_options']:p['sd']['render_options'][name]['mode']='inherit'
  r=self.recipe(p);t={**r['config']['templates']['portrait'],'_native':{'payload':{'enable_hr':True,'hr_scale':1.2,'refiner_checkpoint':'native model'},'bindings':{}}};calls,_=self.render(r,t=t);self.assertEqual(calls[0][1]['hr_scale'],1.2);self.assertEqual(calls[0][1]['refiner_checkpoint'],'native model')
 def test_bad_options_no_world_or_binding_write(self):
  for name,key,value in [('refiner','switch',1.1),('hires','scale',3),('hires','denoise',float('nan')),('hires','steps',True),('refiner','targets',['secret']),('adetailer','passes',[{'model':'face.pt','parameters':{'api_key':'forbidden'}}]),('adetailer','passes',[{'model':'face.pt','parameters':{'ad_clip_skip':0}}]),('adetailer','passes',[{'model':'face.pt','parameters':{'ad_noise_multiplier':.2}}]),('adetailer','passes',[{'model':'face.pt','parameters':{'ad_mask_max_ratio':1.2}}])]:
   p=self.advanced();p['sd']['render_options'][name][key]=value;old=copy.deepcopy(self.s.studio.config);world=self.s.engine.journal()
   with self.assertRaises(ValueError):self.save(p)
   self.assertEqual(old,self.s.studio.config);self.assertEqual(world,self.s.engine.journal())
 def test_unavailable_plugins_block_before_queue(self):
  p=self.advanced();self.s.studio.services[self.s.studio.config['url']]['adetailer_models']=[];pack=self.save(p);self.assertEqual(pack['status'],'blocked');self.assertEqual(pack['jobs'],{});self.assertIn('ADetailer',pack['message'])
 def test_unavailable_upscaler_does_not_download(self):
  p=self.advanced();p['sd']['render_options']['hires']['upscaler']='uninstalled model';pack=self.save(p);self.assertEqual(pack['status'],'blocked');self.assertEqual(pack['jobs'],{})
 def test_refiner_known_family_mismatch_preflight(self):
  p=self.advanced();self.s.studio.resources['refine']['base']='sd1.5';pack=self.save(p);self.assertEqual(pack['status'],'blocked');self.assertIn('Refiner',pack['message']);self.assertEqual(pack['jobs'],{})
 def test_comfy_advanced_controls_do_not_silently_disappear(self):
  p=self.advanced();self.s.studio.config['backend']='comfyui';pack=self.save(p);self.assertEqual(pack['status'],'blocked');self.assertIn('ComfyUI',pack['message'])
 def test_comfy_multistyle_native_binding_required_preflight(self):
  p=self.advanced();p['sd'].pop('render_options');p['sd']['lora']='hero';self.s.studio.config['backend']='comfyui';self.s.studio.native_templates['native']={'title':'mock','output':'1','installation':'fixture','backend':'comfyui','bindings':{'style_lora':[],'style_weight':[]}};self.s.studio.config['native_selected']['portrait']='native';pack=self.save(p);self.assertEqual(pack['status'],'blocked');self.assertIn('第 2',pack['message']);self.assertEqual(pack['jobs'],{})
 def test_model_and_options_persist_with_untouched_other_actor(self):
  p=self.advanced();self.save(p);saved=json.loads(self.s.studio.config_path.read_text(encoding='utf-8'));self.assertEqual(saved['profiles']['member-01']['render_options']['refiner']['checkpoint'],'refine');self.assertEqual(saved['profiles']['member-01']['style_loras'][0]['lora'],'line');self.assertNotIn('member-02',saved['profiles'])
 def test_ad_false_follow_respects_authored_prompt(self):
  p=self.advanced();p['sd']['render_options']['adetailer']['passes'][0].update(follow=False,prompt='authored face detail');r=self.recipe(p);calls,_=self.render(r);self.assertEqual(calls[0][1]['alwayson_scripts']['adetailer']['args'][2]['ad_prompt'],'authored face detail')
 def test_hires_limits_and_ad_slot_limit_preflight(self):
  p=self.advanced();p['sd']['render_options']['hires']['scale']=2;self.s.studio.config['templates']['portrait']['height']=1536;pack=self.save(p);self.assertEqual(pack['status'],'blocked');self.assertEqual(pack['jobs'],{});self.s.studio.config['templates']['portrait']['height']=1024;p=self.advanced();self.s.studio.services[self.s.studio.config['url']]['adetailer_slots']=1;pack=self.save(p);self.assertEqual(pack['status'],'blocked');self.assertEqual(pack['jobs'],{})

del Fixture
if __name__=='__main__':unittest.main()
