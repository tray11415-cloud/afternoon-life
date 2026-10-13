"""SFW scene albums from conversations the player actually heard."""
import copy,json,time
from .character_art import atomic,BLOCKED
from .model import digest


class CGTimeline:
 def __init__(self,atelier):
  self.a=atelier;self.s=atelier.s;self.path=self.s.root/'cg-timeline.json'
  events=self.s.engine._events
  self.data={'version':1,'enabled':True,'interval':6,'auto_show':True,'cursor':len(events),'anchor':events[-1]['hash'] if events else '', 'counts':{},'records':{},'selected':{},'error':''}
  try:
   saved=json.loads(self.path.read_text(encoding='utf-8'))
   if isinstance(saved,dict) and set(saved)==set(self.data) and saved['version']==1 and type(saved['enabled']) is bool and type(saved['auto_show']) is bool and type(saved['interval']) is int and 1<=saved['interval']<=30 and type(saved['cursor']) is int and saved['cursor']>=0 and all(isinstance(saved[k],dict) for k in ('counts','records','selected')):self.data=saved
  except (OSError,ValueError,TypeError):pass

 def persist(self):atomic(self.path,self.data)

 def _scene(self):return self.s.space.entities['player']['scene']

 def _jobs(self,scene=''):
  return [j for j in self.s.studio.jobs.values() if j['kind']=='cg' and isinstance(j.get('scene'),dict) and (not scene or j['scene']['scene']==scene)]

 def _public(self,j):
  return {'job_id':j['id'],'actor':j['actor'],'scene':{'scene':j['scene']['scene'],'place_name':j['scene']['place_name']},'place_name':j['scene']['place_name'],'status':j['status'],'created':j.get('created',0),'url':'/character-art/'+j['files']['cg'] if j['files'].get('cg') else None,'dialogue':j['id'] in self.data['records']}

 def _matches(self,j):
  record=self.data['records'].get(j['id'])
  return not record or (record['profile']==digest(self.s.character_setup.current(self.s,j['actor'])) and record['binding']==digest(self.s.studio.config['profiles'].get(j['actor'])) and record['outfit']==self.s.wardrobe.appearance(j['actor'])['render_key'])

 def state(self):
  with self.s.lock,self.s.studio.lock:
   scene=self._scene();jobs=self._jobs(scene)
   ready=[j for j in jobs if j['status']=='ready' and j['files'].get('cg') and self._matches(j)]
   active=None
   if ready:active=ready[-1]
   choice=self.data['selected'].get(scene,{})
   manual=next((j for j in jobs if j['id']==choice.get('id') and j['status']=='ready' and j['files'].get('cg')),None)
   if manual and (not ready or choice.get('seen')==ready[-1]['id']):active=manual
   return {'enabled':self.data['enabled'],'interval':self.data['interval'],'auto_show':self.data['auto_show'],'scene':scene,'count':len(jobs),'active':self._public(active) if active else None,'error':self.data['error']}

 def observe(self):
  # Called only after explicit game actions, never a GET or startup scan.
  with self.s.lock,self.s.studio.lock:
   events=self.s.engine._events;cursor=self.data['cursor']
   if cursor>len(events) or (cursor and events[cursor-1]['hash']!=self.data['anchor']):
    self.data.update(cursor=len(events),anchor=events[-1]['hash'] if events else '',counts={},error='');self.persist();return
   if cursor==len(events):return
   fresh=events[cursor:];self.data.update(cursor=len(events),anchor=events[-1]['hash'])
   scene=self._scene();candidates={}
   if self.data['enabled'] and scene in self.a.public_cg_scenes():
    for event in fresh:
     if event['kind'] not in ('message_spoken','city_spoken','group_spoken') or 'player' not in event['audience']:continue
     text=event['data'].get('text','')
     if not isinstance(text,str) or not text.strip() or BLOCKED.search(text):continue
     speaker=event['actor'];target=event['data'].get('target')
     actor=target if speaker=='player' and target in self.s.character_setup.profiles else speaker
     if actor not in self.s.character_setup.profiles:actor='player'
     entity=self.s.space.entities.get(actor)
     if not entity or entity['scene']!=scene:continue
     key=scene+':'+actor;self.data['counts'][key]=self.data['counts'].get(key,0)+1
     candidates[actor]={'key':key,'text':text[:420],'event':event['id']}
    for actor,context in candidates.items():
     if self.data['counts'][context['key']]<self.data['interval']:continue
     if not self.s.studio.services.get(self.s.studio.config['url'],{}).get('ready'):
      self.data['error']='對話 CG 等待本機 SD 連線。';continue
     if any(j.get('status') in ('queued','running') and j.get('actor')==actor and j.get('scene',{}).get('scene')==scene for jid,j in self.s.studio.jobs.items() if jid in self.data['records']):continue
     try:
      from .art_atelier import PUBLIC_SCENES
      description=PUBLIC_SCENES[scene]+', candid everyday conversation, nonsexual daily life, fully clothed adults. Spoken context only: '+context['text']
      cg={'scene':scene,'place_name':self.s.map_spec['maps'][scene]['name'],'description':description[:1200]}
      outfit=self.s.wardrobe.appearance(actor)
      job=self.s.studio.submit(actor,outfit,self.s.art_outfit_prompt(actor),'cg',cg,follow_identity=True)
      self.s.studio.jobs[job['id']]['source']='dialogue-cg';self.s.studio._persist()
      self.data['records'][job['id']]={'event':context['event'],'profile':digest(self.s.character_setup.current(self.s,actor)),'binding':digest(self.s.studio.config['profiles'].get(actor)),'outfit':outfit['render_key']}
      self.data['counts'][context['key']]=0;self.data['error']=''
     except (ValueError,RuntimeError,KeyError) as exc:self.data['error']=str(exc)[:250]
   self.persist()

 def operation(self,p):
  command=p['command']
  with self.s.lock,self.s.studio.lock:
   if command=='cg_gallery' and set(p)=={'command','scene','page'}:
    if not isinstance(p['scene'],str) or p['scene'] and p['scene'] not in self.a.public_cg_scenes() or type(p['page']) is not int or p['page']<0:raise ValueError('請選公共 CG 場景與有效頁數。')
    jobs=list(reversed(self._jobs(p['scene'])));pages=max(1,(len(jobs)+19)//20);page=min(p['page'],pages-1)
    return {'gallery':{'scene':p['scene'],'page':page,'pages':pages,'total':len(jobs),'items':[self._public(j) for j in jobs[page*20:(page+1)*20]]},'timeline':self.state()}
   if command=='cg_timeline_config' and set(p)=={'command','enabled','interval','auto_show'}:
    if type(p['enabled']) is not bool or type(p['auto_show']) is not bool or type(p['interval']) is not int or not 1<=p['interval']<=30:raise ValueError('CG 對話間隔需為 1–30 句。')
    # Start from current progress when explicitly enabled; do not replay history.
    if p['enabled'] and not self.data['enabled']:
     events=self.s.engine._events;self.data.update(cursor=len(events),anchor=events[-1]['hash'] if events else '',counts={})
    self.data.update({k:p[k] for k in ('enabled','interval','auto_show')});self.data['error']='';self.persist();return {'timeline':self.state()}
   if command=='cg_select' and set(p)=={'command','id'}:
    j=self.s.studio.jobs.get(p['id'])
    if not j or j['kind']!='cg' or j['status']!='ready' or not j['files'].get('cg'):raise ValueError('請選已完成的 CG。')
    ready=[x for x in self._jobs(j['scene']['scene']) if x['status']=='ready' and x['files'].get('cg') and self._matches(x)]
    self.data['selected'][j['scene']['scene']]={'id':j['id'],'seen':ready[-1]['id'] if ready else j['id']};self.persist()
    self.a.config['cg']=j['id'];atomic(self.a.path,self.a.config);return {'timeline':self.state()}
  raise ValueError('無效場景 CG 操作')
