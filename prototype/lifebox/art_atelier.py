"""Player-operated SD art creation and explicit display selection; no world events."""
import copy,json
from .character_art import atomic,BLOCKED,key
from .model import digest

PUBLIC_SCENES={'shared':'a peaceful shared courtyard with flowers and wooden benches','district':'a quiet neighborhood street with shops','library':'a warm library with bookshelves and reading tables','cafe':'a cozy cafe with coffee cups and wooden tables','park':'a riverside park with trees and flower beds','zoo':'an outdoor zoo walkway with trees and habitat signs','gallery':'an art gallery with framed paintings','cinema':'a small cinema lobby with soft lights','restaurant':'a warm restaurant with a set dining table','market':'an outdoor craft market with handmade goods on stalls','boutique':'a clothing shop with racks of daily clothes','pool':'a public outdoor swimming pool with swimming lanes and deck chairs'}

class ArtAtelier:
 def __init__(self,session):
  self.s=session;self.path=session.root/'art-atelier.json';self.config={'prefer_sd':{},'cg':None}
  try:
   v=json.loads(self.path.read_text(encoding='utf-8'))
   if isinstance(v,dict) and set(v)==set(self.config) and isinstance(v['prefer_sd'],dict):self.config=v
  except (OSError,ValueError):pass
  from .cg_timeline import CGTimeline
  self.timeline=CGTimeline(self)
  from .character_pipeline import CharacterPipeline
  self.pipeline=CharacterPipeline(self)
 def public_cg_scenes(self):return {k for k in PUBLIC_SCENES if k in self.s.map_spec['maps']}
 def scope(self,actor):return actor+':'+self.s.wardrobe.appearance(actor)['render_key']
 def prefers(self,actor,outfit):return self.config['prefer_sd'].get(actor+':'+outfit['render_key'],False)
 def selected_cg(self):
  j=self.s.studio.jobs.get(self.config['cg'])
  if not j or j['kind']!='cg' or j['status']!='ready' or not j['files'].get('cg'):return None
  return {'job_id':j['id'],'url':'/character-art/'+j['files']['cg'],'actor':j['actor'],'scene':copy.deepcopy(j['scene'])}
 def state(self):
  with self.s.lock:
   data=self.s.studio.state();bindings={a:digest(data['config']['profiles'].get(a)) for a in self.s.character_setup.profiles}
   for a in self.s.character_setup.profiles:
    data['config']['profiles'].setdefault(a,{'identity':self.s.character_setup.current(self.s,a)['appearance'] or 'adult person, everyday appearance','trigger':'','lora':'','weight':.8,'clothes_lora':'','clothes_weight':.6,'seed':4100+(10 if a=='player' else int(a[-2:])-1),'auto':False,'expression':'neutral'})
   data['atelier']={'bindings':bindings,'outfits':{a:self.s.wardrobe.appearance(a) for a in self.s.character_setup.profiles},'prefer_sd':copy.deepcopy(self.config['prefer_sd']),'cg':self.selected_cg(),'public_scenes':{k:v['name'] for k,v in self.s.map_spec['maps'].items() if not k.startswith('room-')},'default_scene':self.s.space.entities['player']['scene']}
   data['atelier']['pipeline']=self.pipeline.state()
   return data
 def operation(self,p):
  if not isinstance(p,dict) or not isinstance(p.get('command'),str):raise ValueError('無效美術工坊操作')
  command=p['command']
  if command in ('cg_gallery','cg_timeline_config','cg_select'):return self.timeline.operation(p)
  if command=='refresh_sd_capabilities':
   if set(p)!={'command'}:raise ValueError('無效的功能清單更新')
   self.s.studio.probe();return self.state()
  if command in ('save_character','retry_character','cancel_character','build_saved_character'):return self.pipeline.operation(p)
  if command=='state' and set(p)=={'command'}:return self.state()
  actor=p.get('actor')
  if actor not in self.s.character_setup.profiles:raise ValueError('請選玩家或共居角色')
  if command=='binding' and set(p)=={'command','actor','profile','before'}:
   with self.s.lock,self.s.studio.lock:
    if p['before']!=digest(self.s.studio.config['profiles'].get(actor)):raise ValueError('SD 人物設定已改變，請重新讀取')
    profiles=copy.deepcopy(self.s.studio.config['profiles']);profiles[actor]=p['profile'];self.s.studio.configure({'profiles':profiles})
  elif command=='generate' and set(p)=={'command','actor','kind','scene','description'}:
   if p['kind'] not in {'portrait','pixel','both','cg'}:raise ValueError('未知生成用途')
   if not isinstance(p['description'],str) or len(p['description'])>600 or BLOCKED.search(p['description']):raise ValueError('描述目前只接受600字內的成年 SFW 美術')
   scene=None
   if p['kind']=='cg':
    places={k:v for k,v in self.s.map_spec['maps'].items() if not k.startswith('room-')}
    if p['scene'] not in places:raise ValueError('CG 草稿請選公共場景')
    scene={'scene':p['scene'],'place_name':places[p['scene']]['name'],'description':PUBLIC_SCENES.get(p['scene'],'a peaceful public daily-life setting')+(', '+p['description'].strip() if p['description'].strip() else '')}
   elif p['scene'] is not None or p['description']:raise ValueError('立繪與像素請使用已保存的固定模板')
   with self.s.lock:
    outfit=self.s.wardrobe.appearance(actor);prompt=self.s.art_outfit_prompt(actor)
    with self.s.studio.lock:
     job=self.s.studio.submit(actor,outfit,prompt,p['kind'],scene,follow_identity=True)
     self.s.studio.jobs[job['id']]['source']='atelier';self.s.studio._persist()
  elif command=='apply' and set(p)=={'command','actor','id','expression'}:
   with self.s.lock,self.s.studio.lock:
    j=self.s.studio.jobs.get(p['id'])
    if not j or j['actor']!=actor or j['status']!='ready':raise ValueError('只能套用這位人物已完成的素材')
    if j['kind']=='cg':
     if not j['files'].get('cg'):raise ValueError('CG 尚未完成')
     self.config['cg']=j['id']
    else:
     if not (j['files'].get('sprite') or j['files'].get('portraits')):raise ValueError('沒有可套用的人物素材')
     if j['outfit']['render_key']!=self.s.wardrobe.appearance(actor)['render_key']:raise ValueError('素材屬於其他穿著，請穿回同一套再套用')
     profile=self.s.character_setup.current(self.s,actor);recipe=j.get('recipe',{})
     if recipe.get('gender',profile['gender'])!=profile['gender']:raise ValueError('素材性別與目前人物不同')
     if profile['look']['enabled'] and key(recipe.get('look',{}))!=key(profile['look']):raise ValueError('外觀已修改，請重新生成相符的素材')
     self.s.studio.activate(j['id'],p['expression']);self.config['prefer_sd'][self.scope(actor)]=True
    atomic(self.path,self.config)
  elif command=='restore' and set(p)=={'command','actor'}:
   with self.s.lock,self.s.studio.lock:
    pack=self.pipeline.packs.get(actor)
    if pack:
     for jid in pack['jobs'].values():
      if self.s.studio.jobs.get(jid,{}).get('status') in ('queued','running'):self.s.studio.cancel(jid)
     pack.update(status='restored',applied=[k for k in pack['applied'] if k!='both'],message='已恢復原生／匯入美術；人物生成檔仍保留。');self.pipeline.persist()
    scope=self.scope(actor);self.s.studio.config['active'].pop(scope,None);self.config['prefer_sd'].pop(scope,None)
    atomic(self.s.studio.config_path,self.s.studio.config);atomic(self.path,self.config)
  else:raise ValueError('無效美術工坊欄位')
  return self.state()
