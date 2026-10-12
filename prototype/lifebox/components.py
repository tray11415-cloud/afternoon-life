"""Versioned component packages, dry runs, atomic application and rollback.

IDs remain stable; executable adapters use explicit local HTTP contracts.
Component metadata never carries runtime memories, inventories or credentials.
"""
import base64,copy,hashlib,io,json,re,secrets,threading
from pathlib import Path
from collections import deque
from .model import Action,Rejected,canonical,digest
from .character_art import atomic
from .component_adapters import local_endpoint,request_tool,RoutedBackend

def text(v,n=1200):
 if not isinstance(v,str) or not 1<=len(v)<=n:raise ValueError('文字長度不符')
def number(v,a,b):
 if type(v) is not int or not a<=v<=b:raise ValueError('數值超出允許範圍')
def point(p,w,h):
 if not isinstance(p,(list,tuple)) or len(p)!=2:raise ValueError('座標需為 [x,y]')
 number(p[0],0,w-1);number(p[1],0,h-1)

class Components:
 def __init__(self,s):
  self.s=s;self.root=s.root/'components';self.root.mkdir(exist_ok=True);self.file=self.root/'registry.json';self.lock=threading.RLock();self.proposals={}
  source=Path(__file__).resolve().parents[1]
  from .neighborhood import NPCS,FESTIVALS
  from .economy import EMPLOYERS,RECIPES,SUPPLIES,WAGE,SHIFT_MINUTES,MAX_SHIFTS
  original_maps=json.loads((source/'web/assets/maps.json').read_text(encoding='utf-8'))['maps']
  self.base={**{'map:'+k:copy.deepcopy(v) for k,v in original_maps.items()},**{'catalog:'+k:copy.deepcopy(v) for k,v in s.facilities.data.items()},
   **{'visual:'+k:copy.deepcopy(v) for k,v in json.loads((source/'data/art-manifest.json').read_text(encoding='utf-8'))['scenes'].items()},
   **{'npc:'+k:copy.deepcopy(v) for k,v in NPCS.items()},'events:calendar':copy.deepcopy(FESTIVALS),
   'rules:economy':{'employers':copy.deepcopy(EMPLOYERS),'recipes':copy.deepcopy(RECIPES),'supplies':copy.deepcopy(SUPPLIES),'wage':WAGE,'shift_minutes':SHIFT_MINUTES,'max_shifts':MAX_SHIFTS},
   'rules:pool':{'water':[9,4,22,12],'locker':[5,15],'rental_price':12,'swim_minutes':15},
   'rules:movement':{'algorithm':'bfs'},'theme:interface':{'paper':'#f6f3e9','ink':'#34443d','accent':'#566a50'},
   'service:dialogue':{'adapter':'existing','endpoint':'http://127.0.0.1:9000/decide','model':'','max_calls':20},
   'service:action':{'adapter':'existing','endpoint':'http://127.0.0.1:9000/decide','model':'','max_calls':20},
   'service:memory':{'adapter':'existing','endpoint':'http://127.0.0.1:11434','model':''},
   'service:replacement':{'adapter':'builtin','endpoint':'http://127.0.0.1:9000/replace','model':'','max_calls':20},
   **{'clothing:'+k:copy.deepcopy(v) for k,v in s.wardrobe.catalog.items()},
   **{'actor:'+k:{'name':v['name'],'age':v['age'],'gender':v.get('gender','female')} for k,v in s.engine._state['actors'].items() if v['role']!='npc'}}
  actor_baseline=self.root/'base-actors.json'
  if actor_baseline.exists():self.base.update(json.loads(actor_baseline.read_text(encoding='utf-8')))
  else:atomic(actor_baseline,{k:v for k,v in self.base.items() if k.startswith('actor:')})
  from .characters import default_profile,PRIVATE_FIELDS
  for k,v in self.base.items():
   if k.startswith('actor:'):
    p=default_profile(k[6:],v);v['character_profile']={f:p[f] for f in PRIVATE_FIELDS}
  self.static=source/'web/assets';self.art_names={p.name for p in self.static.glob('*.png')}
  self.registry={'version':1,'revision':0,'overrides':{},'history':[]}
  if self.file.exists():self.registry=json.loads(self.file.read_text(encoding='utf-8'))
  self.usage=json.loads((self.root/'tool-usage.json').read_text(encoding='utf-8')) if (self.root/'tool-usage.json').exists() else {}
  self.original_memory=s.memory;self.validate(self.registry['overrides'],startup=True);self.bind(clear=False)
  self.original_backend=s.backend;s.backend=RoutedBackend(s.backend,self)
 def get(self,target,overrides=None):
  live=overrides is None
  overrides=self.registry['overrides'] if overrides is None else overrides
  if target.startswith('actor:') and target in self.base:
   from .characters import default_profile,PRIVATE_FIELDS
   actor=target[6:];a=self.s.engine._state['actors'][actor]
   value=copy.deepcopy(overrides.get(target,self.base[target]))
   if live:
    value.update({f:a[f] for f in ('name','age','gender')})
    p={**default_profile(actor,a),**a.get('character_profile',{}),'goal':a['goal']['title'] or default_profile(actor)['goal']}
    value['character_profile']={f:p.get(f,'') for f in PRIVATE_FIELDS}
   elif 'character_profile' not in value:
    p={**default_profile(actor,a),**a.get('character_profile',{}),'goal':a['goal']['title'] or default_profile(actor)['goal']}
    value['character_profile']={f:p.get(f,'') for f in PRIVATE_FIELDS}
   return value
  if target.startswith('object:'):
   _,scene,ident=target.split(':',2);row=next((o for o in self.get('map:'+scene,overrides)['objects'] if o['id']==ident),None)
   if row is None:raise ValueError('找不到物件')
   return copy.deepcopy(overrides.get(target,row))
  if target.startswith('item:'):
   _,venue,ident=target.split(':',2);row=next((i for i in self.get('catalog:'+venue,overrides)['items'] if i['id']==ident),None)
   if row is None:raise ValueError('找不到品項')
   return copy.deepcopy(overrides.get(target,row))
  if target.startswith('decor:'):
   _,scene,ident=target.split(':',2);visual=overrides.get('visual:'+scene,self.base.get('visual:'+scene,{}));row=next((d for d in visual.get('decor',[]) if d['id']==ident),None)
   if row is None:raise ValueError('找不到美術部件')
   return copy.deepcopy(overrides.get(target,row))
  if target.startswith('visual:'):
   if target not in self.base:raise ValueError('未知場景美術 ID')
   v=copy.deepcopy(overrides.get(target,self.base[target]));v['decor']=[copy.deepcopy(overrides.get('decor:'+target[7:]+':'+d['id'],d)) for d in v['decor']];return v
  if target=='service:sd':return copy.deepcopy(overrides.get(target,self.s.studio.config) if overrides is not self.registry['overrides'] else self.s.studio.config)
  if target=='service:tts':return copy.deepcopy(overrides.get(target,self.s.speech.config) if overrides is not self.registry['overrides'] else self.s.speech.config)
  if target.startswith('art:'):
   name=target[4:]
   if name not in self.art_names:raise ValueError('未知素材 ID')
   from PIL import Image
   with Image.open(self.static/name) as im:dimensions=list(im.size)
   return copy.deepcopy(overrides.get(target,{'file':None,'size':dimensions,'url':'/assets/'+name}))
  if target.startswith('tool:'):return copy.deepcopy(overrides.get(target,{'adapter':'local-tool','endpoint':'http://127.0.0.1:9000/interact','enabled':False,'max_calls':20}))
  if target not in self.base:raise ValueError('未知部件 ID')
  return copy.deepcopy(overrides.get(target,self.base[target]))
 def targets(self):
  ids=list(self.base)+['service:sd','service:tts']+['art:'+k for k in sorted(self.art_names)]
  for k in self.base:
   if k.startswith('map:'):ids+=['object:'+k[4:]+':'+o['id'] for o in self.get(k)['objects']]
   if k.startswith('catalog:'):ids+=['item:'+k[8:]+':'+i['id'] for i in self.get(k)['items']]
   if k.startswith('visual:'):ids+=['decor:'+k[7:]+':'+d['id'] for d in self.get(k)['decor']]
  ids+=list(k for k in self.registry['overrides'] if k.startswith('tool:'))
  return ids
 def maps(self,overrides=None):
  overrides=self.registry['overrides'] if overrides is None else overrides
  maps={k[4:]:self.get(k,overrides) for k in self.base if k.startswith('map:')}
  for scene,m in maps.items():m['objects']=[copy.deepcopy(overrides.get('object:'+scene+':'+o['id'],o)) for o in m['objects']]
  return maps
 def catalogs(self,overrides=None):
  overrides=self.registry['overrides'] if overrides is None else overrides
  data={k[8:]:self.get(k,overrides) for k in self.base if k.startswith('catalog:')}
  for venue,v in data.items():v['items']=[copy.deepcopy(overrides.get('item:'+venue+':'+i['id'],i)) for i in v['items']]
  return data
 def state(self):
  labels={}
  for scene,m in self.s.map_spec['maps'].items():
   labels['map:'+scene]=labels['visual:'+scene]=m['name']
   for o in m['objects']:labels['object:'+scene+':'+o['id']]=m['name']+' · '+o.get('name',o['id'])
  for venue,v in self.s.facilities.data.items():
   labels['catalog:'+venue]=v['name']
   for i in v['items']:labels['item:'+venue+':'+i['id']]=v['name']+' · '+i['title']
  for k,v in self.s.engine._state['actors'].items():labels['actor:'+k]=labels['npc:'+k]=v['name']
  return {'contract':'lifebox.components.v1','revision':self.registry['revision'],'targets':[{'id':k,'label':labels.get(k,k),'kind':k.split(':')[0],'replaced':k in self.registry['overrides']} for k in self.targets()],
   'history':[{'id':h['id'],'instruction':h['instruction'],'targets':h['targets']} for h in self.registry['history'][-20:]],'usage':copy.deepcopy(self.usage)}
 def public(self):
  return {'revision':self.registry['revision'],'map':copy.deepcopy(self.s.map_spec['maps'][self.s.space.entities['player']['scene']]),
   'visual':self.get('visual:'+self.s.space.entities['player']['scene']), 'theme':self.get('theme:interface'),
   'art':{k[4:]:v['url'] for k,v in self.registry['overrides'].items() if k.startswith('art:')}}
 def reserve(self,target,limit):
  key=str((self.s.engine.tick+840)//1440)+':'+target;count=self.usage.get(key,0)
  if count>=limit:raise Rejected('tool_budget')
  self.usage[key]=count+1;atomic(self.root/'tool-usage.json',self.usage)
 def asset(self,name):
  if not re.fullmatch(r'[a-f0-9]{64}\.png',name):return None
  refs=[]
  for k,v in self.registry['overrides'].items():
   if k.startswith('art:'):refs.append(v['url'])
   elif k.startswith('decor:'):refs.append(v['image'])
   elif k.startswith('visual:'):refs.extend([v['background']]+[d['image'] for d in v['decor']]+[t['image'] for t in v.get('tiles',[])])
  if '/component-art/'+name not in refs:return None
  file=self.root/name;return file if file.is_file() else None
 def upload(self,target,encoded):
  if not target.startswith('art:'):raise ValueError('PNG 必須指定 art: 素材 ID')
  original=self.get(target,{});raw=base64.b64decode(encoded,validate=True)
  if len(raw)>3*1024*1024 or not raw.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('PNG 最大 3 MB')
  from PIL import Image
  try:
   with Image.open(io.BytesIO(raw)) as im:
    if im.format!='PNG' or list(im.size)!=original['size']:raise ValueError('PNG 尺寸需為 '+str(original['size']))
    im=im.convert('RGBA');buf=io.BytesIO();im.save(buf,format='PNG');raw=buf.getvalue()
  except (OSError,Image.DecompressionBombError):raise ValueError('PNG 已損壞或尺寸過大')
  name=hashlib.sha256(raw).hexdigest()+'.png';(self.root/name).write_bytes(raw)
  return {'file':name,'size':original['size'],'url':'/component-art/'+name}
 def prepare(self,p):
  if set(p)-{'instruction','changes','revision'} or not isinstance(p.get('changes'),list) or not 1<=len(p['changes'])<=40:raise ValueError('需要 1–40 個替換項')
  text(p.get('instruction',''),400)
  if p.get('revision',self.registry['revision'])!=self.registry['revision']:raise ValueError('部件版本已改變，請重新預覽')
  candidate=copy.deepcopy(self.registry['overrides']);seen=set();changes=[];previous_values={}
  for row in p['changes']:
   if not isinstance(row,dict) or set(row)-{'target','value','png','reset'} or 'target' not in row or sum(k in row for k in ('value','png','reset'))!=1:raise ValueError('每項需有 target 和 value／png／reset')
   target=row['target'];before=self.get(target)
   if target in seen:raise ValueError('重複部件 ID')
   seen.add(target);previous_values[target]=before
   if 'reset' in row:
    if row['reset'] is not True:raise ValueError('reset 需為 true')
    candidate.pop(target,None);value=self.get(target,candidate)
   else:
    value=self.upload(target,row['png']) if 'png' in row else copy.deepcopy(row['value']);candidate[target]=value
   changes.append({'target':target,'before':digest(before),'after':digest(value),'summary':('恢復原部件' if 'reset' in row else '替換部件'),'diff':self.diff(before,value)})
  self.validate(candidate)
  ident=secrets.token_hex(16);proposal={'id':ident,'instruction':p['instruction'],'revision':self.registry['revision'],'changes':changes,'candidate':candidate,'previous_values':previous_values}
  self.proposals[ident]=proposal
  if len(self.proposals)>32:self.proposals.pop(next(iter(self.proposals)))
  return {k:v for k,v in proposal.items() if k not in {'candidate','previous_values'}}|{'validated':True,'effects':['使用相同 ID，保留既有記憶和庫存快照','路徑會清空並重新尋路，角色位置保留','預覽不套用或生成美術']}
 def validate(self,overrides,startup=False):
  if not isinstance(overrides,dict):raise ValueError('部件資料必須為物件')
  maps=self.maps(overrides)
  for scene,m in maps.items():
   if set(m)-{'id','name','width','height','ground','decor','tiles','blocked','portals','objects','labels','palette','outside','props','theme','service_object'}:raise ValueError('未知地圖欄位')
   text(m['name'],80);number(m['width'],8,128);number(m['height'],8,128)
   if (m['width'],m['height'])!=(self.base['map:'+scene]['width'],self.base['map:'+scene]['height']):raise ValueError('目前換圖需保留格網尺寸，背景和座標才能相容')
   w,h=m['width'],m['height'];blocked={tuple(p) for p in m['blocked']}
   if m['id']!=self.base['map:'+scene]['id']:raise ValueError('地圖内部 ID 需保留')
   for p in m['blocked']:point(p,w,h)
   if len(m['objects'])>200:raise ValueError('場景最多 200 個物件')
   ids=set()
   for o in m['objects']:
    if set(o)-{'id','name','x','y','description','effect','handler'}:raise ValueError('未知物件欄位')
    text(o['id'],80);text(o['description']);point([o['x'],o['y']],w,h)
    if o['id'] in ids:raise ValueError('物件 ID 重複')
    ids.add(o['id'])
    if o['effect'] not in {'none','inspect','venue','rest','water'}:raise ValueError('請使用 handler 指定自訂互動')
    if 'handler' in o:self.handler_valid(o['handler'],overrides)
   if m.get('service_object') and m['service_object'] not in ids:raise ValueError('服務桌 ID 不存在')
   original_ids={o['id'] for o in self.base['map:'+scene]['objects']}
   if not original_ids.issubset(ids):raise ValueError('既有互動 ID 不可移除，可替換其內容或停用行為')
   for label in m['labels']:text(label['text'],80);point([label['x'],label['y']],w,h)
   for po in m['portals']:
    if set(po)!={'x','y','to','spawn'} or po['to'] not in maps:raise ValueError('無效門口')
    point([po['x'],po['y']],w,h);dest=maps[po['to']];point(po['spawn'],dest['width'],dest['height'])
    if (po['x'],po['y']) in blocked or tuple(po['spawn']) in {tuple(p) for p in dest['blocked']}:raise ValueError('門口或出生點被阻擋')
    if not any(back['to']==scene for back in dest['portals']):raise ValueError('門口需有回程')
   if not m['portals']:raise ValueError('場景不可沒有出口')
   # Every exit and service object must remain in the walkable connected area.
   seed=(m['portals'][0]['x'],m['portals'][0]['y']);seen={seed};q=deque([seed])
   while q:
    x,y=q.popleft()
    for dx,dy in ((1,0),(-1,0),(0,1),(0,-1)):
     p=(x+dx,y+dy)
     if 0<=p[0]<w and 0<=p[1]<h and p not in blocked and p not in seen:seen.add(p);q.append(p)
   if any((po['x'],po['y']) not in seen for po in m['portals']) or any(not any((o['x']+dx,o['y']+dy) in seen for dx,dy in ((1,0),(-1,0),(0,1),(0,-1))) for o in m['objects']):raise ValueError('替換會封死門口或互動物件')
   for e in self.s.space.entities.values():
    if e['scene']==scene and (e['x'],e['y']) not in seen:raise ValueError('替換會困住目前角色，請先讓角色移開')
  graph={k:{p['to'] for p in m['portals']} for k,m in maps.items()};todo=['shared'];reachable=set(todo)
  for node in todo:
   for target in graph[node]:
    if target not in reachable:reachable.add(target);todo.append(target)
  if reachable!=set(maps):raise ValueError('替換會切斷公共街區與場所的連線')
  for k,v in overrides.items():
   if k.startswith(('map:','object:')):self.get(k,overrides);continue
   if k.startswith('decor:'):
    _,scene,ident=k.split(':',2);self.get(k,overrides)
    if v.get('id')!=ident or set(v)-{'id','image','x','y','depth'}:raise ValueError('美術部件需保留 ID')
    self.image_url(v['image'])
    for f in ('x','y','depth'):number(v[f],-512,8192)
    continue
   if k.startswith(('catalog:','item:')):self.get(k,overrides);continue
   if k.startswith('visual:'):
    if k not in self.base or set(v)-{'background','decor','tiles'}:raise ValueError('未知美術場景')
    self.image_url(v['background']);number(len(v['decor']),0,300)
    for d in v['decor']:
     if set(d)-{'id','image','x','y','depth'}:raise ValueError('未知物件美術欄位')
     self.image_url(d['image'])
     for f in ('x','y','depth'):number(d[f],-512,8192)
    for tile in v.get('tiles',[]):
     if set(tile)!={'image','source','x','y','width','height'} or len(tile['source'])!=4:raise ValueError('圖塊需有圖檔、source矩形與目的矩形')
     self.image_url(tile['image'])
     for f in ('x','y','width','height'):number(tile[f],0,4096)
     for n in tile['source']:number(n,0,4096)
     for n in tile['source'][2:]+[tile['width'],tile['height']]:number(n,1,4096)
     from PIL import Image
     path=self.static/tile['image'][8:] if tile['image'].startswith('/assets/') else self.root/tile['image'][15:]
     with Image.open(path) as im:
      if tile['source'][0]+tile['source'][2]>im.width or tile['source'][1]+tile['source'][3]>im.height:raise ValueError('圖塊來源矩形超出 PNG')
   elif k.startswith('art:'):
    original=self.get(k,{})
    if set(v)!={'file','size','url'} or v['size']!=original['size'] or not re.fullmatch(r'[a-f0-9]{64}\.png',v['file'] or '') or v['url']!='/component-art/'+v['file'] or not (self.root/v['file']).is_file():raise ValueError('美術需用 png 匯入，不接受任意檔案路徑')
   elif k.startswith('actor:'):
    if k not in self.base or not {'name','age','gender'}<=set(v) or set(v)-{'name','age','gender','character_profile'} or v['gender'] not in {'male','female'}:raise ValueError('人物公開欄位不符')
    text(v['name'],32);number(v['age'],18,120)
    if 'character_profile' in v:
     from .characters import validate_profile,PRIVATE_FIELDS
     if not isinstance(v['character_profile'],dict) or set(v['character_profile']) not in (set(PRIVATE_FIELDS),set(PRIVATE_FIELDS)-{'look'}):raise ValueError('人物性格、目標、背景與外觀欄位不符')
     validate_profile({**{f:v[f] for f in ('name','age','gender')},**v['character_profile']})
   elif k.startswith('clothing:'):
    from .wardrobe import Wardrobe
    if k not in self.base or v['id']!=k[9:] or not Wardrobe.valid_item(v):raise ValueError('服裝需保留 ID 與有效 SFW 配方')
    number(v['price'],0,10000)
   elif k.startswith('npc:'):
    if k not in self.base or set(v)!=set(self.base[k]):raise ValueError('NPC 欄位不符')
    text(v['name'],40);text(v['line'],1200);number(v['age'],18,100)
    if v['gender'] not in {'male','female'} or v['venue'] not in maps:raise ValueError('NPC 性別或場所不符')
   elif k=='events:calendar':
    if not isinstance(v,list) or not 1<=len(v)<=40:raise ValueError('公共活動數量不符')
    ids=set()
    for e in v:
     if set(e)!={'id','title','venue','period','offset','hour','minutes','description'}:raise ValueError('活動欄位不符')
     text(e['id'],80);text(e['title'],100);text(e['description']);number(e['period'],1,365);number(e['offset'],0,e['period']-1);number(e['hour'],0,23);number(e['minutes'],3,720)
     if e['venue'] not in maps or e['id'] in ids:raise ValueError('活動 ID 或場所不符')
     ids.add(e['id'])
   elif k=='rules:movement':
    if v not in ({'algorithm':'bfs'},{'algorithm':'astar'}):raise ValueError('目前提供 bfs／astar 尋路轉接器')
   elif k=='rules:pool':
    if set(v)!=set(self.base[k]):raise ValueError('泳池規則欄位不符')
    point(v['locker'],maps['pool']['width'],maps['pool']['height']);number(v['rental_price'],0,1000);number(v['swim_minutes'],3,120)
    if len(v['water'])!=4:raise ValueError('水域需為矩形')
    point(v['water'][:2],maps['pool']['width'],maps['pool']['height']);point(v['water'][2:],maps['pool']['width'],maps['pool']['height'])
    if v['water'][0]>v['water'][2] or v['water'][1]>v['water'][3]:raise ValueError('水域矩形不符')
    if v['locker'] in maps['pool']['blocked']:raise ValueError('更衣櫃不可設在牆內')
    for e in self.s.space.entities.values():
     if e['scene']=='pool' and v['water'][0]<=e['x']<=v['water'][2] and v['water'][1]<=e['y']<=v['water'][3] and not self.s.neighborhood.in_swimwear(e['id']):raise ValueError('新水域不能蓋住未換泳裝的人')
   elif k=='rules:economy':self.economy_valid(v,maps)
   elif k=='theme:interface':
    if set(v)!=set(self.base[k]) or any(not re.fullmatch(r'#[a-fA-F0-9]{6}',color) for color in v.values()):raise ValueError('介面只接受六位色碼')
   elif k.startswith('tool:'):
    if not re.fullmatch(r'tool:[a-z][a-z0-9_-]{0,50}',k) or set(v)!={'adapter','endpoint','enabled','max_calls'} or v['adapter']!='local-tool' or type(v['enabled']) is not bool:raise ValueError('工具契約不符')
    local_endpoint(v['endpoint']);number(v['max_calls'],1,100)
   elif k in ('service:action','service:dialogue','service:replacement'):
    if set(v)!=set(self.base[k]) or v['adapter'] not in ({'builtin','local-plan'} if k=='service:replacement' else {'existing','local-decide'}):raise ValueError('決策服務契約不符')
    local_endpoint(v['endpoint']);number(v['max_calls'],1,100)
    if not isinstance(v['model'],str) or len(v['model'])>120:raise ValueError('模型名稱不符')
   elif k=='service:memory':
    if set(v)!=set(self.base[k]) or v['adapter'] not in {'existing','lexical','ollama'}:raise ValueError('記憶服務契約不符')
    local_endpoint(v['endpoint'])
    if v['adapter']=='ollama':text(v['model'],120)
   elif k=='service:tts':
    from .speech import validate
    validate(v)
   elif k=='service:sd':
    allowed={'installation','backend','url','checkpoint','vae','sampler','scheduler','auto','pixel_guide','control_model','control_weight','palette','palette_reference','remove_background','background_tolerance','background_method','background_model','background_device','background_resolution','expressions','templates','profiles','outfit_loras'}
    clone=copy.copy(self.s.studio);clone.config=copy.deepcopy(self.s.studio.config);clone.lock=threading.RLock();clone.auto_seen=set();clone.config_path=self.root/'validation-sd.json'
    clone.configure({f:value for f,value in v.items() if f in allowed})
    if v.get('active')!=self.s.studio.config.get('active'):raise ValueError('生成素材套用請使用原生美術差分接口')
    clone.native_select({'selections':v['native_selected']})
    if set(v)-set(self.s.studio.config):raise ValueError('未知 SD 欄位')
   else:raise ValueError('未知部件種類')
  for venue,v in self.catalogs(overrides).items():
   if set(v)-{'name','url','note','checked_at','items','stale'}:raise ValueError('未知場所欄位')
   text(v['name'],100);text(v['note'],2000)
   ids=set()
   for row in v['items']:
    for f in ('id','title','mode','facts'):text(row[f],10000)
    number(row['price'],0,100000);number(row['minutes'],0,720)
    if row['id'] in ids:raise ValueError('品項 ID 重複')
    ids.add(row['id'])
   if not {i['id'] for i in self.base['catalog:'+venue]['items']}.issubset(ids):raise ValueError('舊品項 ID 不可刪除，已購與活動仍可能引用')
  if not startup:
   # Manual saves must also remain loadable, without changing their journals.
   for file in list(self.s.root.glob('pixel-*.json'))+list((self.s.root/'archives').glob('*/pixel-*.json')):
    payload=json.loads(file.read_text(encoding='utf-8'))['payload'];entities=payload['space']['entities']
    for e in entities.values():
     m=maps[e['scene']]
     if [e['x'],e['y']] in m['blocked']:raise ValueError('替換會阻擋現有存檔角色位置')
 def image_url(self,url):
  if url.startswith('/assets/') and url[8:] in self.art_names:return
  if url.startswith('/component-art/') and re.fullmatch(r'[a-f0-9]{64}\.png',url[15:]) and (self.root/url[15:]).is_file():return
  raise ValueError('美術只能引用已匯入或打包的 PNG')
 def diff(self,before,after,path=''):
  if before==after:return []
  if isinstance(before,dict) and isinstance(after,dict):
   rows=[]
   for key in sorted(set(before)|set(after)):rows+=self.diff(before.get(key),after.get(key),path+'/'+key)
   return rows[:30]
  def short(v):
   value=canonical(v);return value if len(value)<240 else value[:200]+'… ('+str(len(value))+' 字元)'
  return [{'field':path or '/', 'before':short(before),'after':short(after)}]
 def schema(self):
  return {'function_tools':json.loads((Path(__file__).resolve().parents[1]/'data/component-tools.json').read_text(encoding='utf-8'))['tools'],'contract':'lifebox.components.v1','endpoint':'/api/components','authentication':'本機 Host + X-Play-Token；POST 另需 Origin，金鑰不得放在部件包',
   'tools':[{'name':'get','params':{'target':'部件 ID'}}, {'name':'plan','params':{'instruction':'替換指示','targets':['部件 ID']}},
    {'name':'prepare','params':{'instruction':'替換目的','revision':'目前部件版本，可省略','changes':[{'target':'部件 ID','value':'新定義；也可用 png/base64 或 reset/true'}]}},
    {'name':'apply','params':{'proposal':'已驗證的預覽 ID'}},{'name':'rollback','params':{'history':'最近一次紀錄 ID，回傳還原預覽，仍需 apply'}},{'name':'export','params':{'targets':['部件 ID']}}],
   'adapter_contracts':{'decision':{'request':{'contract':'lifebox.decide.v1','actor':'唯一角色 ID','context':'該角色投影','profile':'自身語氣','trigger':'觸發事件','model':'模型名'},'response':{'action':{'kind':'合法引擎動詞','params':{}}}},
    'interaction':{'request':{'contract':'lifebox.interact.v1','actor':'唯一角色 ID','object':'在場物件','arguments':{},'context':'角色自己能知道的資料'},'response':'僅 notice 或 action，命令仍由世界裁定'},
    'replacement':{'request':{'contract':'lifebox.replace.v1','instruction':'玩家指令','components':'僅玩家選定的部件定義','model':'模型名'},'response':{'changes':[{'target':'選定 ID','value':'新定義'}]}}},
   'categories':['map','object','visual','decor','art','catalog','item','clothing','actor','npc','events','rules','service','tool','theme'],
   'engine_contract':'共享事件日誌裁定結果；更換邏輯不提供原始程式執行權，也不能改寫歷史。'}
 def economy_valid(self,v,maps):
  if set(v)!=set(self.base['rules:economy']):raise ValueError('經濟規則欄位不符')
  number(v['wage'],0,10000);number(v['shift_minutes'],1,120);number(v['max_shifts'],1,10)
  if set(v['recipes'])!=set(self.base['rules:economy']['recipes']) or set(v['supplies'])!=set(self.base['rules:economy']['supplies']):raise ValueError('製作人與補給 ID 需保持穩定')
  for venue,title in v['employers'].items():
   if venue not in maps:raise ValueError('打工場所不符')
   text(title,100)
  if not v['employers']:raise ValueError('至少需要一個收入場所')
  for row in list(v['recipes'].values())+list(v['supplies'].values()):
   text(row['title'],100);number(row['price'],0,10000);number(row['quantity'],1,20)
   for n,amount in row['effects'].items():
    if n not in {'hunger','thirst','fatigue','curiosity'}:raise ValueError('未知需求')
    number(amount,0,100)
  for actor,r in v['recipes'].items():
   if r['id']!=self.base['rules:economy']['recipes'][actor]['id']:raise ValueError('作品 ID 不可改變')
   number(r['minutes'],1,120)
 def handler_valid(self,h,overrides):
  if not isinstance(h,dict) or h.get('kind') not in {'notify','command','tool'}:raise ValueError('互動 handler 不符')
  if h['kind']=='notify':
   if set(h)!={'kind','text'}:raise ValueError('通知欄位不符')
   text(h['text'])
  elif h['kind']=='command':
   if set(h)!={'kind','action'}:raise ValueError('命令欄位不符')
   a=Action.parse(h['action'])
   if a.kind not in self.s.engine._schemas() or a.kind in {'move','interact','approach_object'} or set(a.params)!=self.s.engine._schemas()[a.kind]:raise ValueError('物件不能執行此命令，移動由實體尋路裁定')
  else:
   if set(h)!={'kind','tool','arguments'} or not isinstance(h['arguments'],dict):raise ValueError('工具欄位不符')
   self.get(h['tool'],overrides)
 def bind(self,clear=True):
  s=self.s;s.map_spec['maps']=self.maps();s.space.maps=s.map_spec['maps'];s.space.blocked={k:{tuple(p) for p in m['blocked']} for k,m in s.space.maps.items()}
  if clear:
   for e in s.space.entities.values():e.update(path=[],destination=None,walking=False)
   s.space.revision+=1
  s.components=self;s.facilities.data=self.catalogs();s.facilities.bind();s.engine.interaction_handler=self.interact;s.engine.approach_handler=self.approach
  for row in s.facilities.data['pool']['items']:
   if row['id']=='pool-swim':row.update(minutes=self.get('rules:pool')['swim_minutes'],title='游泳'+str(self.get('rules:pool')['swim_minutes'])+'分鐘')
  s.wardrobe.catalog={k[9:]:self.get(k) for k in self.base if k.startswith('clothing:')}
  for k in self.base:
   if not k.startswith(('actor:','npc:')):continue
   # Actor values belong to the saved event journal. Only an explicit apply
   # emits a new profile; loading another world must keep that world's people.
   if k.startswith('actor:'):continue
   a=k.split(':',1)[1];definition=self.get(k,self.registry['overrides']);value={f:definition[f] for f in ('name','age','gender')}
   if k.startswith('actor:') and 'character_profile' in definition:value['character_profile']=definition['character_profile']
   if 'npc:'+a in self.registry['overrides']:value={f:self.get('npc:'+a)[f] for f in ('name','age','gender')}
   from .characters import PRIVATE_FIELDS
   current=s.engine._state['actors'][a]
   changed=any(current.get(f)!=v for f,v in value.items() if f!='character_profile')
   if 'character_profile' in value:changed=changed or any(current.get('character_profile',{}).get(f)!=v for f,v in value['character_profile'].items())
   if changed:s.engine._emit('component_profile',a,value,[],remember=False)
  s.space.algorithm=self.get('rules:movement')['algorithm']
  s.studio.actor_genders={a:v.get('gender','female') for a,v in s.engine._state['actors'].items()}
  s.studio.actor_identities={a:{'age':v['age'],'appearance':v.get('character_profile',{}).get('appearance',''),**({'look':v['character_profile']['look']} if v.get('character_profile',{}).get('look',{}).get('enabled') else {})} for a,v in s.engine._state['actors'].items()}
  c=self.get('service:memory')
  if c['adapter']=='existing':s.memory=self.original_memory
  else:
   from .memory import VectorMemory,LexicalEmbedding,OllamaEmbedding
   provider=LexicalEmbedding() if c['adapter']=='lexical' else OllamaEmbedding(c['endpoint'],c['model'])
   s.memory=VectorMemory(s.root/'vector-memory.sqlite3',provider)
 def apply(self,ident):
  with self.s.lock,self.lock:
   p=self.proposals.get(ident)
   if not p:raise ValueError('預覽已過期，請重新建立')
   if p['revision']!=self.registry['revision'] or any(digest(self.get(r['target']))!=r['before'] for r in p['changes']):raise ValueError('部件已改變，請重新預覽')
   self.validate(p['candidate'])
   old=copy.deepcopy(self.registry);journal=self.s.engine.journal();spatial=self.s.space.snapshot();sd=copy.deepcopy(self.s.studio.config);tts=copy.deepcopy(self.s.speech.config)
   try:
    for row in p['changes']:
     target=row['target'];value=self.get(target,p['candidate'])
     if target=='service:sd':
      allowed={'installation','backend','url','checkpoint','vae','sampler','scheduler','auto','pixel_guide','control_model','control_weight','palette','palette_reference','remove_background','background_tolerance','background_method','background_model','background_device','background_resolution','expressions','templates','profiles','outfit_loras'}
      self.s.studio.configure({k:v for k,v in value.items() if k in allowed})
      self.s.studio.native_select({'selections':value['native_selected']})
     elif target=='service:tts':self.s.speech.configure(value)
    record={'id':ident,'instruction':p['instruction'],'targets':[r['target'] for r in p['changes']],'previous':old['overrides'],'after':p['candidate'],'previous_values':p['previous_values']}
    self.registry={'version':1,'revision':old['revision']+1,'overrides':p['candidate'],'history':(old['history']+[record])[-20:]}
    atomic(self.file,self.registry);self.bind()
    for row in p['changes']:
     if row['target'].startswith('actor:'):
      value=self.get(row['target'],p['candidate']);self.s.engine._emit('component_profile',row['target'][6:],value,[],remember=False)
    self.s.studio.actor_genders={a:v.get('gender','female') for a,v in self.s.engine._state['actors'].items()}
    self.s.studio.actor_identities={a:{'age':v['age'],'appearance':v.get('character_profile',{}).get('appearance',''),**({'look':v['character_profile']['look']} if v.get('character_profile',{}).get('look',{}).get('enabled') else {})} for a,v in self.s.engine._state['actors'].items()}
    self.s._save();self.proposals.clear()
   except Exception:
    self.registry=old;atomic(self.file,old);self.s.studio.config=sd;atomic(self.s.studio.config_path,sd);self.s.speech.config=tts;atomic(self.s.speech.root/'settings.json',tts)
    from .engine import Engine
    from .spatial import SpatialWorld
    self.s.engine=Engine.replay(journal);self.s.map_spec['maps']=self.maps();self.s.space=SpatialWorld(self.s.map_spec['maps'],self.s.engine,spatial)
    self.s.economy.bind();self.s.wardrobe.bind();self.s.social.bind();self.s.neighborhood.bind();self.bind(clear=False);self.s._save();raise
   return {'revision':self.registry['revision'],'applied':record['targets'],'notice':'替換已套用，原狀態已保存，可還原'}
 def rollback(self,ident):
  record=next((h for h in self.registry['history'] if h['id']==ident),None)
  if not record:raise ValueError('找不到替換紀錄')
  rows=[]
  for target in record['targets']:
   if self.get(target)!=self.get(target,record['after']):raise ValueError('目標部件已改變，請重新預覽還原')
   value=record['previous_values'][target]
   rows.append({'target':target,'value':value} if target in record['previous'] or target in {'service:sd','service:tts'} or target.startswith('actor:') else {'target':target,'reset':True})
  # External service baselines are saved explicitly by preparation below.
  p=self.prepare({'instruction':'還原：'+record['instruction'],'changes':rows});return p
 def interact(self,actor,action):
  s=self.s;e=s.space.entities[actor];o=next((o for o in s.map_spec['maps'][e['scene']]['objects'] if o['id']==action.params['object']),None)
  if not o or abs(o['x']-e['x'])+abs(o['y']-e['y'])>2 or not s.space.line_clear(e['scene'],(e['x'],e['y']),(o['x'],o['y'])):raise Rejected('object_too_far')
  h=o.get('handler');notice=o['description']
  if h:
   if h['kind']=='notify':notice=h['text']
   elif h['kind']=='command':s.engine._perform(actor,Action.parse(h['action']))
   else:
    c=self.get(h['tool'])
    if not c['enabled']:raise Rejected('tool_disabled')
    self.reserve(h['tool'],c['max_calls'])
    try:result=request_tool(c['endpoint'],{'contract':'lifebox.interact.v1','actor':actor,'object':o,'arguments':h['arguments'],'context':s.engine.view(actor,4)})
    except Exception:raise Rejected('tool_unavailable') from None
    if set(result)=={'notice'}:text(result['notice']);notice=result['notice']
    elif set(result)=={'action'}:
     self.handler_valid({'kind':'command','action':result['action']},self.registry['overrides']);s.engine._perform(actor,Action.parse(result['action']))
    else:raise Rejected('tool_output')
  elif o['effect']=='rest':s._native_step();s._native_step();notice='休息了一會兒。'
  elif o['effect']=='water':s.space.flags['water_day']=s.engine.tick//1440;s.space.revision+=1
  s.engine._emit('component_interacted',actor,{'scene':e['scene'],'object':o['id'],'notice':notice},[actor])
  s.notice=notice
 def object_context(self,actor):
  e=self.s.space.entities[actor]
  return [{'id':o['id'],'name':o.get('name',o['id']),'description':o['description'][:180],'near':abs(o['x']-e['x'])+abs(o['y']-e['y'])<=2} for o in self.s.map_spec['maps'][e['scene']]['objects'] if max(abs(o['x']-e['x']),abs(o['y']-e['y']))<=12 and self.s.space.line_clear(e['scene'],(e['x'],e['y']),(o['x'],o['y']))][:12]
 def approach(self,actor,action):
  e=self.s.space.entities[actor];o=next((o for o in self.s.map_spec['maps'][e['scene']]['objects'] if o['id']==action.params['object']),None)
  if not o:raise Rejected('object_unknown')
  if abs(o['x']-e['x'])+abs(o['y']-e['y'])<=2:return
  if not any(self.s.space.walk_to(actor,o['x']+dx,o['y']+dy) for dx,dy in ((0,1),(1,0),(-1,0),(0,-1))):raise Rejected('object_unreachable')
 def operation(self,body):
  if set(body)!={'operation','params'} or not isinstance(body['params'],dict):raise ValueError('工具呼叫需有 operation 和 params')
  op,p=body['operation'],body['params']
  with self.s.lock,self.lock:
   if op=='get' and set(p)=={'target'}:return {'target':p['target'],'value':self.get(p['target']),'revision':self.registry['revision']}
   if op=='prepare':return self.prepare(p)
   if op=='apply' and set(p)=={'proposal'}:return self.apply(p['proposal'])
   if op=='rollback' and set(p)=={'history'}:return self.rollback(p['history'])
   if op=='plan' and set(p)=={'instruction','targets'}:return self.plan(p)
   if op=='export' and set(p)=={'targets'}:
    rows=[]
    for k in p['targets']:
     value=self.get(k)
     rows.append({'target':k,'png':base64.b64encode((self.root/value['file']).read_bytes()).decode()} if k.startswith('art:') and value.get('file') else {'target':k,'reset':True} if k.startswith('art:') else {'target':k,'value':value})
    return {'instruction':'匯出的部件包','changes':rows}
  raise ValueError('未知替換工具')
 def plan(self,p):
  text(p['instruction'],400)
  if not isinstance(p['targets'],list) or not 1<=len(p['targets'])<=8:raise ValueError('請選擇 1–8 個要替換的部件')
  values={k:self.get(k) for k in p['targets']};c=self.get('service:replacement');instruction=p['instruction']
  if c['adapter']=='local-plan':
   self.reserve('service:replacement',c['max_calls']);result=request_tool(c['endpoint'],{'contract':'lifebox.replace.v1','instruction':instruction,'components':values,'model':c['model']})
   rows=result.get('changes')
   if not isinstance(rows,list) or any(r.get('target') not in values for r in rows):raise ValueError('替換 AI 只能修改你選定的部件')
  else:
   if len(values)!=1:raise ValueError('內建指令一次選一個部件；多項可使用部件包或本機替換 AI')
   target,value=next(iter(values.items()));m=re.fullmatch(r'(說明|名稱|價格|互動|尋路|说明|名称|价格|互动|寻路)(?:改成|改為|設為|改为|设为|=)(.+)',instruction.strip(),re.S)
   if not m:m=re.fullmatch(r'(description|name|price|interaction|pathfinding|説明|名前|価格|操作|経路)\s*[:：=]\s*(.+)',instruction.strip(),re.S|re.I)
   if not m:raise ValueError('可用指令：說明改成…／名稱改成…／價格改成數字／互動改為休息／尋路改為astar；複雜替換可編輯 JSON 或連接本機替換 AI')
   field,data=m.groups();field={'說明':'description','名稱':'name','價格':'price','互動':'effect','尋路':'algorithm','说明':'description','名称':'name','价格':'price','互动':'effect','寻路':'algorithm','description':'description','name':'name','price':'price','interaction':'effect','pathfinding':'algorithm','説明':'description','名前':'name','価格':'price','操作':'effect','経路':'algorithm'}[field.lower()]
   if field=='name' and target.startswith(('item:','clothing:')):field='title'
   if field=='name' and target.startswith('object:') and 'name' not in value:value['name']=value['id']
   if not isinstance(value,dict) or field not in value:raise ValueError('這個部件沒有該欄位')
   value[field]=int(data) if field=='price' else {'休息':'rest','澆水':'water','浇水':'water','查看':'none','休憩':'rest','水やり':'water','確認':'none'}.get(data,data) if field=='effect' else data
   if field=='effect':value.pop('handler',None)
   rows=[{'target':target,'value':value}]
  return self.prepare({'instruction':instruction,'changes':rows})
