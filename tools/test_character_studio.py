import base64,copy,importlib.util,io,json,sys,tempfile,time,unittest
from pathlib import Path
from PIL import Image,ImageDraw
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'prototype'))
source=Path(__file__).parent/'sd-upgrade/prototype/lifebox/character_art.py'
if not source.is_file():source=Path(__file__).resolve().parents[1]/'prototype/lifebox/character_art.py'
sys.path.insert(0,str(source.parents[1]))
spec=importlib.util.spec_from_file_location('lifebox.character_art',source);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.CharacterStudio.discover=lambda self,extra=None:self.state()
m.CharacterStudio.probe=lambda self:self.state()
class StudioTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory(dir=Path(__file__).parent);self.root=Path(self.temp.name);self.s=m.CharacterStudio(self.root);self.s.closed=True;self.s.thread.join(2)
  self.s.resources={'c':{'id':'c','name':'base.safetensors','path':str(self.root/'base.safetensors'),'category':'checkpoint','selectable':True,'installations':['f'],'base':'sdxl'},'l':{'id':'l','name':'hero.safetensors','path':str(self.root/'hero.safetensors'),'category':'lora','selectable':True,'installations':['f'],'base':'sdxl'}}
  for r in self.s.resources.values():Path(r['path']).write_bytes(b'x')
  self.s.folders=[{'id':'f','backend':'a1111','path':str(self.root)}]
  self.profile={'identity':'short brown hair','trigger':'hero','lora':'l','weight':.8,'clothes_lora':'','clothes_weight':.6,'seed':123,'auto':False,'expression':'neutral'}
  self.s.configure({'installation':'f','backend':'a1111','checkpoint':'c','pixel_guide':'identity','profiles':{'member-01':self.profile}})
  self.s.services[self.s.config['url']]={'ready':True,'models':[],'loras':[],'vaes':[]}
  self.outfit={'render_key':'worn1','id':'coat','title':'日常外套'}
 def tearDown(self):self.temp.cleanup()
 def submit(self,kind='both'):return self.s.submit('member-01',self.outfit,'fully clothed opaque cardigan',kind)
 def test_local_endpoint_only(self):
  for u in ('https://cloud.example','http://192.168.1.1:7860','http://127.0.0.1:7860/secret','http://user:pass@localhost:7860','file:///D:/models'):
   with self.assertRaises(ValueError):m.local_url(u)
 def test_unknown_fields_rejected(self):
  with self.assertRaises(ValueError):self.s.configure({'unknown':1})
 def test_no_inline_lora(self):
  t=copy.deepcopy(self.s.config['templates']);t['portrait']['prompt']='<lora:missing:1>'
  with self.assertRaises(ValueError):self.s.configure({'templates':t})
 def test_sfw_positive_prompt(self):
  t=copy.deepcopy(self.s.config['templates']);t['portrait']['prompt']='nude woman'
  with self.assertRaises(ValueError):self.s.configure({'templates':t})
 def test_model_family_mismatch(self):
  self.s.resources['c']['base']='stable-diffusion-xl-v1-base'
  self.s.resources['l']['base']='sd_v1'
  with self.assertRaises(ValueError):self.submit()
 def test_auto_waits_for_selected_lora_and_generates_new_worn_outfit_once(self):
  self.s.config['auto']=True;self.s.config['profiles']['member-01']['auto']=True
  self.s.maybe_auto([('member-01',self.outfit,'fully clothed cardigan')]);self.assertEqual(len(self.s.pending),1)
  self.s.maybe_auto([('member-01',self.outfit,'fully clothed cardigan')]);self.assertEqual(len(self.s.pending),1)
  self.outfit['render_key']='changed-worn-outfit';self.s.maybe_auto([('member-01',self.outfit,'fully clothed jacket')]);self.assertEqual(len(self.s.pending),2)
 def test_unbound_does_not_generate(self):
  self.s.config['profiles']['member-01']['lora']=''
  with self.assertRaises(ValueError):self.submit()
 def test_job_deduplication(self):self.assertEqual(self.submit()['id'],self.submit()['id']);self.assertEqual(len(self.s.pending),1)
 def test_worn_outfit_scopes_cache(self):
  first=self.submit()['id'];self.outfit['render_key']='worn2';self.assertNotEqual(first,self.submit()['id'])
 def test_checkpoint_changes_cache(self):
  first=self.submit()['id'];self.s.resources['c']['mtime']=123;self.assertNotEqual(first,self.submit()['id'])
 def test_cancel_records_request(self):
  j=self.submit();self.s.cancel(j['id']);self.assertTrue(self.s.jobs[j['id']]['cancel'])
 def test_no_arbitrary_asset_path(self):self.assertIsNone(self.s.asset('../settings.json'));self.assertIsNone(self.s.asset('0'*64+'-sprite.png'))
 def image(self):
  im=Image.new('RGB',(512,512),'white');d=ImageDraw.Draw(im);d.rectangle((210,30,302,480),fill='#846046');d.rectangle((225,230,250,360),fill='white');b=io.BytesIO();im.save(b,format='PNG');return b.getvalue()
 def test_cutout_keeps_enclosed_white_clothes(self):
  im=self.s._cutout(self.image(),self.s.config);self.assertEqual(im.getpixel((0,0))[3],0);self.assertEqual(im.getpixel((230,250))[3],255)
 def test_sprite_anchor_and_grid(self):
  im=self.s._cutout(self.image(),self.s.config,True);self.assertEqual(im.size,(64,64));self.assertEqual(im.getbbox()[3],60)
 def test_generation_frame_and_expression_plan(self):
  j=self.submit();job=self.s.jobs[j['id']];calls=[]
  self.s.closed=False
  def render(r,t,prompt,seed,reference=None):calls.append((prompt,seed,reference is not None));return self.image()
  self.s._render=render;self.s._generate(job);job['status']='ready';self.s.closed=True
  self.assertEqual(len(calls),18);self.assertEqual(sum(c[2] for c in calls),16)
  self.assertEqual(len(job['files']['portraits']),6)
  with Image.open(self.s.assets/job['files']['sprite']) as sheet:self.assertEqual(sheet.size,(192,256))
  self.assertTrue(any('back view' in c[0] for c in calls));self.assertTrue(any('left foot forward' in c[0] for c in calls))
  self.s.activate(job['id'],'happy');self.assertIn('portrait',self.s.appearance('member-01',self.outfit));self.assertEqual(self.s.appearance('member-01',{'render_key':'other'}),{})
  self.assertEqual(self.s.appearance('member-02',self.outfit),{});self.assertIsNotNone(self.s.asset(job['files']['sprite']))
 def test_restart_keeps_jobs_and_active(self):
  j=self.submit();self.s._persist();again=m.CharacterStudio(self.root);again.closed=True;again.thread.join(2);self.assertEqual(again.jobs[j['id']]['status'],'interrupted')
 def test_comfy_graph_identity_and_img2img(self):
  j=self.submit('portrait');recipe=self.s.jobs[j['id']]['recipe'];recipe['config'].update(backend='comfyui',sampler='euler',scheduler='normal');recipe['api_models']=['base.safetensors'];recipe['api_loras']=['hero.safetensors'];calls=[];original=m.api
  def fake(url,path,payload=None,**kwargs):
   calls.append((path,payload))
   if path=='/upload/image':return {'name':'ref.png','subfolder':''}
   if path=='/prompt':return {'prompt_id':'pid'}
   if path=='/history/pid':return {'pid':{'outputs':{'7':{'images':[{'filename':'x.png','subfolder':'','type':'output'}]}}}}
  class Response:
   def __enter__(self):return self
   def __exit__(self,*a):pass
   def read(self,*a):return self_image
  class Opener:
   def open(self,*a,**k):return Response()
  self_image=self.image();oldopener=m.request.build_opener;m.api=fake;m.request.build_opener=lambda *a:Opener()
  try:self.s._render(recipe,recipe['config']['templates']['portrait'],'adult woman',123,self_image)
  finally:m.api=original;m.request.build_opener=oldopener
  graph=next(p['prompt'] for route,p in calls if route=='/prompt');classes={n['class_type'] for n in graph.values()};self.assertIn('LoraLoader',classes);self.assertIn('VAEEncode',classes);self.assertIn('LoadImage',classes);self.assertEqual(graph['5']['inputs']['seed'],123)
 def control_setup(self):
  path=self.root/'pose.safetensors';path.write_bytes(b'pose');self.s.resources['cn']={'id':'cn','name':path.name,'path':str(path),'category':'controlnet','selectable':True,'installations':['f'],'base':'sdxl'}
  self.s.configure({'pixel_guide':'controlnet','control_model':'cn'});self.s.services[self.s.config['url']]['control_models']=['pose [abc]']
 def test_controlnet_uses_identity_anchor_and_twelve_pose_maps(self):
  self.control_setup();j=self.submit('pixel');job=self.s.jobs[j['id']];calls=[];self.s.closed=False
  def render(r,t,prompt,seed,reference=None,control=None):calls.append((prompt,reference,control,t['denoise']));return self.image()
  self.s._render=render;self.s._generate(job);self.s.closed=True
  self.assertEqual(job['total'],13);self.assertEqual(len(calls),13);self.assertIsNone(calls[0][1]);self.assertTrue(all(c[1] and c[2] for c in calls[1:]));self.assertEqual(len({c[2] for c in calls[1:]}),12);self.assertEqual(len(job['validation']['frames']),12);self.assertTrue(all(f['feet_y']==60 for f in job['validation']['frames']))
 def test_missing_controlnet_does_not_silently_use_lpc(self):
  self.control_setup();self.s.services[self.s.config['url']]['control_models']=[]
  with self.assertRaises(ValueError):self.submit('pixel')
 def test_pose_control_model_must_match_checkpoint(self):
  self.control_setup();self.s.resources['cn']['base']='sd_v1'
  with self.assertRaises(ValueError):self.submit('pixel')
 def test_hybrid_matte_clears_light_background_panel(self):
  im=Image.new('RGBA',(128,128),'white');d=ImageDraw.Draw(im);d.rectangle((16,16,112,96),fill='#f3eee4');d.rectangle((52,12,76,116),fill='#73452a');d.rectangle((58,44,70,74),fill='white');b=io.BytesIO();im.save(b,format='PNG');c=copy.deepcopy(self.s.config);c['background_method']='rmbg';result=self.s._cutout(b.getvalue(),c)
  self.assertEqual(result.getpixel((20,30))[3],0);self.assertEqual(result.getpixel((62,60))[3],255)
 def test_palette_alignment_keeps_face_white_shirt_and_black_pants(self):
  from lifebox.sd_identity import align_clothes_palette
  import colorsys
  def figure(color):
   im=Image.new('RGBA',(64,64));d=ImageDraw.Draw(im);d.rectangle((20,15,44,50),fill=color);d.rectangle((27,19,37,37),fill='white');d.rectangle((23,51,41,60),fill='black');d.rectangle((25,3,39,13),fill='#f0ba90');return im
  frame=figure('#b67b2c');ref=figure('#6b2024');result=align_clothes_palette(frame,ref)
  old=colorsys.rgb_to_hsv(*[x/255 for x in frame.getpixel((22,26))[:3]]);new=colorsys.rgb_to_hsv(*[x/255 for x in result.getpixel((22,26))[:3]])
  self.assertLess(new[2],old[2]);self.assertEqual(result.getpixel((30,7)),frame.getpixel((30,7)));self.assertEqual(result.getpixel((30,26)),(255,255,255,255));self.assertEqual(result.getpixel((30,55)),(0,0,0,255));self.assertEqual(result.getpixel((0,0))[3],0)
 def test_templates_reject_attribute_and_large_format_spec(self):
  for text in ('{identity.__class__}','{identity:>999999999}','{identity!r}'):
   templates=copy.deepcopy(self.s.config['templates']);templates['pixel']['prompt']=text
   with self.assertRaises(ValueError):self.s.configure({'templates':templates})
 def test_cg_uses_actor_outfit_scene_and_keeps_background(self):
  scene={'scene':'park','place_name':'河畔公園','description':'riverside park with trees and a bench'};j=self.s.submit('member-01',self.outfit,'opaque brown jacket','cg',scene);job=self.s.jobs[j['id']];self.s.closed=False;calls=[]
  def render(r,t,prompt,seed,reference=None):calls.append((prompt,reference));return self.image()
  self.s._render=render;self.s._generate(job);self.s.closed=True;job['status']='ready';self.assertEqual(job['total'],2);self.assertEqual(len(calls),2);self.assertIn('riverside park',calls[1][0]);self.assertIn('opaque brown jacket',calls[1][0]);self.assertTrue(calls[1][1]);self.assertIsNotNone(self.s.asset(job['files']['cg']))
  with Image.open(self.s.assets/job['files']['cg']) as im:self.assertEqual(im.getpixel((0,0))[:3],(255,255,255))
 def test_scene_changes_general_cg_cache(self):
  a=self.s.submit('member-01',self.outfit,'opaque jacket','cg',{'scene':'park','place_name':'公園','description':'riverside park'});b=self.s.submit('member-01',self.outfit,'opaque jacket','cg',{'scene':'cafe','place_name':'咖啡廳','description':'cafe table'});self.assertNotEqual(a['id'],b['id'])
 def test_comfy_controlnet_graph_inputs(self):
  self.control_setup();recipe=self.s.recipe('member-01',self.outfit,'opaque jacket','pixel');recipe['config'].update(backend='comfyui',sampler='euler',scheduler='normal');recipe.update(api_models=['base.safetensors'],api_loras=['hero.safetensors'],api_control_models=['pose.safetensors']);calls=[];original=m.api;image=self.image()
  def fake(url,path,payload=None,**kwargs):
   calls.append((path,payload))
   if path=='/upload/image':return {'name':'ref.png','subfolder':''}
   if path=='/prompt':return {'prompt_id':'pid'}
   if path=='/history/pid':return {'pid':{'outputs':{'7':{'images':[{'filename':'x.png','subfolder':'','type':'output'}]}}}}
  class Response:
   def __enter__(self):return self
   def __exit__(self,*a):pass
   def read(self,*a):return image
  class Opener:
   def open(self,*a,**k):return Response()
  old=m.request.build_opener;m.api=fake;m.request.build_opener=lambda *a:Opener()
  try:self.s._render(recipe,recipe['config']['templates']['pixel'],'adult clothed woman',123,image,control=image)
  finally:m.api=original;m.request.build_opener=old
  graph=next(v['prompt'] for p,v in calls if p=='/prompt');self.assertEqual(graph['22']['class_type'],'ControlNetApplyAdvanced');self.assertEqual(graph['5']['inputs']['positive'],['22',0]);self.assertEqual(graph['21']['inputs']['control_net_name'],'pose.safetensors')
if __name__=='__main__':unittest.main(verbosity=1)
