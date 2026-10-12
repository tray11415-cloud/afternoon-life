"""Local SD character studio: inventory, reproducible recipes and bounded jobs.

No model is unpickled here, no paid/cloud endpoint is accepted, and no worker
mutates the world. Activated art is scoped to its captured worn outfit.
"""
from __future__ import annotations
import base64, copy, hashlib, io, json, os, re, socket, struct, threading, time, string,secrets
from collections import deque
from pathlib import Path
from urllib import request, parse
from .policies import _NoRedirect
from . import sd_templates

ACTORS = [f'member-{i:02d}' for i in range(1,11)] + ['player']
EXPRESSIONS = {'neutral':'relaxed neutral expression', 'happy':'gentle happy smile',
 'shy':'bashful smile, light blush', 'sad':'sad eyes, closed mouth',
 'surprised':'surprised expression, raised eyebrows', 'angry':'annoyed expression, furrowed brows'}
LABELS = {'neutral':'平常','happy':'開心','shy':'害羞','sad':'難過','surprised':'驚訝','angry':'生氣'}
NEGATIVE = 'nsfw, nude, naked, nipples, underwear, lingerie, erotic, child, teen, baby, young-looking, school uniform, transparent clothes, cleavage, bare shoulders, backless outfit, exposed back, open back clothes, bad anatomy, extra limbs, extra fingers, cropped feet, text, watermark, multiple people'
BLOCKED = re.compile(r'nsfw|hentai|nude|naked|sex|lingerie|see.through|footjob|bdsm|ahegao|bikini|loli|child|teen|fuck|blowjob|fellatio|creampie|cumshot|penetration|masturb|orgasm|tentacle|r18|anal|dildo|paizuri|buttjob|doggy.?style|missionary|cowgirl|milking|milk_hand|hand_milk|cumdrip|cumdr|cervix|clitoris|nippl|penis|pussy|bondage|spank|pillory|breast.?sucking|breast.?press|sucking|grop|grabb(?:ed|ing).?breast|kissing.?breast|panties|undress|transparent.?corset|fishnet.?bra|裸|情趣|内衣|內衣|乳交|足交|性交|比基尼|透視|透视|色情|性愛|性爱', re.I)
EXTS = {'.safetensors','.ckpt','.pt','.pth','.bin','.gguf','.onnx','.yaml','.yml','.json'}
CATEGORIES = {'Stable-diffusion':'checkpoint','checkpoints':'checkpoint','diffusion_models':'diffusion',
 'unet':'diffusion','Lora':'lora','loras':'lora','LyCORIS':'lora','VAE':'vae','vae':'vae',
 'ControlNet':'controlnet','controlnet':'controlnet','embeddings':'embedding','text_encoders':'text_encoder',
 'clip':'text_encoder','clip_vision':'vision','ipadapter':'ipadapter','upscale_models':'upscaler',
 'ESRGAN':'upscaler','RealESRGAN':'upscaler','SwinIR':'upscaler','RMBG':'background',
 'rembg':'background','background_removal':'background'}
TEMPLATES = {
 'portrait': {'prompt':'high quality anime character illustration, {identity}, {outfit}, full body standing portrait, {expression}, natural relaxed standing pose, hands visible, both feet visible, front view, centered single character, plain white background, soft studio lighting',
  'negative':NEGATIVE,'width':768,'height':1024,'steps':24,'cfg':6.0,'denoise':0.30},
 'pixel': {'prompt':'clean detailed pixel art, (single adult woman:1.4), {direction}, {pose}, {identity}, {outfit}, full body, orthographic view, both feet visible, centered one person, (flat plain white background:1.3), crisp pixel edges, consistent proportions',
  'negative':NEGATIVE+', photorealistic, blurry, perspective floor, grid, sprite sheet, duplicate, twins, two people, side by side, split image, ornamental border, frame, floor, scenery, gradient background',
  'width':512,'height':512,'steps':24,'cfg':6.0,'denoise':0.80},
 'cg':{'prompt':'high quality anime scene illustration, {identity}, {outfit}, {scene}, (detailed environment fills entire canvas:1.4), wide scenic background, relaxed everyday moment, single adult woman, fully clothed, consistent face and hair, natural lighting, no text',
  'negative':NEGATIVE+', white border, empty white margins, blank background, picture frame, rectangular frame, pillars, split panels','width':768,'height':512,'steps':24,'cfg':6.0,'denoise':.92}}

def key(value):
 return hashlib.sha256(json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':')).encode()).hexdigest()

def family(value):
 value=value.lower()
 if any(s in value for s in ('sdxl','sd_xl','stable-diffusion-xl')):return 'sdxl'
 if any(s in value for s in ('sd_v1','sd1.5','sd1_5','stable-diffusion-v1','sd15')):return 'sd1'
 if any(s in value for s in ('sd_v2','sd2.1','sd2_','stable-diffusion-v2')):return 'sd2'
 for name in ('flux','qwen','wan','hunyuan'):
  if name in value:return name
 return None

def atomic(path, value):
 path.parent.mkdir(parents=True,exist_ok=True)
 tmp=path.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8');os.replace(tmp,path)

def metadata(path):
 try:
  if path.suffix.lower()!='.safetensors':return {}
  with path.open('rb') as f:
   length=struct.unpack('<Q',f.read(8))[0]
   if length>8*1024*1024:return {}
   head=json.loads(f.read(length));meta=head.get('__metadata__',{})
  arch=str(meta.get('ss_base_model_version') or meta.get('modelspec.architecture') or '')
  if not arch:
   names=' '.join(list(head)[:250])
   arch='SDXL' if 'conditioner.embedders.1' in names or 'lora_te2_' in names else '未知'
  words=[]
  if isinstance(meta.get('ss_tag_frequency'),str):
   tags=json.loads(meta['ss_tag_frequency']);counter={}
   for group in tags.values():
    if isinstance(group,dict):
     for tag,count in group.items():
      if isinstance(count,(int,float)):counter[tag]=counter.get(tag,0)+count
   words=sorted(counter,key=counter.get,reverse=True)[:16]
  return {'base':arch[:120],'tags':words,'title':str(meta.get('modelspec.title') or meta.get('ss_output_name') or '')[:120]}
 except (OSError,ValueError,TypeError,AttributeError,struct.error):return {}

def local_url(url):
 p=parse.urlsplit(url)
 if p.scheme!='http' or p.hostname not in {'127.0.0.1','localhost','::1'} or p.username or p.password or p.path not in ('','/') or p.query or p.fragment:
  raise ValueError('只接受本機 SD HTTP 服務位址，例如 http://127.0.0.1:7861')
 if not p.port or not 1024<=p.port<=65535:raise ValueError('請指定本機 SD 連接埠')
 return url.rstrip('/')

def api(url, path, payload=None, timeout=4, raw=None, content_type=None):
 local_url(url)
 data=raw if raw is not None else json.dumps(payload).encode() if payload is not None else None
 req=request.Request(url+path,data,{'Content-Type':content_type or 'application/json'},method='POST' if data is not None else 'GET')
 with request.build_opener(_NoRedirect).open(req,timeout=timeout) as r:
  body=r.read(48*1024*1024+1)
 if len(body)>48*1024*1024:raise ValueError('SD 回傳內容過大')
 return json.loads(body) if content_type!='image/png' else body

class CharacterStudio:
 def __init__(self,root,project=None):
  self.root=Path(root);self.project=Path(project) if project else Path(__file__).resolve().parents[2]
  self.config_path=self.root/'settings.json';self.assets=self.root/'assets';self.assets.mkdir(parents=True,exist_ok=True)
  self.lock=threading.RLock();self.pending=deque();self.jobs={};self.closed=False;self.resources={};self.folders=[];self.services={};self.auto_seen=set()
  self.config={'version':2,'installation':'','backend':'a1111','url':'http://127.0.0.1:7861',
   'checkpoint':'','vae':'','sampler':'Euler','scheduler':'Automatic','auto':True,
   'pixel_size':64,'pixel_guide':'controlnet','control_model':'','control_weight':.85,'palette':64,'palette_reference':True,'remove_background':True,'background_tolerance':26,
   'background_method':'edge','background_model':'','background_device':'cpu','background_resolution':512,
   'expressions':list(EXPRESSIONS),'templates':copy.deepcopy(TEMPLATES),'profiles':{},'active':{},'native_selected':{'portrait':'','pixel':'','cg':''},'outfit_loras':{}}
  self.portrait_library={};self.library_path=self.root/'portrait-library.json'
  if self.library_path.is_file():
   try:self.portrait_library=json.loads(self.library_path.read_text(encoding='utf-8'))
   except (ValueError,OSError):pass
  self.native_templates={};self.native_path=self.root/'native-templates.json';self.sd_processes={}
  if self.native_path.is_file():
   try:self.native_templates=json.loads(self.native_path.read_text(encoding='utf-8'))
   except (OSError,ValueError):pass
  saved={}
  if self.config_path.exists():
   try:
    saved=json.loads(self.config_path.read_text(encoding='utf-8'));self.config.update(saved)
    if saved.get('version',1)<2:
     self.config.update(version=2,pixel_guide='controlnet');self.config['templates']['pixel']['denoise']=.8
   except (OSError,ValueError):pass
  manifest=self.root/'jobs.json'
  if manifest.exists():
   try:
    for job in json.loads(manifest.read_text(encoding='utf-8')):
     if job.get('status') in ('queued','running'):job.update(status='interrupted',message='上次服務停止，請重新生成；已完成圖片保留。')
     self.jobs[job['id']]=job
   except (OSError,ValueError,KeyError):pass
  migrated=False
  for job in self.jobs.values():
   if job.get('status')!='ready' or job.get('recipe',{}).get('pipeline_version',1)>=6:continue
   for expression,file in job.get('files',{}).get('portraits',{}).items():
    ident=key({'legacy_portrait':job['id'],'expression':expression})
    if ident in self.portrait_library or not (self.assets/file).is_file():continue
    self.portrait_library[ident]={'actor':job['actor'],'gender':'female','outfit':copy.deepcopy(job['outfit']),'expression':expression,'file':file,'url':'/character-art/'+file,'source':f'sources/{job["id"]}/portrait-{expression}.png','signature':ident,'created':job.get('created',0),'legacy':True};migrated=True
  if migrated:atomic(self.library_path,self.portrait_library)
  self.discover()
  for name,template in TEMPLATES.items():self.config['templates'].setdefault(name,copy.deepcopy(template))
  for name in TEMPLATES:self.config['native_selected'].setdefault(name,'')
  if not self.config['control_model']:
   candidates=[r for r in self.resources.values() if r['category']=='controlnet' and 'openpose' in r['name'].lower() and self.config['installation'] in r['installations']]
   if candidates:self.config['control_model']=candidates[0]['id']
  if not self.config['background_model']:
   candidates=[r for r in self.resources.values() if r['category']=='background' and Path(r['path']).name=='model.safetensors' and (Path(r['path']).parent/'birefnet.py').is_file()]
   if candidates:
    self.config['background_model']=candidates[0]['id']
    if 'background_method' not in saved:self.config['background_method']='rmbg'
  if not self.config['checkpoint']:
   available=[r for r in self.resources.values() if r['category']=='checkpoint' and r['selectable'] and self.config['installation'] in r['installations']]
   if available:self.config['checkpoint']=available[0]['id']
  self.probe()
  self.thread=threading.Thread(target=self._worker,name='character-sd',daemon=True);self.thread.start()

 def discover(self,extra=None):
  roots=[]
  known=[Path('D:/stable-diffusion-webui-reForge'),Path('D:/ComfyUI_windows_portable_nightly_pytorch/ComfyUI')]
  extra_file=self.root/'extra-folders.json'
  if extra_file.exists():
   try:known.extend(Path(p) for p in json.loads(extra_file.read_text(encoding='utf-8')))
   except (OSError,ValueError,TypeError):pass
  for drive in ('C:/','D:/','E:/'):
   try:
    for p in Path(drive).iterdir():
     if p.is_dir() and re.search(r'comfy|stable.diffusion|sd.webui|forge',p.name,re.I):known.extend([p,p/'ComfyUI'])
   except OSError:pass
  if extra:known.append(Path(extra).expanduser().resolve())
  for p in known:
   p=p.resolve()
   backend='comfyui' if (p/'main.py').is_file() and (p/'comfy').is_dir() else 'a1111' if (p/'webui.py').is_file() else None
   if backend and p not in [q[0] for q in roots]:roots.append((p,backend))
  if extra and Path(extra).resolve() not in [q[0] for q in roots]:raise ValueError('這不是 SD WebUI / Forge / ComfyUI 安裝資料夾')
  if extra:atomic(extra_file,[str(q[0]) for q in roots])
  folders=[];resources={};visited=set()
  for root,backend in roots:
   fid=key(str(root))[:16];folders.append({'id':fid,'path':str(root),'backend':backend,'label':root.name})
   locations=[root/'models',root/'embeddings']
   # ComfyUI shared paths: parse only path strings, never arbitrary YAML tags.
   yaml=root/'extra_model_paths.yaml'
   if yaml.is_file():
    try:
     for line in yaml.read_text(encoding='utf-8').splitlines():
      m=re.match(r'\s*base_path:\s*["\']?([^"\'#]+)',line)
      if m:
       shared=Path(m.group(1).strip());locations.extend([shared/'models',shared/'embeddings'])
    except OSError:pass
   for location in locations:
    if not location.is_dir():continue
    try:
     for path in location.rglob('*'):
      if not path.is_file() or path.suffix.lower() not in EXTS or path.stat().st_size==0:continue
      resolved=path.resolve()
      if not resolved.is_relative_to(location.resolve()):continue
      rid=key(str(resolved))[:24]
      if rid in visited:
       if fid not in resources[rid]['installations']:resources[rid]['installations'].append(fid)
       continue
      visited.add(rid);rel=path.relative_to(location);category='embedding' if location.name=='embeddings' else CATEGORIES.get(rel.parts[0],'other')
      meta=metadata(path) if category in ('checkpoint','lora') else {}
      blocked=bool(category=='lora' and BLOCKED.search(path.stem+' '+meta.get('title','')))
      size=path.stat();resources[rid]={'id':rid,'name':path.name,'path':str(resolved),'category':category,
       'bytes':size.st_size,'mtime':size.st_mtime_ns,'base':meta.get('base','未知'),'tags':meta.get('tags',[]),
       'installations':[fid],'selectable':not blocked and path.suffix.lower() in {'.safetensors','.ckpt','.pt','.pth','.gguf','.onnx'},
       'note':'H 類 LoRA 已封印' if blocked else '底模可生成 SFW；不代表其所有輸出均為 SFW' if BLOCKED.search(path.stem) else '',
       'relative':rel.as_posix(),'format':path.suffix[1:]}
    except OSError:continue
  # Include installed scripts/extensions/workflows in the inventory without executing them.
  for root,backend in roots:
   fid=key(str(root))[:16]
   for dirname in ('extensions','custom_nodes'):
    folder=root/dirname
    if folder.is_dir():
     for p in folder.iterdir():
      if p.is_dir() and p.name not in ('__pycache__','.git'):
       rid=key(str(p.resolve()))[:24];resources[rid]={'id':rid,'name':p.name,'path':str(p),'category':'extension','bytes':0,'base':'','tags':[],'installations':[fid],'selectable':False,'note':'僅列出安裝；是否可用依 SD 服務','format':'folder'}
   for name in ('user/default/workflows','workflows'):
    folder=root/name
    if folder.is_dir():
     for p in folder.rglob('*.json'):
       rid=key(str(p.resolve()))[:24];resources[rid]={'id':rid,'name':p.name,'path':str(p),'category':'workflow','bytes':p.stat().st_size,'base':'','tags':[],'installations':[fid],'selectable':False,'note':'可在完整 SD／原生模板匯入；畫布 JSON 請先在 ComfyUI 匯出 API 格式','format':'json'}
  with self.lock:
   self.folders,self.resources=folders,resources
   if not self.config['installation'] and folders:self.config['installation']=folders[0]['id']
  return self.state()

 def probe(self):
  url=local_url(self.config['url']);backend=self.config['backend']
  try:
   if backend=='a1111':
    models=api(url,'/sdapi/v1/sd-models');loras=api(url,'/sdapi/v1/loras');samplers=api(url,'/sdapi/v1/samplers')
    models=[{k:v for k,v in m.items() if k in ('title','filename','model_name','hash','sha256')} for m in models]
    loras=[{k:v for k,v in m.items() if k in ('name','alias','path')} for m in loras]
    try:vaes=api(url,'/sdapi/v1/sd-vae')
    except Exception:vaes=[]
    try:controls=api(url,'/controlnet/model_list')['model_list'];modules=api(url,'/controlnet/module_list')['module_list']
    except Exception:controls=[];modules=[]
    try:scripts=api(url,'/sdapi/v1/scripts')
    except Exception:scripts={}
    service={'ready':True,'models':models,'loras':loras,'samplers':[s['name'] for s in samplers],'vaes':vaes,'control_models':controls,'control_modules':modules,'scripts':scripts,'message':'本機 WebUI API 已連線'}
   else:
    info=api(url,'/object_info');needed={'CheckpointLoaderSimple','LoraLoader','CLIPTextEncode','KSampler','VAEDecode','SaveImage','EmptyLatentImage','LoadImage','VAEEncode'}
    if not needed.issubset(info):raise ValueError('ComfyUI 缺少基本工作流節點')
    choose=lambda node,arg:info[node]['input']['required'][arg][0]
    service={'ready':True,'models':choose('CheckpointLoaderSimple','ckpt_name'),'loras':choose('LoraLoader','lora_name'),
     'samplers':choose('KSampler','sampler_name'),'vaes':choose('VAELoader','vae_name') if 'VAELoader' in info else [],'control_models':choose('ControlNetLoader','control_net_name') if {'ControlNetLoader','ControlNetApplyAdvanced'}.issubset(info) else [],'message':'本機 ComfyUI API 已連線'}
  except Exception as exc:service={'ready':False,'models':[],'loras':[],'samplers':[],'vaes':[],'message':'尚未連線。請以 API 模式啟動所選 SD；資料夾存在不等於服務可用。','diagnostic':type(exc).__name__+': '+str(exc)[:200]}
  with self.lock:self.services[url]=service;self.auto_seen.clear()
  return self.state()

 def state(self):
  with self.lock:
   return {'config':copy.deepcopy(self.config),'folders':copy.deepcopy(self.folders),
    'background_runtimes':[{'label':f['label'],'path':str(p)} for f in self.folders for p in ([Path(f['path'])/'venv/Scripts/python.exe'] if f['backend']=='a1111' else [Path(f['path']).parent/'python_embeded/python.exe']) if p.is_file()],
    'resources':list(copy.deepcopy(self.resources).values()),'service':copy.deepcopy(self.services.get(self.config['url'],{'ready':False,'message':'請測試 SD 連線'})),
    'portrait_library':[{'id':n,**{k:v for k,v in t.items() if k not in ('source','signature')}} for n,t in self.portrait_library.items()],
    'native_templates':[{'id':n,**{k:t[k] for k in ('title','backend','output','bindings','installation')}} for n,t in self.native_templates.items()],
    'jobs':[self._public_job(j) for j in list(self.jobs.values())[-80:]],'expression_labels':LABELS,
    'limits':{'worker':1,'queue':12,'frame_count':12,'portrait_count':len(self.config['expressions'])}}

 def launch(self,installation=None,url=None):
  import subprocess
  url=local_url(url or self.config['url']);installation=installation or self.config['installation']
  folder=next((f for f in self.folders if f['id']==installation),None)
  if not folder:raise ValueError('未知 SD 安裝')
  try:
   with request.build_opener(_NoRedirect).open(url+'/',timeout=3) as r:
    if 'text/html' in r.headers.get('Content-Type',''):
     return {**self.state(),'native_message':'完整 SD 介面已啟動，可開啟視窗。'}
  except Exception:pass
  root=Path(folder['path']);port=str(parse.urlsplit(url).port)
  # Never kill or replace another user's server. A live API-only service needs
  # a free port or manual restart; our shipped launcher now starts the full UI.
  try:
   api(url,'/system_stats' if folder['backend']=='comfyui' else '/sdapi/v1/samplers')
  except Exception:pass
  else:raise ValueError('此連接埠是 API-only 服務；請以完整模式重啟，或為完整 SD 選另一個本機連接埠')
  if folder['backend']=='a1111':
   executable=root/'venv/Scripts/python.exe';script=root/'launch.py'
   args=['--api','--port',port,'--server-name','127.0.0.1','--skip-prepare-environment','--skip-install','--no-gradio-queue']
  else:
   candidates=[root.parent/'python_embeded/python.exe',root/'venv/Scripts/python.exe',root/'.venv/Scripts/python.exe']
   executable=next((p for p in candidates if p.is_file()),candidates[0]);script=root/'main.py'
   args=['--listen','127.0.0.1','--port',port,'--disable-auto-launch','--disable-xformers','--use-pytorch-cross-attention']
  if not executable.is_file() or not script.is_file():raise ValueError('找不到此安裝的既有 Python 或啟動程式；請先手動啟動 SD，遊戲不會自動安裝套件。')
  previous=self.sd_processes.get(url)
  if previous and previous.poll() is None:raise ValueError('SD 正在背景啟動，稍後按測試連線；不要重複啟動。')
  log=self.root/'sd-startup.log'
  with log.open('ab') as output:
   self.sd_processes[url]=subprocess.Popen([str(executable),'-X','utf8',str(script),*args],cwd=root,stdout=output,stderr=output,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
  return {**self.state(),'native_message':'完整 SD 已在背景啟動，保留原有擴充與節點；稍後開啟視窗。啟動紀錄：'+str(log)}

 def native_prepare(self,data):
  backend=self.config['backend'];document=data.get('document');title=data.get('title') or '原生固定模板'
  if data.get('png'):
   from PIL import Image
   raw=base64.b64decode(data['png'],validate=True)
   if len(raw)>3*1024*1024:raise ValueError('PNG 請小於 3 MB，較大圖片可改貼 PNG Info 文字')
   with Image.open(io.BytesIO(raw)) as im:
    if im.format!='PNG':raise ValueError('請使用原生 SD 輸出的 PNG')
    info=im.info
   if backend=='comfyui':
    if not info.get('prompt'):raise ValueError('PNG 沒有 ComfyUI API 節點圖，請改匯入 Export (API) JSON')
    document=json.loads(info['prompt'])
   else:
    if not info.get('parameters'):raise ValueError('PNG 沒有原生生成參數；請改貼 PNG Info 文字或 API payload')
    document={'infotext':info['parameters']}
  if isinstance(document,str):
   try:document=json.loads(document)
   except ValueError:document={'infotext':document} if backend=='a1111' else None
  if not isinstance(document,dict):raise ValueError('請貼上完整參數 JSON／PNG Info 或 ComfyUI API JSON')
  if 'payload' in document and 'backend' in document:
   draft=copy.deepcopy(document);draft.pop('id',None);draft.pop('installation',None);draft['title']=title
  else:
   if backend=='comfyui' and isinstance(document.get('prompt'),dict):document=document['prompt']
   draft={'title':title,'backend':backend,'payload':document,'bindings':sd_templates.infer(document) if backend=='comfyui' and 'nodes' not in document else {},'output':''}
   if backend=='comfyui':
    outputs=[n for n,v in document.items() if isinstance(v,dict) and v.get('class_type') in ('SaveImage','PreviewImage')]
    if len(outputs)==1:draft['output']=outputs[0]
  return {**self.state(),'native_draft':draft}

 def native_save(self,data):
  backend=self.config['backend'];info=None;fields=None
  if backend=='comfyui':info=api(local_url(self.config['url']),'/object_info',timeout=15)
  else:
   spec=api(local_url(self.config['url']),'/openapi.json',timeout=15);schema=spec['components']['schemas'];fields=set()
   for route in ('txt2img','img2img'):
    ref=spec['paths']['/sdapi/v1/'+route]['post']['requestBody']['content']['application/json']['schema']['$ref'].split('/')[-1]
    fields.update(schema[ref]['properties'])
  template=sd_templates.validate(data,backend,BLOCKED,info,fields);template['installation']=self.config['installation'];tid=key(template)
  with self.lock:
   if tid not in self.native_templates and len(self.native_templates)>=32:raise ValueError('最多保存 32 份原生模板，請先刪除不需要的模板')
   self.native_templates[tid]=template;atomic(self.native_path,self.native_templates)
  return {**self.state(),'native_saved':tid}

 def native_select(self,data):
  choices=data.get('selections') if 'selections' in data else {data.get('kind'):data.get('id')}
  if not isinstance(choices,dict) or not choices or set(choices)-set(TEMPLATES):raise ValueError('請選擇立繪、像素或 CG')
  with self.lock:
   for kind,tid in choices.items():
    if not isinstance(tid,str):raise ValueError('無效模板 ID')
    t=self.native_templates.get(tid)
    if tid and (not t or t['backend']!=self.config['backend'] or t['installation']!=self.config['installation']):raise ValueError('模板與目前 SD 安裝不相同，請先切換 SD 連線')
    if tid and t['backend']=='comfyui' and (not {'reference','denoise'}.issubset(t['bindings']) or kind=='pixel' and self.config['pixel_guide']=='controlnet' and 'control' not in t['bindings']):raise ValueError('遊戲差分需綁定 reference 與 denoise；骨架模式的像素模板另需 control 綁定。請在原生 SD 完成圖生圖工作流')
   self.config['native_selected'].update(choices);atomic(self.config_path,self.config);self.auto_seen.clear()
  return self.state()

 def native_read(self,tid):
  if tid not in self.native_templates:raise ValueError('找不到原生模板')
  return {**self.state(),'native_draft':{k:v for k,v in copy.deepcopy(self.native_templates[tid]).items() if k!='installation'}}

 def native_delete(self,tid):
  with self.lock:
   if tid not in self.native_templates:raise ValueError('找不到原生模板')
   if tid in self.config['native_selected'].values():raise ValueError('請先將使用中的生成用途切回內建模板，再刪除')
   del self.native_templates[tid];atomic(self.native_path,self.native_templates)
  return self.state()

 def native_history(self,tid=None):
  if self.config['backend']!='comfyui':raise ValueError('生成紀錄擷取限 ComfyUI；WebUI 請匯入原圖或 PNG Info')
  history=api(local_url(self.config['url']),'/history'+('/'+parse.quote(tid,safe='') if tid else '?max_items=20'),timeout=15)
  if tid:
   record=history.get(tid)
   if not record or not record.get('outputs'):raise ValueError('請選擇已完成且有圖片輸出的紀錄')
   result=self.native_prepare({'document':record['prompt'][2],'title':'ComfyUI 已完成工作流'})
   image_outputs=[n for n,v in record['outputs'].items() if v.get('images')]
   if len(image_outputs)==1:result['native_draft']['output']=image_outputs[0]
   return result
  return {**self.state(),'native_history':[{'id':n,'nodes':len(v.get('prompt',[None,None,{}])[2]),'images':sum(len(x.get('images',[])) for x in v.get('outputs',{}).values())} for n,v in history.items() if v.get('outputs')]}

 def native_resource(self,rid):
  r=self.resources.get(rid)
  if not r or r['category']!='workflow' or self.config['installation'] not in r['installations']:raise ValueError('請選擇目前安裝的既有工作流')
  folder=next(f for f in self.folders if f['id']==self.config['installation']);path=Path(r['path']).resolve()
  if not path.is_relative_to(Path(folder['path']).resolve()) or path.stat().st_size>2*1024*1024:raise ValueError('工作流需位於所選 SD 安裝內，且小於 2 MB')
  return self.native_prepare({'title':path.stem[:100],'document':json.loads(path.read_text(encoding='utf-8'))})

 def _public_job(self,j):
  return {k:copy.deepcopy(v) for k,v in j.items() if k not in ('recipe',)}

 def _resource(self,rid,category=None):
  r=self.resources.get(rid)
  if not r or (category and r['category']!=category) or not r['selectable'] or self.config['installation'] not in r['installations']:raise ValueError('請選擇此安裝中的可用本機資源')
  if not Path(r['path']).is_file():raise ValueError('模型檔案已不存在，請重新掃描')
  return r

 def configure(self,data):
  allowed={'installation','backend','url','checkpoint','vae','sampler','scheduler','auto','pixel_guide','control_model','control_weight','palette','palette_reference','remove_background','background_tolerance','background_method','background_model','background_device','background_resolution','expressions','templates','profiles','outfit_loras'}
  if not isinstance(data,dict) or set(data)-allowed:raise ValueError('未知的設定欄位')
  new=copy.deepcopy(self.config);new.update(copy.deepcopy(data))
  folder=next((f for f in self.folders if f['id']==new['installation']),None)
  if not folder or new['backend']!=folder['backend']:raise ValueError('請選擇正確的 SD 安裝與引擎')
  if new['installation']!=self.config['installation']:
   new['native_selected']={k:v if v in self.native_templates and self.native_templates[v]['installation']==new['installation'] else '' for k,v in new['native_selected'].items()}
  local_url(new['url'])
  if type(new['auto']) is not bool or type(new['remove_background']) is not bool or type(new['palette_reference']) is not bool:raise ValueError('無效開關')
  if new['pixel_guide'] not in ('controlnet','lpc','identity'):raise ValueError('未知的像素姿勢參考方式')
  if type(new['control_weight']) not in (int,float) or not .1<=new['control_weight']<=1.5:raise ValueError('ControlNet 權重需為 0.1–1.5')
  if new['background_method'] not in ('edge','rmbg') or new['background_device'] not in ('cpu','cuda') or new['background_resolution'] not in (512,768,1024):raise ValueError('無效去背方式或設備')
  if new['palette'] not in (16,32,48,64,128,256) or type(new['background_tolerance']) is not int or not 1<=new['background_tolerance']<=80:raise ValueError('無效像素後製設定')
  if not isinstance(new['expressions'],list) or not new['expressions'] or len(set(new['expressions']))!=len(new['expressions']) or 'neutral' not in new['expressions'] or any(e not in EXPRESSIONS for e in new['expressions']):raise ValueError('差分需包含平常，且不得重複')
  new['expressions']=['neutral']+[e for e in new['expressions'] if e!='neutral']
  if set(new['templates'])=={'portrait','pixel'}:new['templates']['cg']=copy.deepcopy(TEMPLATES['cg'])
  if set(new['templates'])!=set(TEMPLATES):raise ValueError('必須有立繪、像素與一般 CG 模板')
  for t in new['templates'].values():
   if set(t)!=set(TEMPLATES['portrait']):raise ValueError('模板欄位不完整')
   for field in ('prompt','negative'):
    if not isinstance(t[field],str) or not 1<=len(t[field])<=6000 or re.search(r'<lora:|<lyco:',t[field],re.I):raise ValueError('模板禁止手寫 LoRA 標籤，請用選單')
   if any(type(t[k]) is not int or not 256<=t[k]<=1536 or t[k]%64 for k in ('width','height')):raise ValueError('尺寸需為 256–1536 的 64 倍數')
   if type(t['steps']) is not int or not 1<=t['steps']<=60 or not 1<=t['cfg']<=15 or not .05<=t['denoise']<=.95:raise ValueError('Steps／CFG／差分重繪幅度超出範圍')
   if BLOCKED.search(t['prompt']):raise ValueError('目前只開放 SFW 模板')
   # Only known substitutions; no attribute/path interpolation.
   try:
    for _,name,spec,conversion in string.Formatter().parse(t['prompt']):
     if name is not None and (name not in {'identity','outfit','expression','direction','pose','scene'} or spec or conversion):raise ValueError('unknown template field')
   except (KeyError,ValueError,AttributeError,IndexError):raise ValueError('模板只接受 identity/outfit/expression/direction/pose/scene 變數')
  if not isinstance(new['profiles'],dict) or set(new['profiles'])-set(ACTORS):raise ValueError('未知角色')
  if not isinstance(new['outfit_loras'],dict) or set(new['outfit_loras'])-{'swim-onepiece','swim-trunks'}:raise ValueError('未知泳裝綁定')
  for p in new['outfit_loras'].values():
   if set(p)!={'lora','weight','trigger'} or not isinstance(p['lora'],str) or type(p['weight']) not in (int,float) or not 0<p['weight']<=1.5 or not isinstance(p['trigger'],str) or len(p['trigger'])>300 or BLOCKED.search(p['trigger']) or '<' in p['trigger']:raise ValueError('無效泳裝 LoRA 設定')
  for actor,p in new['profiles'].items():
   if set(p)!={'identity','trigger','lora','weight','clothes_lora','clothes_weight','seed','auto','expression'}:raise ValueError('角色設定欄位不完整')
   if any(not isinstance(p[k],str) or len(p[k])>1600 or '<' in p[k] or BLOCKED.search(p[k]) for k in ('identity','trigger')):raise ValueError('角色描述／觸發詞需為成年日常 SFW 內容')
   if type(p['seed']) is not int or not 0<=p['seed']<=4294967295 or type(p['auto']) is not bool or not 0<=p['weight']<=1.5 or not 0<=p['clothes_weight']<=1.5 or p['expression'] not in EXPRESSIONS:raise ValueError('角色 Seed／LoRA 權重／差分無效')
  if not isinstance(new['sampler'],str) or not 0<len(new['sampler'])<=80 or not isinstance(new['scheduler'],str) or len(new['scheduler'])>80:raise ValueError('無效採樣器')
  with self.lock:
   old=self.config;self.config=new
   try:
    if new['checkpoint']:self._resource(new['checkpoint'],'checkpoint')
    if new['vae']:self._resource(new['vae'],'vae')
    if new['control_model']:self._resource(new['control_model'],'controlnet')
    if new['background_model']:
     r=self.resources.get(new['background_model'])
     if not r or r['category']!='background' or not (Path(r['path']).parent/'birefnet.py').is_file():raise ValueError('需選本機完整 RMBG-2.0 模型')
    for p in new['profiles'].values():
     for k in ('lora','clothes_lora'):
      if p[k]:self._resource(p[k],'lora')
    for p in new['outfit_loras'].values():
     if p['lora']:self._resource(p['lora'],'lora')
   except Exception:self.config=old;raise
   atomic(self.config_path,self.config);self.auto_seen.clear()
  return self.state()

 def recipe(self,actor,outfit,outfit_prompt,kind,scene=None):
  if actor not in ACTORS or kind not in ('portrait','pixel','both','cg'):raise ValueError('未知角色／生成類型')
  if kind=='cg' and (not isinstance(scene,dict) or set(scene)!={'scene','place_name','description'} or any(not isinstance(x,str) or not 1<=len(x)<=1200 or BLOCKED.search(x) for x in scene.values())):raise ValueError('一般 CG 需要當下公開場景')
  c=copy.deepcopy(self.config);p=c['profiles'].get(actor)
  if not p:raise ValueError('請先保存此角色的身份與 LoRA 設定')
  if not p.get('lora'):raise ValueError('請先選擇角色 LoRA；服裝 LoRA 不能代替角色身份')
  p.pop('auto',None);p.pop('expression',None)
  authored=getattr(self,'actor_identities',{}).get(actor,{})
  if BLOCKED.search(authored.get('appearance','')):raise ValueError('外觀描述目前只支援成年 SFW 生圖')
  if authored.get('appearance'):p['identity']+=', '+authored['appearance']
  from .looks import look_prompt
  look_notes=look_prompt(authored.get('look'))
  if look_notes:p['identity']+=', '+look_notes
  swim=outfit['id'] in {'swim-onepiece','swim-trunks'}
  if swim:
   binding=c['outfit_loras'].get(outfit['id'],{})
   if not binding.get('lora'):raise ValueError('泳池生圖必須先在生圖設定綁定這套泳装的本機服裝 LoRA')
   p['clothes_lora']=binding['lora'];p['clothes_weight']=binding['weight'];outfit_prompt+=', '+binding.get('trigger','')
  checkpoint=self._resource(c['checkpoint'],'checkpoint')
  model_list=self.services.get(c['url'],{}).get('models',[])
  if not self.services.get(c['url'],{}).get('ready'):raise ValueError('請先測試並連接本機 SD API')
  loras=[]
  for field,weight in (('lora','weight'),('clothes_lora','clothes_weight')):
   if p[field]:loras.append({**self._resource(p[field],'lora'),'weight':p[weight]})
  if not loras:raise ValueError('請先選擇角色 LoRA；未綁定的角色不會自動生成')
  # Catch known incompatible training families before a costly render.
  for l in loras:
   a,b=family(checkpoint['base']),family(l['base'])
   if a and b and a!=b:raise ValueError('LoRA 與底模架構不相容')
  pose_reference=None
  if kind in ('pixel','both') and c['pixel_guide']=='lpc':
   directory=self.project/'prototype/web/assets';name=f'lpc-{actor}-{outfit["id"]}.png'
   path=directory/name
   if not path.is_file():path=directory/f'lpc-{actor}-original.png'
   if not path.is_file() or not path.resolve().is_relative_to(directory.resolve()):raise ValueError('此角色缺少 LPC 姿勢參考圖')
   raw=path.read_bytes();pose_reference={'name':path.name,'sha256':hashlib.sha256(raw).hexdigest(),'data':base64.b64encode(raw).decode(),'license':'LPC composed reference: CC-BY-SA 4.0; see LPC-CREDITS.txt'}
  wanted_loras={l['path'].replace('\\','/').lower() for l in loras}
  api_loras=self.services[c['url']].get('loras',[])
  if c['backend']=='a1111':
   api_loras=[l for l in api_loras if isinstance(l,dict) and str(l.get('path','')).replace('\\','/').lower() in wanted_loras]
   model_list=[m for m in model_list if isinstance(m,dict) and str(m.get('filename','')).replace('\\','/').lower()==checkpoint['path'].replace('\\','/').lower()]
  control=None
  if kind in ('pixel','both') and c['pixel_guide']=='controlnet':
   control=self._resource(c['control_model'],'controlnet')
   if not self.services[c['url']].get('control_models'):raise ValueError('所選 SD 服務缺少可用 ControlNet；請啟動內建 ControlNet 並測試連線')
   a,b=family(checkpoint['base']),family(control['base']) or family(control['name'])
   if a and b and a!=b:raise ValueError('姿勢 ControlNet 與底模架構不相容')
  background=None
  if kind!='cg' and c['remove_background'] and c['background_method']=='rmbg':
   background=copy.deepcopy(self.resources.get(c['background_model']))
   if not background or not Path(background['path']).is_file():raise ValueError('未找到本機 RMBG 權重')
  scoped={k:c[k] for k in ('installation','backend','url','sampler','scheduler','pixel_guide','control_weight','palette','palette_reference','remove_background','background_tolerance','background_method','background_model','background_device','background_resolution','templates','expressions')}
  used={'portrait','cg'} if kind=='cg' else {'portrait'} if kind=='portrait' else {'portrait','pixel'}
  scoped['templates']={k:v for k,v in c['templates'].items() if k in used}
  scoped['native_templates']={}
  for purpose in used:
   tid=c['native_selected'].get(purpose)
   if tid:
    native=self.native_templates.get(tid)
    if not native or native['installation']!=c['installation'] or native['backend']!=c['backend']:raise ValueError('使用中的原生模板與 SD 安裝不相同，請重新選擇')
    scoped['native_templates'][purpose]=copy.deepcopy(native)
  return {'pipeline_version':6,'age':authored.get('age',25),'gender':getattr(self,'actor_genders',{}).get(actor,'male' if actor=='player' else 'female'),'swim':swim,'actor':actor,'outfit':copy.deepcopy(outfit),'outfit_prompt':outfit_prompt,'kind':kind,'scene':copy.deepcopy(scene),'pose_reference':pose_reference,'control':control,'background':background,
   'profile':p,'config':scoped,**({'look':copy.deepcopy(authored['look'])} if authored.get('look',{}).get('enabled') else {}),
   'checkpoint':checkpoint,'vae':self._resource(c['vae'],'vae') if c['vae'] else None,'loras':loras,
   'api_models':copy.deepcopy(model_list),'api_loras':copy.deepcopy(api_loras),
   'api_vaes':copy.deepcopy(self.services[c['url']].get('vaes',[])),
   'api_control_models':copy.deepcopy(self.services[c['url']].get('control_models',[]))}

 def submit(self,actor,outfit,outfit_prompt,kind='both',scene=None):
  with self.lock:
   recipe=self.recipe(actor,outfit,outfit_prompt,kind,scene)
   if kind=='cg':recipe['scene_nonce']=secrets.token_hex(4)
   jid=key(recipe)
   previous=self.jobs.get(jid)
   if previous and previous['status'] not in ('failed','cancelled','interrupted'):return self._public_job(previous)
   if len(self.pending)>=12:raise ValueError('生成佇列已滿，請等目前任務完成')
   total=2 if kind=='cg' else (len(recipe['config']['expressions']) if kind in ('both','portrait') else 1 if kind=='pixel' and recipe['config']['pixel_guide']=='controlnet' else 0)+(12 if kind in ('both','pixel') else 0)
   job={'id':jid,'actor':actor,'kind':kind,'outfit':outfit,'scene':copy.deepcopy(scene),'status':'queued','done':0,'total':total,'cancel':False,'created':int(time.time()),'message':'等待本機 GPU','files':{},'recipe':recipe}
   self.jobs[jid]=job;self.pending.append(jid);self._persist();return self._public_job(job)

 def maybe_auto(self,appearances):
  if not self.config['auto']:return
  for actor,outfit,prompt in appearances:
   p=self.config['profiles'].get(actor,{})
   signature=(actor,outfit['render_key'],key({'profile':{k:v for k,v in p.items() if k not in {'auto','expression'}},'authored':getattr(self,'actor_identities',{}).get(actor,{}),'gender':getattr(self,'actor_genders',{}).get(actor)}))
   if p.get('auto') and p.get('lora') and signature not in self.auto_seen:
    self.auto_seen.add(signature)
    try:self.submit(actor,outfit,prompt,'both')
    except ValueError:pass

 def _persist(self):
  atomic(self.root/'jobs.json',list(self.jobs.values()))

 def cancel(self,jid):
  with self.lock:
   if jid not in self.jobs:raise ValueError('找不到任務')
   j=self.jobs[jid]
   if j['status'] in ('queued','running'):j['cancel']=True;j['message']='收到取消；目前單張完成後停止，不會中斷其他人在 SD 的任務。'
   self._persist()
  return self.state()

 def activate(self,jid,expression='neutral'):
  with self.lock:
   j=self.jobs.get(jid)
   if not j or j['status']!='ready' or expression not in EXPRESSIONS:raise ValueError('只能套用已完成的素材')
   if 'portraits' in j['files'] and expression not in j['files']['portraits']:raise ValueError('此差分尚未生成')
   scope=j['actor']+':'+j['outfit']['render_key'];active=copy.deepcopy(self.config['active'].get(scope,{}))
   if 'sprite' in j['files']:active['sprite']=j['files']['sprite'];active['frames']=3
   if 'portraits' in j['files']:active['portraits']=j['files']['portraits'];active['expression']=expression
   if j.get('recipe',{}).get('look'):active['look_signature']=key(j['recipe']['look'])
   else:active.pop('look_signature',None)
   active['job']=jid;self.config['active'][scope]=active;atomic(self.config_path,self.config)
  return self.state()

 def appearance(self,actor,outfit):
  with self.lock:
   active=self.config['active'].get(actor+':'+outfit['render_key'],{})
   look=getattr(self,'actor_identities',{}).get(actor,{}).get('look')
   if look and look.get('enabled') and active.get('look_signature')!=key(look):return {}
   result={}
   if active.get('sprite') and (self.assets/active['sprite']).is_file():result.update(sprite='/character-art/'+active['sprite'],frames=active.get('frames',3))
   portrait=active.get('portraits',{}).get(active.get('expression','neutral'))
   if portrait and (self.assets/portrait).is_file():result['portrait']='/character-art/'+portrait
   return result

 def asset(self,name):
  if not re.fullmatch(r'[0-9a-f]{64}-(?:portrait-[a-z]+|sprite|cg)\.png',name):return None
  with self.lock:
   allowed=set()
   for j in self.jobs.values():
    if j['status']=='ready':
     allowed.update(j['files'].get('portraits',{}).values())
     if j['files'].get('sprite'):allowed.add(j['files']['sprite'])
     if j['files'].get('cg'):allowed.add(j['files']['cg'])
   allowed.update(t['file'] for t in self.portrait_library.values())
   path=self.assets/name
   return path if name in allowed and path.is_file() else None

 def _worker(self):
  while not self.closed:
   with self.lock:jid=self.pending.popleft() if self.pending else None
   if jid is None:time.sleep(.25);continue
   job=self.jobs[jid]
   try:
    if job['cancel']:raise InterruptedError()
    with self.lock:job.update(status='running',message='正在本機生成');self._persist()
    self._generate(job)
    with self.lock:job.update(status='ready',message='完成；請預覽差分，再套用到遊戲。');self._persist()
   except InterruptedError:
    with self.lock:job.update(status='cancelled',message='已取消；未套用不完整素材。');self._persist()
   except Exception as exc:
    with self.lock:job.update(status='failed',message=str(exc)[:500] or 'SD 生成失敗；請確認底模與 LoRA 相容、GPU 和服務狀態。');self._persist()

 def _a1111_name(self,resource,items,field):
  for item in items:
   if isinstance(item,dict) and str(item.get('filename',item.get('path',''))).replace('\\','/').lower()==resource['path'].replace('\\','/').lower():return item.get(field) or item.get('name')
  raise ValueError('模型在資料夾中，但所選 SD API 未載入它；請確認服務使用同一資料夾並重新掃描模型。')

 def _comfy_name(self,resource,items):
  matches=[s for s in items if isinstance(s,str) and s.replace('\\','/').rsplit('/',1)[-1]==resource['name']]
  if len(matches)!=1:raise ValueError('ComfyUI 模型名稱未找到或有同名衝突，請調整模型路徑')
  return matches[0]

 def _render(self,recipe,t,prompt,seed,reference=None,control=None):
  c=recipe['config'];backend=c['backend'];url=c['url'];p=recipe['profile']
  negative=t['negative']+', '+NEGATIVE
  if recipe.get('swim'):
   for phrase in ('bare shoulders','backless outfit','exposed back','open back clothes'):negative=negative.replace(phrase,'')
  if backend=='a1111':
   model=self._a1111_name(recipe['checkpoint'],recipe['api_models'],'title')
   for l in recipe['loras']:
    name=self._a1111_name(l,recipe['api_loras'],'name')
    if any(x in name for x in '<>:'):raise ValueError('LoRA 名稱無法用安全標籤引用')
    prompt+=f' <lora:{name}:{l["weight"]}>'
   overrides={'sd_model_checkpoint':model}
   if recipe['vae']:overrides['sd_vae']=self._a1111_name(recipe['vae'],recipe['api_vaes'],'model_name')
   payload={'prompt':prompt,'negative_prompt':negative,'seed':seed,'steps':t['steps'],'cfg_scale':t['cfg'],
    'width':t['width'],'height':t['height'],'sampler_name':c['sampler'],'scheduler':c['scheduler'],
    'batch_size':1,'n_iter':1,'override_settings':overrides,'override_settings_restore_afterwards':True,'send_images':True,'save_images':False}
   native=t.get('_native')
   if native:
    imported=sd_templates.mapped_payload(native,{'prompt':prompt,'negative':negative,'seed':seed,'checkpoint':model,'lora':self._a1111_name(recipe['loras'][0],recipe['api_loras'],'name'),'lora_weight':recipe['loras'][0]['weight']})
    # Infotext is parsed by the installed WebUI, including its plugin fields.
    # Do not overwrite those native values with our basic defaults.
    if imported.get('infotext'):
     payload={k:v for k,v in payload.items() if k not in {'width','height','steps','cfg_scale','sampler_name','scheduler'}}
    payload.update(imported)
    payload.update(prompt=prompt,negative_prompt=negative,seed=seed,batch_size=1,n_iter=1,send_images=True,save_images=False,override_settings_restore_afterwards=True)
    payload['override_settings']={**(imported.get('override_settings') or {}),**overrides}
   if reference:payload.update(init_images=[base64.b64encode(reference).decode()],denoising_strength=t['denoise'])
   if control:
    matches=[n for n in recipe['api_control_models'] if n.split(' [')[0].lower()==Path(recipe['control']['path']).stem.lower()]
    if len(matches)!=1:raise ValueError('API 未載入所選姿勢 ControlNet，請重新測試連線')
    scripts=payload.setdefault('alwayson_scripts',{});cn=next((n for n in scripts if n.lower()=='controlnet'),'controlnet')
    if native and 'control' in native['bindings']:
     for path in native['bindings']['control']:sd_templates.pointer(payload,path,base64.b64encode(control).decode(),True)
    else:scripts.setdefault(cn,{'args':[]})['args'].append({'enabled':True,'module':'None','model':matches[0],'image':base64.b64encode(control).decode(),'weight':c['control_weight'],'guidance_start':0,'guidance_end':1,'resize_mode':0,'pixel_perfect':False})
   result=api(url,'/sdapi/v1/img2img' if reference else '/sdapi/v1/txt2img',payload,timeout=300)
   image=base64.b64decode(result['images'][0].split(',')[-1],validate=True)
  else:
   if t.get('_native'):return self._render_native_comfy(recipe,t,prompt,negative,seed,reference,control)
   model=self._comfy_name(recipe['checkpoint'],recipe['api_models']);g={}
   def node(n,kind,inputs):g[str(n)]={'class_type':kind,'inputs':inputs};return [str(n),0]
   node(1,'CheckpointLoaderSimple',{'ckpt_name':model});model_ref=['1',0];clip_ref=['1',1];vae_ref=['1',2]
   for i,l in enumerate(recipe['loras']):
    n=10+i;node(n,'LoraLoader',{'model':model_ref,'clip':clip_ref,'lora_name':self._comfy_name(l,recipe['api_loras']),'strength_model':l['weight'],'strength_clip':l['weight']});model_ref=[str(n),0];clip_ref=[str(n),1]
   if recipe['vae']:vae_ref=node(8,'VAELoader',{'vae_name':self._comfy_name(recipe['vae'],recipe['api_vaes'])})
   pos=node(2,'CLIPTextEncode',{'text':prompt,'clip':clip_ref});neg=node(3,'CLIPTextEncode',{'text':negative,'clip':clip_ref})
   def upload(raw_image):
    boundary='lifebox'+key(raw_image.hex())[:20];filename='lifebox-'+key(raw_image.hex())+'.png'
    raw=(f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{filename}"\r\nContent-Type: image/png\r\n\r\n'.encode()+raw_image+f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="type"\r\n\r\ninput\r\n--{boundary}--\r\n'.encode())
    uploaded=api(url,'/upload/image',raw=raw,content_type='multipart/form-data; boundary='+boundary)
    return ('/'.join([uploaded.get('subfolder',''),uploaded['name']])).lstrip('/')
   if control:
    cn=node(21,'ControlNetLoader',{'control_net_name':self._comfy_name(recipe['control'],recipe['api_control_models'])})
    guide=node(20,'LoadImage',{'image':upload(control)})
    node(22,'ControlNetApplyAdvanced',{'positive':pos,'negative':neg,'control_net':cn,'image':guide,'strength':c['control_weight'],'start_percent':0.0,'end_percent':1.0});pos=['22',0];neg=['22',1]
   if reference:
    boundary='lifebox'+key(reference.hex())[:20];filename='lifebox-'+key(reference.hex())+'.png'
    raw=(f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{filename}"\r\nContent-Type: image/png\r\n\r\n'.encode()+reference+f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="type"\r\n\r\ninput\r\n--{boundary}--\r\n'.encode())
    uploaded=api(url,'/upload/image',raw=raw,content_type='multipart/form-data; boundary='+boundary)
    image_ref=node(9,'LoadImage',{'image':('/'.join([uploaded.get('subfolder',''),uploaded['name']])).lstrip('/')})
    latent=node(4,'VAEEncode',{'pixels':image_ref,'vae':vae_ref})
   else:latent=node(4,'EmptyLatentImage',{'width':t['width'],'height':t['height'],'batch_size':1})
   scheduler=c['scheduler'].lower();scheduler='normal' if scheduler=='automatic' else scheduler
   sampled=node(5,'KSampler',{'model':model_ref,'positive':pos,'negative':neg,'latent_image':latent,'seed':seed,'steps':t['steps'],'cfg':t['cfg'],'sampler_name':c['sampler'],'scheduler':scheduler,'denoise':t['denoise'] if reference else 1.0})
   decoded=node(6,'VAEDecode',{'samples':sampled,'vae':vae_ref});node(7,'SaveImage',{'images':decoded,'filename_prefix':'LifeBox/character'})
   submitted=api(url,'/prompt',{'prompt':g,'client_id':'lifebox-character-studio'},timeout=10)
   if 'prompt_id' not in submitted:raise ValueError('ComfyUI 拒絕工作流：'+str(submitted.get('node_errors',{}))[:250])
   pid=submitted['prompt_id'];deadline=time.monotonic()+300;record={}
   while time.monotonic()<deadline:
    history=api(url,'/history/'+parse.quote(pid),timeout=6);record=history.get(pid,{})
    if record.get('status',{}).get('status_str')=='error':raise ValueError('ComfyUI 工作流失敗，請查看 SD 視窗的 GPU／模型錯誤')
    if record.get('outputs',{}).get('7',{}).get('images'):break
    time.sleep(1)
   else:raise TimeoutError('ComfyUI 單張生成超過 300 秒')
   meta=record['outputs']['7']['images'][0];query=parse.urlencode({k:meta[k] for k in ('filename','subfolder','type')})
   req=request.Request(url+'/view?'+query)
   with request.build_opener(_NoRedirect).open(req,timeout=20) as r:image=r.read(16*1024*1024+1)
  if not 8<len(image)<=16*1024*1024 or not image.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('SD 沒有回傳有效 PNG')
  return image

 def _render_native_comfy(self,recipe,t,prompt,negative,seed,reference,control):
  url=local_url(recipe['config']['url']);native=t['_native'];bindings=native['bindings']
  if not {'reference','denoise'}.issubset(bindings):raise ValueError('原生工作流未綁定圖生圖 reference／denoise，請回完整 SD 完成工作流')
  if control and 'control' not in bindings:raise ValueError('原生像素工作流缺少 control 骨架圖片綁定')
  def upload(raw):
   boundary='lifebox'+key(raw.hex())[:20];filename='lifebox-'+key(raw.hex())+'.png'
   body=(f'--{boundary}\r\nContent-Disposition: form-data; name="image"; filename="{filename}"\r\nContent-Type: image/png\r\n\r\n'.encode()+raw+f'\r\n--{boundary}\r\nContent-Disposition: form-data; name="type"\r\n\r\ninput\r\n--{boundary}--\r\n'.encode())
   result=api(url,'/upload/image',raw=body,content_type='multipart/form-data; boundary='+boundary)
   return '/'.join([result.get('subfolder',''),result['name']]).lstrip('/')
  if reference is None:
   from PIL import Image
   buf=io.BytesIO();Image.new('RGB',(t['width'],t['height']),'white').save(buf,format='PNG');reference_name=upload(buf.getvalue())
  else:reference_name=upload(reference)
  values={'prompt':prompt,'negative':negative,'seed':seed,'checkpoint':self._comfy_name(recipe['checkpoint'],recipe['api_models']),
   'lora':self._comfy_name(recipe['loras'][0],recipe['api_loras']),'lora_weight':recipe['loras'][0]['weight'],
   'reference':reference_name,'denoise':t['denoise'] if reference else 1.0,'width':t['width'],'height':t['height']}
  if control:values['control']=upload(control)
  if len(recipe['loras'])>1:
   if not {'clothes_lora','clothes_weight'}.issubset(bindings):raise ValueError('角色使用服裝 LoRA，但原生模板沒有服裝 LoRA 與權重綁定')
   values.update(clothes_lora=self._comfy_name(recipe['loras'][1],recipe['api_loras']),clothes_weight=recipe['loras'][1]['weight'])
  elif 'clothes_weight' in bindings:values['clothes_weight']=0.0
  graph=sd_templates.mapped_payload(native,values)
  # Check the current running installation again, not just the import snapshot.
  sd_templates.validate({k:v for k,v in native.items() if k!='installation'},'comfyui',BLOCKED,api(url,'/object_info',timeout=15))
  submitted=api(url,'/prompt',{'prompt':graph,'client_id':'lifebox-native-template'},timeout=15)
  if not submitted.get('prompt_id'):raise ValueError('ComfyUI 拒絕原生工作流：'+str(submitted.get('node_errors',{}))[:250])
  pid=submitted['prompt_id'];deadline=time.monotonic()+300;output=native['output']
  while time.monotonic()<deadline:
   record=api(url,'/history/'+parse.quote(pid,safe=''),timeout=8).get(pid,{})
   if record.get('status',{}).get('status_str')=='error':raise ValueError('ComfyUI 原生模板失敗，請查看原生視窗的節點錯誤')
   images=record.get('outputs',{}).get(output,{}).get('images')
   if images:break
   if record.get('status',{}).get('completed'):raise ValueError('工作流已完成，但所選輸出節點沒有圖片；請選 SaveImage 或 PreviewImage')
   time.sleep(1)
  else:raise TimeoutError('ComfyUI 原生工作流單張生成超過 300 秒')
  meta=images[0];query=parse.urlencode({k:meta[k] for k in ('filename','subfolder','type')})
  with request.build_opener(_NoRedirect).open(url+'/view?'+query,timeout=20) as r:image=r.read(16*1024*1024+1)
  if not 8<len(image)<=16*1024*1024 or not image.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('原生工作流沒有回傳 PNG 圖片')
  return image

 def _cutout(self,raw,c,pixel=False):
  from PIL import Image, ImageChops
  im=Image.open(io.BytesIO(raw));im.load()
  if im.width>4096 or im.height>4096:raise ValueError('圖片尺寸超出限制')
  im=im.convert('RGBA')
  if c['remove_background']:
   # Flood only connected near-white background; enclosed pale clothes stay.
   from PIL import ImageDraw
   rgb=im.convert('RGB');rgb.thumbnail((768,1024));w,h=rgb.size;px=rgb.load();mask=Image.new('L',(w,h),255);mp=mask.load();q=deque()
   for x in range(w):q.append((x,0));q.append((x,h-1))
   for y in range(h):q.append((0,y));q.append((w-1,y))
   seen=bytearray(w*h);t=42 if c.get('background_method')=='rmbg' else c['background_tolerance']
   corners=[px[x,y] for x,y in ((0,0),(w-1,0),(0,h-1),(w-1,h-1))]
   # A white-background model often returns uniform light grey/cream instead.
   samples=[v for v in corners if min(v)>180 and max(v)-min(v)<45] or [(255,255,255)]
   while q:
    x,y=q.popleft();index=y*w+x
    if seen[index]:continue
    seen[index]=1
    r,g,b=px[x,y]
    if not any(max(abs(a-b) for a,b in zip((r,g,b),sample))<=t for sample in samples):continue
    mp[x,y]=0
    for xx,yy in ((x-1,y),(x+1,y),(x,y-1),(x,y+1)):
     if 0<=xx<w and 0<=yy<h and not seen[yy*w+xx]:q.append((xx,yy))
   alpha=mask.resize(im.size,Image.Resampling.NEAREST);im.putalpha(ImageChops.multiply(im.getchannel('A'),alpha))
  bounds=im.getbbox()
  if not bounds:raise ValueError('去背後角色為空；請調整白背景模板或容差')
  if pixel:
   body=im.crop(bounds);body.thumbnail((52,56),Image.Resampling.LANCZOS)
   body=body.quantize(colors=c['palette'],method=Image.Quantize.FASTOCTREE).convert('RGBA')
   result=Image.new('RGBA',(64,64));result.alpha_composite(body,((64-body.width)//2,60-body.height));return result
  return im

 def _pose_guide(self,recipe,direction,frame,t):
  from PIL import Image
  raw=base64.b64decode(recipe['pose_reference']['data']);sheet=Image.open(io.BytesIO(raw)).convert('RGBA')
  row={'up':0,'left':1,'down':2,'right':3}[direction];column=(0,2,6)[frame]
  pose=sheet.crop((column*64,row*64,(column+1)*64,(row+1)*64));box=pose.getbbox()
  if not box:raise ValueError('像素姿勢參考圖是空白')
  pose=pose.crop(box);scale=min(t['width']*.55/pose.width,t['height']*.85/pose.height)
  pose=pose.resize((round(pose.width*scale),round(pose.height*scale)),Image.Resampling.NEAREST)
  image=Image.new('RGB',(t['width'],t['height']),'white');image.paste(pose,((image.width-pose.width)//2,round(image.height*.92)-pose.height),pose)
  output=io.BytesIO();image.save(output,format='PNG');return output.getvalue()

 def _matte_batch(self,job,sources,names):
  import subprocess
  r=job['recipe'];c=r['config']
  if not r.get('background') or not c['remove_background']:return {}
  folder=Path(r['background']['path']).parent
  runtimes=[Path(f['path'])/'venv/Scripts/python.exe' for f in self.folders if f['backend']=='a1111']+[Path(f['path']).parent/'python_embeded/python.exe' for f in self.folders if f['backend']=='comfyui']
  executable=next((p for p in runtimes if p.is_file()),None)
  if not executable:raise ValueError('找不到既有 SD Python，RMBG 無法離線執行')
  target=sources/'matted';target.mkdir(exist_ok=True)
  records=[{'input':str((sources/name).resolve()),'output':str((target/name).resolve())} for name in names]
  manifest=sources/'matte-manifest.json';atomic(manifest,{'model':str(folder),'device':c['background_device'],'resolution':c['background_resolution'],'files':records})
  with self.lock:job['message']='使用本機 RMBG 去背；保留白色衣物與髮絲';self._persist()
  log=sources/'rmbg.log'
  with log.open('wb') as output:
   process=subprocess.Popen([str(executable),'-X','utf8',str(Path(__file__).with_name('rmbg_worker.py')),str(manifest.resolve())],stdout=output,stderr=output,creationflags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0)
   deadline=time.monotonic()+max(300,len(records)*45)
   try:
    while process.poll() is None:
     if job['cancel'] or self.closed:raise InterruptedError()
     if time.monotonic()>deadline:raise TimeoutError('本機 RMBG 去背超時，請改用 CPU／較小去背解析度')
     count=sum(Path(row['output']).is_file() for row in records)
     with self.lock:job['message']=f'RMBG 神經去背 {count}/{len(records)}';job['postprocessed']=count
     time.sleep(.5)
    if process.returncode:raise ValueError('本機 RMBG 無法完成去背；請檢查既有 SD 環境套件與模型，紀錄：'+str(log))
   finally:
    if process.poll() is None:process.terminate();process.wait(10)
  return {name:(target/name).read_bytes() for name in names}

 def _generate(self,job):
  from PIL import Image
  r=job['recipe'];p=r['profile'];c=r['config'];jid=job['id'];files={};seed=p['seed'];identity=('adult man' if r.get('gender')=='male' else 'adult woman')+' age '+str(r.get('age',25))+', '+p['identity']+', '+p['trigger'];outfit=r['outfit_prompt']+(', opaque athletic swimwear, nonsexual public swimming' if r.get('swim') else ', opaque daily clothes, long sleeves')
  portrait_signatures={};library_sources={}
  sources=self.root/'sources'/jid;sources.mkdir(parents=True,exist_ok=True)
  def generate(kind,variation,expression='',direction='',pose='',reference=None,control=None,denoise=None):
   if job['cancel'] or self.closed:raise InterruptedError()
   t=copy.deepcopy(c['templates'][kind]);prompt=t['prompt'].format(identity=identity,outfit=outfit,expression=expression,direction=direction,pose=pose,scene=(r.get('scene') or {}).get('description',''))
   if r.get('gender')=='male':prompt=prompt.replace('adult woman','adult man')
   if r.get('swim'):
    prompt=prompt.replace('fully clothed','wearing opaque athletic swimwear')
    for phrase in ('bare shoulders','backless outfit','exposed back','open back clothes'):t['negative']=t['negative'].replace(phrase,'')
   if kind in c.get('native_templates',{}):t['_native']=c['native_templates'][kind]
   if denoise is not None:t['denoise']=denoise
   cache=sources/(kind+'-'+variation+'.png')
   if kind=='portrait':
    signature=key({'actor':r['actor'],'outfit':r['outfit']['render_key'],'profile':{k:v for k,v in p.items() if k not in {'auto','expression'}},'gender':r.get('gender'),'checkpoint':r['checkpoint'],'vae':r['vae'],'loras':r['loras'],'template':t,'prompt':prompt,'reference_hash':hashlib.sha256(reference).hexdigest() if reference else None,'seed':seed,'variation':variation,'sampler':c['sampler'],'scheduler':c['scheduler'],'pipeline':6})
    portrait_signatures[variation]=signature;stored=self.portrait_library.get(signature)
    if stored:
     path=(self.root/stored['source']).resolve()
     if path.is_relative_to(self.root.resolve()) and path.is_file():library_sources[variation]=stored;cache.write_bytes(path.read_bytes())
   if cache.is_file():raw=cache.read_bytes()
   elif control:raw=self._render(r,t,prompt,seed,reference,control=control)
   else:raw=self._render(r,t,prompt,(seed^int(r['scene_nonce'],16)) if kind=='cg' and r.get('scene_nonce') else seed,reference)
   if not cache.is_file():cache.write_bytes(raw)
   with self.lock:job['done']+=1;job['message']=('重用立繪差分 ' if variation in library_sources and kind=='portrait' else '生成 ')+kind+' / '+variation;job['reused_portraits']=len(library_sources);self._persist()
   return raw
  images={};anchor=None
  if r['kind'] in ('portrait','both'):
   base=None
   for expression in c['expressions']:
    raw=generate('portrait',expression,expression=EXPRESSIONS[expression],reference=base)
    if expression=='neutral':base=raw;anchor=raw
    images[('portrait',expression)]=raw
  elif r['kind']=='cg' or r['kind']=='pixel' and c['pixel_guide']=='controlnet':
   anchor=generate('portrait','neutral',expression=EXPRESSIONS['neutral'])
   if r['kind']=='pixel':images[('portrait','neutral')]=anchor
  if r['kind']=='cg':
   from .sd_identity import identity_canvas
   t=c['templates']['cg'];raw=generate('cg','scene',reference=identity_canvas(anchor,t['width'],t['height']))
   name=jid+'-cg.png';Image.open(io.BytesIO(raw)).save(self.assets/name);files['cg']=name
  if r['kind'] in ('pixel','both'):
   base=None;directions={'down':'(front view, facing viewer:1.4)','up':'(back view, from behind, facing away:1.8), back of head, face not visible, (opaque closed back of coat:1.5), shoulders and entire back covered by brown outerwear','left':'(strict left side profile, looking left:1.8)','right':'(strict right side profile, looking right:1.8)'}
   if r.get('swim'):directions['up']='(back view, facing away:1.8), back of head, face not visible, opaque athletic swimsuit with a closed back'
   # Each direction/step has its own LPC pose reference when enabled. The SD
   # images are real img2img outputs, not mirrored frames or a guessed grid.
   for direction in ('down','up','left','right'):
    direction_base=None
    for frame,pose in enumerate(('standing idle pose','walking pose, left foot forward','walking pose, right foot forward')):
     control=None;denoise=None
     if c['pixel_guide']=='controlnet':
      from .sd_identity import pose_image,identity_canvas
      t=c['templates']['pixel'];control=pose_image(direction,frame,t['width'],t['height'])
      (sources/f'pose-{direction}-{frame}.png').write_bytes(control)
      reference=direction_base if frame else identity_canvas(anchor,t['width'],t['height'])
      denoise=.60 if frame else t['denoise'] if direction=='down' else min(.95,t['denoise']+.12)
     else:reference=self._pose_guide(r,direction,frame,c['templates']['pixel']) if r.get('pose_reference') else base
     raw=generate('pixel',direction+'-'+str(frame),direction=directions[direction],pose=pose,reference=reference,control=control,denoise=denoise)
     if base is None:base=raw
     if frame==0:direction_base=raw
     images[('pixel',direction+'-'+str(frame))]=raw
  names=[kind+'-'+variation+'.png' for kind,variation in images]
  mattes=self._matte_batch(job,sources,names) if r.get('background') else {}
  portraits={};frames={};metrics=[];palette_source=None
  for (kind,variation),raw in images.items():
   if job['cancel'] or self.closed:raise InterruptedError()
   raw=mattes.get(kind+'-'+variation+'.png',raw);processed=self._cutout(raw,c,kind=='pixel')
   if kind=='portrait':
    name=jid+'-portrait-'+variation+'.png';processed.save(self.assets/name);portraits[variation]=name
    signature=portrait_signatures.get(variation)
    if signature:
     self.portrait_library[signature]={'actor':r['actor'],'gender':r.get('gender','female'),'outfit':copy.deepcopy(r['outfit']),'expression':variation,'file':name,'url':'/character-art/'+name,'source':(sources/('portrait-'+variation+'.png')).relative_to(self.root).as_posix(),'signature':signature,'created':int(time.time())}
    if variation=='neutral':palette_source=processed
   else:
    if c.get('palette_reference') and c['pixel_guide']=='controlnet' and palette_source is not None:
     from .sd_identity import align_clothes_palette
     processed=align_clothes_palette(processed,palette_source).quantize(colors=c['palette'],method=Image.Quantize.FASTOCTREE).convert('RGBA')
    direction,frame=variation.rsplit('-',1);frames[direction,int(frame)]=processed
    bounds=processed.getbbox();metrics.append({'direction':direction,'frame':int(frame),'bounds':bounds,'feet_y':bounds[3] if bounds else None})
  if r['kind']=='cg' and anchor:
   signature=portrait_signatures.get('neutral')
   if signature not in self.portrait_library:
    name=jid+'-portrait-neutral.png';Image.open(io.BytesIO(anchor)).save(self.assets/name)
    self.portrait_library[signature]={'actor':r['actor'],'gender':r.get('gender','female'),'outfit':copy.deepcopy(r['outfit']),'expression':'neutral','file':name,'url':'/character-art/'+name,'source':(sources/'portrait-neutral.png').relative_to(self.root).as_posix(),'signature':signature,'created':int(time.time())}
  if portrait_signatures:
   with self.lock:atomic(self.library_path,self.portrait_library)
  if portraits:files['portraits']=portraits
  if frames:
   sheet=Image.new('RGBA',(192,256))
   for row,direction in enumerate(('up','left','down','right')):
    for frame in range(3):sheet.alpha_composite(frames[direction,frame],(frame*64,row*64))
   name=jid+'-sprite.png';sheet.save(self.assets/name);files['sprite']=name
  atomic(sources/'recipe.json',r)
  with self.lock:job['files']=files;job['validation']={'pipeline_version':r.get('pipeline_version',1),'guide':c['pixel_guide'] if frames else 'portrait-reference','palette_reference':bool(c.get('palette_reference') and frames),'background':'scene-preserved' if r['kind']=='cg' else c.get('background_method','edge'),'frames':metrics,'review_required':True}
