"""One character save owns a resumable local art pipeline, never another actor's job."""
import copy,json,re,secrets,threading,time
from pathlib import Path
from .character_art import atomic,BLOCKED,EXPRESSIONS,validate_binding
from .characters import validate_profile
from .model import digest

LORA_TAG=re.compile(r'<lora:([^<>:]+):([0-9]+(?:\.[0-9]+)?)>',re.I)
class QueueBusy(ValueError):pass

class CharacterPipeline:
 def __init__(self,atelier):
  self.a=atelier;self.s=atelier.s;self.path=self.s.root/'character-pipelines.json';self.packs={};self.closed=False;self.thread=None;self.wake=threading.Event()
  try:
   value=json.loads(self.path.read_text(encoding='utf-8'))
   if value.get('version')==1 and isinstance(value.get('packs'),dict):self.packs=value['packs']
  except (OSError,ValueError,AttributeError):pass
 def start(self):
  if self.thread is None:self.thread=threading.Thread(target=self._watch,daemon=True);self.thread.start()
 def close(self):
  self.closed=True
  self.wake.set()
  if self.thread:self.thread.join(2)
 def state(self):
  return {'packs':copy.deepcopy(self.packs),'fingerprints':{a:digest(self.s.character_setup.current(self.s,a)) for a in self.s.character_setup.profiles},'template_fingerprints':{a:digest(p) for a,p in self.s.character_setup.profiles.items()}}
 def persist(self):atomic(self.path,{'version':1,'packs':self.packs})
 def normalize(self,profile,sd,actor):
  if not isinstance(sd,dict):raise ValueError('無效的 SD 人物配方。')
  p=validate_profile(profile);binding=copy.deepcopy(sd);prompt=p.get('appearance','').strip()
  if BLOCKED.search(prompt):raise ValueError('請使用成年日常角色 prompt。')
  tags=LORA_TAG.findall(prompt)
  if len(tags)>2:raise ValueError('角色 prompt 最多包含角色與服裝兩個 LoRA；其他功能請用進階 SD 模板。')
  for index,(name,weight) in enumerate(tags):
   found=[r for r in self.s.studio.resources.values() if r['category']=='lora' and r['selectable'] and self.s.studio.config['installation'] in r['installations'] and name.lower() in {r['name'].lower(),Path(r['name']).stem.lower()}]
   if len(found)!=1:raise ValueError('LoRA 名稱沒有唯一對應的本機資源：'+name)
   field='lora' if index==0 else 'clothes_lora';binding[field]=found[0]['id'];binding['weight' if index==0 else 'clothes_weight']=float(weight)
  prompt=LORA_TAG.sub('',prompt).strip(' ,\n')
  if '<' in prompt or '>' in prompt:raise ValueError('角色 prompt 的 LoRA 標籤格式不正確。')
  from .looks import look_prompt
  identity=prompt or (look_prompt(p.get('look')) if p.get('look',{}).get('enabled') else '') or ('adult person' if binding.get('lora') else '')
  p['appearance']=prompt;binding.update(identity=identity,auto=False)
  binding=validate_binding(binding)
  previous=self.s.studio.config['profiles'].get(actor,{})
  for field in ('lora','clothes_lora','style_lora','checkpoint'):
   rid=binding.get(field,'')
   if not isinstance(rid,str):raise ValueError('無效 LoRA ID。')
   if rid:
    resource=self.s.studio.resources.get(rid)
    if not resource:
     if rid!=previous.get(field):raise ValueError('LoRA 已不存在，請重新選擇。')
    elif resource['category']!=('checkpoint' if field=='checkpoint' else 'lora') or not resource['selectable'] or self.s.studio.config['installation'] not in resource['installations']:raise ValueError('請選此安裝內可用的底模或 LoRA。')
  extra=[(e['lora'],'lora') for e in binding.get('style_loras',[]) if e['lora']]
  ref=binding.get('render_options',{}).get('refiner',{}).get('checkpoint')
  if ref:extra.append((ref,'checkpoint'))
  old_ids={e['lora'] for e in previous.get('style_loras',[])}|{previous.get('render_options',{}).get('refiner',{}).get('checkpoint')}
  for rid,category in extra:
   r=self.s.studio.resources.get(rid)
   if not r:
    if rid not in old_ids:raise ValueError('進階配方的模型已不存在，請重新選擇')
   elif r['category']!=category or not r['selectable'] or self.s.studio.config['installation'] not in r['installations']:raise ValueError('請選目前安裝內的進階配方模型')
  return p,binding
 def _matches(self,pack):
  return digest(self.s.character_setup.current(self.s,pack['actor']))==pack['profile_fingerprint'] and digest(self.s.studio.config['profiles'].get(pack['actor']))==pack['binding_fingerprint'] and self.a.scope(pack['actor'])==pack['scope']
 def _enqueue(self,pack):
  actor=pack['actor'];outfit=self.s.wardrobe.appearance(actor);prompt=self.s.art_outfit_prompt(actor)
  scene=pack['scene'];description=pack['description']
  from .art_atelier import PUBLIC_SCENES
  cg={'scene':scene,'place_name':self.s.map_spec['maps'][scene]['name'],'description':PUBLIC_SCENES.get(scene,'a peaceful public daily-life setting')+(', '+description if description else '')}
  recipes={kind:self.s.studio.recipe(actor,outfit,prompt,kind,cg if kind=='cg' else None,follow_identity=True) for kind in ('both','cg')}
  if any(self.s.studio.jobs.get(jid,{}).get('cancel') and self.s.studio.jobs[jid]['status'] in ('queued','running') for jid in pack['jobs'].values()):raise QueueBusy('正在結束上一次單張生成，稍後自動接續。')
  for kind in ('both','cg'):
   previous=self.s.studio.jobs.get(pack.get('previous_jobs',{}).get(kind),{})
   if previous.get('status') in ('ready','queued','running') and not previous.get('cancel') and digest({k:v for k,v in previous.get('recipe',{}).items() if k!='scene_nonce'})==digest(recipes[kind]):pack['jobs'][kind]=previous['id']
  todo=[kind for kind in ('both','cg') if self.s.studio.jobs.get(pack['jobs'].get(kind),{}).get('status') not in ('ready','queued','running')]
  # Preflight both requests before putting either in the queue.
  if len(self.s.studio.pending)+len(todo)>12:raise QueueBusy('等待其他 SD 任務完成；人物已保存，會自動接續。')
  for kind in todo:
   job=self.s.studio.submit(actor,outfit,prompt,kind,cg if kind=='cg' else None,follow_identity=True);pack['jobs'][kind]=job['id']
   self.s.studio.jobs[job['id']]['source']='character-pipeline'
  self.s.studio._persist();pack.update(status='queued',message='人物已保存，正在製作立繪差分、行走圖與 CG。')
 def save(self,p):
  if set(p)!={'command','actor','mode','profile','before','sd','binding_before','scene','description'} or p['mode'] not in ('current','template'):raise ValueError('無效的一鍵人物設定。')
  actor=p['actor']
  if actor not in self.s.character_setup.profiles:raise ValueError('未知人物。')
  if not isinstance(p['description'],str) or len(p['description'])>600 or BLOCKED.search(p['description']):raise ValueError('CG 描述最多600字，使用日常 SFW 構圖。')
  places={k for k in self.s.map_spec['maps'] if not k.startswith('room-')}
  if p['scene'] not in places:raise ValueError('請選 CG 公共場景。')
  with self.s.lock,self.s.studio.lock:
   original=self.s.character_setup.current(self.s,actor) if p['mode']=='current' else self.s.character_setup.profiles[actor]
   if digest(original)!=p['before'] or digest(self.s.studio.config['profiles'].get(actor))!=p['binding_before']:raise ValueError('人物或 SD 配方已由另一頁修改；請重新讀取再保存。')
   profile,binding=self.normalize(p['profile'],p['sd'],actor)
   proposal=None
   if p['mode']=='current':proposal=self.s.character_setup.prepare_current(self.s,actor,profile,p['before'])
   else:
    from .characters import validate_profiles
    templates=copy.deepcopy(self.s.character_setup.profiles);templates[actor]=profile;validate_profiles(templates)
   old=copy.deepcopy(self.s.studio.config);profiles=copy.deepcopy(old['profiles']);profiles[actor]=binding
   # Character data can be saved without an SD installation. Generation is a
   # separate, retryable stage; global/native settings are not rewritten here.
   self.s.studio.config['profiles']=profiles;atomic(self.s.studio.config_path,self.s.studio.config)
   try:
    if proposal:self.s.components.apply(proposal['id'])
    else:self.s.character_setup.configure(templates)
   except Exception:
    self.s.studio.config=old;atomic(self.s.studio.config_path,old);raise
   if p['mode']=='template':return self.a.state()
   return self.begin(actor,p['scene'],p['description'].strip())
 def begin(self,actor,scene='shared',description=''):
  previous=self.packs.get(actor,{});profile=self.s.character_setup.current(self.s,actor)
  pack={'id':secrets.token_hex(12),'actor':actor,'name':profile['name'],'scope':self.a.scope(actor),'profile_fingerprint':digest(profile),'binding_fingerprint':digest(self.s.studio.config['profiles'].get(actor)),'scene':scene,'description':description,'jobs':{},'applied':[],'status':'queued','message':'人物已保存。','created':int(time.time())}
  pack['previous_jobs']=copy.deepcopy(previous.get('jobs',{}));self.packs[actor]=pack
  try:self._enqueue(pack)
  except QueueBusy as e:pack.update(status='waiting',message=str(e))
  except Exception as e:pack.update(status='blocked',message='人物已保存；生圖尚未開始：'+str(e)[:400])
  for jid in set(previous.get('jobs',{}).values())-set(pack['jobs'].values()):
   if self.s.studio.jobs.get(jid,{}).get('status') in ('queued','running'):self.s.studio.cancel(jid)
  self.persist();self.reconcile();return self.a.state()
 def operation(self,p):
  if p.get('command')=='save_character':return self.save(p)
  if set(p)=={'command','actor'} and p['command']=='build_saved_character':
   with self.s.lock,self.s.studio.lock:
    if p['actor'] not in self.s.character_setup.profiles:raise ValueError('未知人物。')
    current=self.s.character_setup.current(self.s,p['actor'])
    if not (current['appearance'].strip() or current['look']['enabled'] or self.s.studio.config['profiles'].get(p['actor'],{}).get('lora')):raise ValueError('請先保存這位人物的角色 prompt。')
    return self.begin(p['actor'])
  if set(p)!={'command','actor','id'} or p['command'] not in ('retry_character','cancel_character'):raise ValueError('無效人物生成操作。')
  with self.s.lock,self.s.studio.lock:
   pack=self.packs.get(p['actor'])
   if not pack or pack['id']!=p['id']:raise ValueError('人物任務已被新的保存取代，請重新讀取。')
   if p['command']=='cancel_character':
    for jid in pack['jobs'].values():
     if self.s.studio.jobs.get(jid,{}).get('status') in ('queued','running'):self.s.studio.cancel(jid)
    pack.update(status='cancelled',message='生成已取消；已保存的人物與已完成素材保留。')
   else:
    if not self._matches(pack):raise ValueError('人物、配方或穿著已改變，請用目前設定重新保存生成。')
    if pack['status'] in ('queued','running','waiting','complete'):return self.a.state()
    try:self._enqueue(pack)
    except QueueBusy as e:pack.update(status='waiting',message=str(e))
    except Exception as e:pack.update(status='blocked',message=str(e)[:500])
   self.persist();return self.a.state()
 def reconcile(self):
  with self.s.lock,self.s.studio.lock:
   changed=False
   for actor,pack in self.packs.items():
    if pack['status'] not in ('queued','running','waiting'):continue
    before=copy.deepcopy(pack)
    if not self._matches(pack):pack.update(status='stale',message='人物或穿著已改變；舊素材保留，沒有套用到新人物。')
    else:
     if pack['status']=='waiting':
      try:self._enqueue(pack)
      except QueueBusy:continue
      except Exception as e:pack.update(status='blocked',message=str(e)[:500]);changed=True;continue
     jobs={kind:self.s.studio.jobs.get(jid) for kind,jid in pack['jobs'].items()}
     if len(jobs)!=2 or any(j is None for j in jobs.values()):pack.update(status='interrupted',message='生成紀錄不完整，請重試。')
     else:
      for kind,j in jobs.items():
       if j['status']=='ready' and kind not in pack['applied']:
        try:
         expression=self.s.studio.config['profiles'][actor]['expression']
         if j['files'].get('portraits') and expression not in j['files']['portraits']:expression='neutral'
         self.a.operation({'command':'apply','actor':actor,'id':j['id'],'expression':expression});pack['applied'].append(kind)
        except Exception as e:pack.update(status='failed',message='素材完成但套用失敗：'+str(e)[:400]);break
      if pack['status']!='failed':
       failed=next((j for j in jobs.values() if j['status'] in ('failed','cancelled','interrupted')),None)
       if failed:pack.update(status='failed',message=failed['message'])
       elif len(pack['applied'])==2:pack.update(status='complete',message='人物已完成：立繪差分、行走圖與 CG 已套用。')
       else:pack.update(status='running',message='正在製作人物；完成的素材會自動套用。')
    changed=changed or before!=pack
   if changed:self.persist()
 def _watch(self):
  while not self.closed:
   try:self.reconcile()
   except Exception as e:
    if not self.closed:
     with self.s.lock:
      for pack in self.packs.values():
       if pack['status'] in ('queued','running','waiting'):pack.update(status='failed',message='人物製作狀態需要重試：'+str(e)[:300])
      self.persist()
   self.wake.wait(.3)
