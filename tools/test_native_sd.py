import sys,copy,json,io,base64,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from PIL import Image,PngImagePlugin
source=Path(__file__).parent/'sd-upgrade/prototype'
if not source.is_dir():source=Path(__file__).resolve().parents[1]/'prototype'
sys.path.insert(0,str(source))
from lifebox import character_art as m,sd_templates as n

def graph():
 return {'1':{'class_type':'CheckpointLoaderSimple','inputs':{'ckpt_name':'base.safetensors'}},
 '10':{'class_type':'LoraLoader','inputs':{'model':['1',0],'clip':['1',1],'lora_name':'hero.safetensors','strength_model':.7,'strength_clip':.7}},
 '2':{'class_type':'CLIPTextEncode','inputs':{'text':'fully clothed adult woman','clip':['10',1]}},
 '3':{'class_type':'CLIPTextEncode','inputs':{'text':m.NEGATIVE,'clip':['10',1]}},
 '9':{'class_type':'LoadImage','inputs':{'image':'reference.png'}},
 '4':{'class_type':'VAEEncode','inputs':{'pixels':['9',0],'vae':['1',2]}},
 '5':{'class_type':'KSampler','inputs':{'model':['10',0],'positive':['2',0],'negative':['3',0],'latent_image':['4',0],'seed':1,'steps':2,'cfg':6,'sampler_name':'euler','scheduler':'normal','denoise':1}},
 '6':{'class_type':'VAEDecode','inputs':{'samples':['5',0],'vae':['1',2]}},
 '7':{'class_type':'SaveImage','inputs':{'images':['6',0],'filename_prefix':'LifeBox/native-test'}}}
def png():
 b=io.BytesIO();Image.new('RGB',(256,320),'white').save(b,format='PNG');return b.getvalue()
class NativeTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).parent)
  with patch.object(m.CharacterStudio,'discover',lambda s,extra=None:s.state()),patch.object(m.CharacterStudio,'probe',lambda s:s.state()):self.s=m.CharacterStudio(Path(self.temp.name))
  self.s.closed=True;self.s.thread.join(2);self.s.folders=[{'id':'f','path':self.temp.name,'backend':'a1111','label':'fixture'}];self.s.config['installation']='f'
 def tearDown(self):self.temp.cleanup()
 def template(self,backend='a1111'):
  g=graph();return {'title':'完整測試模板','backend':backend,'payload':g if backend=='comfyui' else {'steps':2,'width':256,'height':320,'alwayson_scripts':{'FreeU Integrated':{'args':[True,1.1,1.2,.9,.2]}},'enable_hr':True,'hr_scale':1.5},'bindings':n.infer(g) if backend=='comfyui' else {},'output':'7' if backend=='comfyui' else ''}
 def test_native_payload_preserved(self):
  t=n.validate(self.template(),'a1111',m.BLOCKED);self.assertTrue(t['payload']['enable_hr']);self.assertTrue(t['payload']['alwayson_scripts']['FreeU Integrated']['args'][0])
 def test_reforge_png_restores_freeu_and_inherited_hires_sampler(self):
  t=self.template();t['payload']={'infotext':'adult woman\nNegative prompt: nsfw\nSteps: 2, Hires upscale: 1.5, freeu_enabled: True, freeu_b1: 1.1, freeu_b2: 1.2, freeu_s1: 0.9, freeu_s2: 0.2'}
  payload=n.validate(t,'a1111',m.BLOCKED)['payload'];self.assertIsNone(payload['hr_sampler_name']);self.assertIsNone(payload['hr_scheduler']);self.assertEqual(payload['alwayson_scripts']['FreeU Integrated']['args'],[True,1.1,1.2,.9,.2])
 def test_api_schema_unknown_field_fails(self):
  with self.assertRaises(ValueError):n.validate(self.template(),'a1111',m.BLOCKED,api_fields={'steps'})
 def test_comfy_graph_preserved_and_negative_allowed(self):
  t=n.validate(self.template('comfyui'),'comfyui',m.BLOCKED);self.assertEqual(t['payload'],graph())
 def test_missing_nodes_not_silently_discarded(self):
  with self.assertRaisesRegex(ValueError,'未載入'):n.validate(self.template('comfyui'),'comfyui',m.BLOCKED,node_info={})
 def test_cloud_credentials_rejected(self):
  for value in ({'api_key':'fixture'}, {'url':'https://cloud.example/generate'}):
   t=self.template();t['payload'].update(value)
   with self.assertRaises(ValueError):n.validate(t,'a1111',m.BLOCKED)
 def test_h_positive_and_infotext_blocked(self):
  for field,text in [('prompt','nude woman'),('infotext','nude woman\nNegative prompt: bad\nSteps: 2')]:
   t=self.template();t['payload'][field]=text
   with self.assertRaises(ValueError):n.validate(t,'a1111',m.BLOCKED)
 def test_hires_infotext_positive_cannot_bypass_sealed_mode(self):
  t=self.template();t['payload']={'infotext':'adult woman\nNegative prompt: nsfw\nSteps: 2, Hires prompt: high quality, nude woman, Hires upscaler: Latent'}
  with self.assertRaises(ValueError):n.validate(t,'a1111',m.BLOCKED)
 def test_map_does_not_mutate_native_graph(self):
  t=n.validate(self.template('comfyui'),'comfyui',m.BLOCKED);r=n.mapped_payload(t,{'lora_weight':.3,'prompt':'different adult woman'});self.assertEqual(r['10']['inputs']['strength_clip'],.3);self.assertEqual(t['payload'],graph())
 def test_link_cannot_be_replaced_by_binding(self):
  t=self.template('comfyui');t['bindings']['prompt']='/5/inputs/positive'
  with self.assertRaises(ValueError):n.validate(t,'comfyui',m.BLOCKED)
 def test_png_metadata_draft_no_model_or_cast_change(self):
  b=io.BytesIO();meta=PngImagePlugin.PngInfo();meta.add_text('parameters','adult woman, coat\nNegative prompt: nsfw, nude\nSteps: 2, Size: 256x320, FreeU: True');Image.new('RGB',(256,320)).save(b,format='PNG',pnginfo=meta)
  result=self.s.native_prepare({'png':base64.b64encode(b.getvalue()).decode(),'title':'原生PNG'});self.assertIn('FreeU',result['native_draft']['payload']['infotext']);self.assertEqual(self.s.config['profiles'],{});self.assertFalse(self.s.native_path.exists())
 def test_save_uses_installed_schema_names(self):
  spec={'paths':{f'/sdapi/v1/{r}':{'post':{'requestBody':{'content':{'application/json':{'schema':{'$ref':'#/components/schemas/InstalledName'}}}}}} for r in ('txt2img','img2img')},'components':{'schemas':{'InstalledName':{'properties':{k:{} for k in self.template()['payload']}}}}}
  with patch.object(m,'api',return_value=spec):state=self.s.native_save(self.template())
  tid=state['native_saved'];self.assertIn(tid,self.s.native_templates);self.assertEqual(self.s.native_templates[tid]['payload'],self.template()['payload'])
 def test_atomic_template_selection(self):
  self.s.native_templates['good']={**self.template(),'installation':'f'}
  with self.assertRaises(ValueError):self.s.native_select({'selections':{'portrait':'good','cg':'missing'}})
  self.assertEqual(self.s.config['native_selected'],{'portrait':'','pixel':'','cg':''})
 def test_using_template_cannot_be_deleted(self):
  self.s.native_templates['good']={**self.template(),'installation':'f'};self.s.native_select({'kind':'cg','id':'good'})
  with self.assertRaises(ValueError):self.s.native_delete('good')
 def test_comfy_missing_reference_binding_cannot_be_selected(self):
  t=self.template('comfyui');del t['bindings']['reference'];self.s.config['backend']='comfyui';self.s.native_templates['x']={**t,'installation':'f'}
  with self.assertRaisesRegex(ValueError,'reference'):self.s.native_select({'kind':'portrait','id':'x'})
 def test_render_preserves_scripts_and_injects_current_identity(self):
  t={**copy.deepcopy(m.TEMPLATES['portrait']),'_native':n.validate(self.template(),'a1111',m.BLOCKED)}
  r={'config':{'backend':'a1111','url':'http://127.0.0.1:7861','sampler':'Euler','scheduler':'Automatic'},'profile':{'lora':'hero','weight':.8},'checkpoint':{'path':'base'},'loras':[{'id':'hero','path':'hero','weight':.8}],'api_models':[{'filename':'base','title':'base'}],'api_loras':[{'path':'hero','name':'hero'}],'vae':None}
  captured=[]
  def api(url,path,payload=None,**kwargs):captured.append(payload);return {'images':[base64.b64encode(png()).decode()]}
  with patch.object(m,'api',api):self.s._render(r,t,'current adult woman, coat',10)
  payload=captured[0];self.assertTrue(payload['enable_hr']);self.assertEqual(payload['width'],256);self.assertIn('current adult woman',payload['prompt']);self.assertIn('<lora:hero:0.8>',payload['prompt']);self.assertTrue(payload['alwayson_scripts']['FreeU Integrated']['args'][0]);self.assertFalse(payload['save_images'])
 def test_infotext_native_steps_not_overwritten(self):
  data=self.template();data['payload']={'infotext':'adult woman\nNegative prompt: nsfw\nSteps: 2, Size: 256x320, CFG scale: 5'};t={**copy.deepcopy(m.TEMPLATES['portrait']),'_native':n.validate(data,'a1111',m.BLOCKED)}
  r={'config':{'backend':'a1111','url':'http://127.0.0.1:7861','sampler':'Euler','scheduler':'Automatic'},'profile':{'lora':'hero','weight':.8},'checkpoint':{'path':'base'},'loras':[{'id':'hero','path':'hero','weight':.8}],'api_models':[{'filename':'base','title':'base'}],'api_loras':[{'path':'hero','name':'hero'}],'vae':None};captured=[]
  with patch.object(m,'api',lambda url,path,payload,**kw:(captured.append(payload) or {'images':[base64.b64encode(png()).decode()]})):self.s._render(r,t,'clothed adult',1)
  self.assertNotIn('steps',captured[0]);self.assertNotIn('width',captured[0]);self.assertIn('infotext',captured[0])
 def test_comfy_native_execution_reference_and_custom_output(self):
  native=n.validate(self.template('comfyui'),'comfyui',m.BLOCKED);t={**m.TEMPLATES['portrait'],'_native':native};r={'config':{'url':'http://127.0.0.1:8188'},'profile':{'lora':'hero','weight':.5},'checkpoint':{'name':'base.safetensors'},'loras':[{'id':'hero','name':'hero.safetensors','weight':.5}],'api_models':['base.safetensors'],'api_loras':['hero.safetensors']};sent=[]
  info={v['class_type']:{'output_node':v['class_type']=='SaveImage'} for v in graph().values()}
  def api(url,path,payload=None,**kw):
   if path=='/upload/image':return {'name':'ref.png','subfolder':''}
   if path=='/object_info':return info
   if path=='/prompt':sent.append(payload['prompt']);return {'prompt_id':'job'}
   if path=='/history/job':return {'job':{'outputs':{'7':{'images':[{'filename':'out.png','subfolder':'','type':'output'}]}},'status':{'completed':True}}}
   raise AssertionError(path)
  class Response:
   def __enter__(self):return self
   def __exit__(self,*a):pass
   def read(self,*a):return png()
  with patch.object(m,'api',api),patch.object(m.request,'build_opener') as opener:
   opener.return_value.open.return_value=Response();self.s._render_native_comfy(r,t,'current adult','nsfw, nude',33,None,None)
  self.assertEqual(sent[0]['9']['inputs']['image'],'ref.png');self.assertEqual(sent[0]['5']['inputs']['denoise'],1);self.assertEqual(sent[0]['10']['inputs']['strength_clip'],.5);self.assertEqual(sent[0]['6'],graph()['6'])

if __name__=='__main__':unittest.main()
