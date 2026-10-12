"""Multi-person plans with individual consent, physical attendance and spending.

Every outcome is journalled inside the engine's command/clock transaction.
Invitations and conversations only enter their authorized members' memories.
"""
import copy,hashlib
from .model import Action,Rejected

SCHEMAS={'group_create':{'venue','item','title','participants','start','duration'},
 'group_respond':{'group','accept'},'group_cancel':{'group'},'group_leave':{'group'},
 'group_say':{'group','text'}}
PUBLIC_VENUES={'shared','library','cafe','zoo','gallery','cinema','restaurant','park','market','boutique','pool'}
OPEN={'planned','active'}

def apply_social(state,event):
 groups=state.setdefault('groups',{});d=event['data'];kind=event['kind'];actor=event['actor']
 if kind=='group_created':groups[d['id']]=copy.deepcopy(d);return
 g=groups[d['group']]
 if kind=='group_response':g['responses'][actor]=d['response']
 elif kind=='group_started':
  g.update(status='active',attendees=list(d['attendees']),actual_start=event['tick'],ends_at=d['ends_at'])
  for who in g['members']:
   if who not in g['attendees'] and g['responses'][who] in ('accepted','pending'):g['responses'][who]='missed'
  for who in g['attendees']:
   a=state['actors'][who];a['group_id']=g['id']
   if not g['item']:a.update(activity='gathering',busy_until=d['ends_at'],activity_ref=g['id'])
 elif kind=='group_left':
  g['responses'][actor]='left'
  if actor in g.get('attendees',[]):g['attendees'].remove(actor)
  a=state['actors'][actor]
  if a.get('group_id')==g['id']:
   a['group_id']=None;a.update(activity='idle',busy_until=event['tick'],activity_ref=None)
   if a.get('venue_job',{}):a['venue_job']=None
 elif kind=='group_closed':
  g.update(status=d['status'],closed_at=event['tick'],reason=d.get('reason',''))
  for who in g['members']:
   if g['responses'][who]=='pending':g['responses'][who]='expired'
   a=state['actors'][who]
   if a.get('group_id')==g['id']:
    a['group_id']=None
    if not a.get('venue_job'):a.update(activity='idle',busy_until=event['tick'],activity_ref=None)
 elif kind=='group_spoken':g.setdefault('messages',[]).append({'id':event['id'],'actor':actor,'text':d['text'],'tick':event['tick'],'audience':list(event['audience'])})
 else:raise ValueError('unknown social event')

def group_conflict(state,actor,start,end,exclude=None):
 return any(g['id']!=exclude and g['status'] in OPEN and g['responses'].get(actor)=='accepted'
   and start<g.get('ends_at',g['reserve_end']) and g['start']<end for g in state.get('groups',{}).values())

def assert_social(state):
 for gid,g in state.get('groups',{}).items():
  if g['id']!=gid or len(set(g['members']))!=len(g['members']) or not 2<=len(g['members'])<=11 or g['host'] not in g['members'] or any(a not in state['actors'] for a in g['members']):raise ValueError('invalid group membership')
  if set(g['responses'])!=set(g['members']) or g['status'] not in {'planned','active','completed','cancelled','missed'}:raise ValueError('invalid group status')
  if not set(g.get('attendees',[]))<=set(g['members']):raise ValueError('invalid attendance')
  if len(g.get('messages',[]))>200:raise ValueError('group transcript too large')

class GroupActivities:
 def __init__(self,session):self.session=session;self.bind()
 def bind(self):
  self.engine=self.session.engine;self.engine.social_handler=self.handle;self.engine.social_clock=self.clock
 def groups(self):return self.engine._state.get('groups',{})
 def own(self,actor):return self.engine._state['actors'][actor]
 def visible(self,actor):return [g for g in self.groups().values() if actor in g['members']]
 def _get(self,actor,gid):
  if not isinstance(gid,str):raise Rejected('group_not_visible')
  g=self.groups().get(gid)
  if not g or actor not in g['members']:raise Rejected('group_not_visible')
  return g
 def _emit(self,kind,actor,data,audience):self.engine._emit(kind,actor,data,audience)
 def handle(self,actor,action):
  p=action.params;own=self.own(actor);tick=self.engine.tick
  if action.kind=='group_create':
   if own['busy_until']>tick:raise Rejected('actor_busy')
   venue=p['venue'];invitees=p['participants']
   if venue not in PUBLIC_VENUES or venue not in self.engine._state['locations']:raise Rejected('invalid_group_venue')
   if not isinstance(invitees,list) or not 1<=len(invitees)<=10 or any(not isinstance(a,str) or a not in self.engine._state['actors'] or a==actor for a in invitees) or len(set(invitees))!=len(invitees):raise Rejected('invalid_group_members')
   if not isinstance(p['title'],str) or not 1<=len(p['title'].strip())<=100 or not isinstance(p['item'],str):raise Rejected('invalid_group_title')
   if type(p['start']) is not int or not tick+3<=p['start']<=tick+720 or type(p['duration']) is not int or not 3<=p['duration']<=60:raise Rejected('invalid_group_time')
   row=None
   if p['item']:
    if venue=='shared':raise Rejected('unknown_item')
    row=next((r for r in self.session.facilities.items(venue) if r['id']==p['item']),None)
    if not row or row.get('command'):raise Rejected('unknown_item')
    if venue=='library' and not row.get('text'):raise Rejected('text_unavailable')
    if venue=='cinema' and self.session.facilities.items(venue)[0]['id']!=row['id']:raise Rejected('not_now_showing')
   duration=row['minutes'] if row else p['duration'];end=p['start']+duration+10
   if self.engine._conflict(actor,p['start'],end) or own['busy_until']>p['start']:raise Rejected('commitment_conflict')
   if sum(g['status'] in OPEN and g['host']==actor for g in self.groups().values())>=3:raise Rejected('group_limit')
   price=row['price'] if row else 0
   if own.get('wallet',500)<price:raise Rejected('insufficient_funds')
   members=[actor]+invitees;obj=self.session.map_spec['maps'][venue]['objects'][0]
   anchor={'x':obj['x'],'y':obj['y']};spots=[];m=self.session.map_spec['maps'][venue]
   for radius in range(1,7):
    for dx in range(-radius,radius+1):
     for dy in range(-radius,radius+1):
      x,y=obj['x']+dx,obj['y']+dy
      if abs(dx)+abs(dy)!=radius or not self.session.space.passable(venue,x,y) or any(po['x']==x and po['y']==y for po in m['portals']):continue
      if self.session.space.line_clear(venue,(x,y),(obj['x'],obj['y'])):spots.append({'x':x,'y':y})
   if len(spots)<len(members):raise Rejected('group_space_full')
   gid=f'group-{self.engine.revision+1:08d}'
   group={'id':gid,'host':actor,'members':members,'responses':{a:'accepted' if a==actor else 'pending' for a in members},
    'venue':venue,'item':p['item'],'title':p['title'].strip(),'item_title':row['title'] if row else '一起散步與聊天',
    'price':price,'start':p['start'],'duration':duration,'reserve_end':end,'status':'planned','attendees':[],
    'anchor':anchor,'spots':dict(zip(members,spots)),'messages':[],'created':tick}
   self._emit('group_created',actor,group,members);return
  g=self._get(actor,p['group'])
  if action.kind=='group_respond':
   if type(p['accept']) is not bool or actor==g['host'] or g['status']!='planned' or g['responses'][actor]!='pending' or tick>=g['start']:raise Rejected('group_invitation_closed')
   if p['accept'] and (own['busy_until']>g['start'] or self.engine._conflict(actor,g['start'],g['reserve_end']) or own.get('wallet',500)<g['price']):raise Rejected('commitment_conflict')
   self._emit('group_response',actor,{'group':g['id'],'response':'accepted' if p['accept'] else 'declined'},g['members']);return
  if action.kind=='group_cancel':
   if g['host']!=actor or g['status']!='planned':raise Rejected('group_cancel_not_allowed')
   self._emit('group_closed',actor,{'group':g['id'],'status':'cancelled','reason':'host_cancelled'},g['members']);return
  if action.kind=='group_leave':
   if g['status'] not in OPEN or g['responses'][actor] not in ('pending','accepted'):raise Rejected('group_invitation_closed')
   if actor==g['host'] and g['status']=='planned':
    self._emit('group_closed',actor,{'group':g['id'],'status':'cancelled','reason':'host_cancelled'},g['members']);return
   self._emit('group_left',actor,{'group':g['id']},g['members']);return
  if action.kind=='group_say':
   if g['status']!='active' or actor not in g['attendees'] or not self.arrived(actor,g):raise Rejected('group_not_here')
   if not isinstance(p['text'],str) or not 1<=len(p['text'].strip())<=1200 or len(g['messages'])>=200:raise Rejected('invalid_group_text')
   audience=[a for a in g['attendees'] if self.arrived(a,g)]
   self._emit('group_spoken',actor,{'group':g['id'],'text':p['text'].strip()},audience);return
  raise Rejected('invalid_action_params')

 def arrived(self,actor,g):
  e=self.session.space.entities[actor];a=g['anchor']
  return e['scene']==g['venue'] and abs(e['x']-a['x'])+abs(e['y']-a['y'])<=6 and self.session.space.line_clear(g['venue'],(e['x'],e['y']),(a['x'],a['y']))

 def clock(self):
  tick=self.engine.tick
  for g in list(self.groups().values()):
   if g['status']=='active':
    if tick>=g['ends_at']:
     if not g['item']:
      for actor in g['attendees']:
       own=self.own(actor)
       if own.get('life'):
        needs=copy.deepcopy(own['life']['needs']);needs['fatigue']=max(0,needs['fatigue']-10);needs['curiosity']=max(0,needs['curiosity']-8)
        self.engine._emit('economy_needs',actor,{'needs':needs},[actor],remember=False)
     self._emit('group_closed',None,{'group':g['id'],'status':'completed','reason':'activity_finished'},g['members'])
    elif len(g['attendees'])<2:
     # Remaining participants may finish their already paid individual item.
     self._emit('group_closed',None,{'group':g['id'],'status':'cancelled','reason':'too_few_participants'},g['members'])
    continue
   if g['status']!='planned' or tick<g['start']:continue
   candidates=[a for a in g['members'] if g['responses'][a]=='accepted' and self.own(a)['busy_until']<=tick and self.arrived(a,g) and self.own(a).get('wallet',500)>=g['price']]
   if len(candidates)>=2 and g['host'] in candidates:
    resolved={}
    if g['item']:
     for actor in candidates:
      try:
       result=self.session.facilities.resolve(actor,g['item'],group_anchor=g['anchor'])
       if result['price']==g['price'] and result['minutes']==g['duration'] and self.own(actor).get('wallet',500)>=result['price']:resolved[actor]=result
      except Rejected:pass
     candidates=[a for a in candidates if a in resolved]
    if len(candidates)>=2 and g['host'] in candidates:
     end=tick+g['duration']
     self._emit('group_started',None,{'group':g['id'],'attendees':candidates,'ends_at':end},candidates)
     for actor in candidates:
      if actor in resolved:
       data={**resolved[actor],'ends_at':end,'group':g['id']};self._emit('venue_started',actor,data,[actor])
     continue
   if tick>=g['start']+10:self._emit('group_closed',None,{'group':g['id'],'status':'missed','reason':'not_enough_arrivals'},g['members'])

 def native(self,actor,index):
  own=self.own(actor);tick=self.engine.tick
  for g in self.visible(actor):
   if g['status']=='planned' and g['responses'][actor]=='pending' and tick<g['start']:
    needs=own.get('life',{}).get('needs',{});preferred=('park','cafe','library','restaurant','zoo','gallery','park','cinema','park','library')[index%10]
    choice=int(hashlib.sha256((actor+g['id']).encode()).hexdigest()[:2],16)%4
    willing=(needs.get('fatigue',0)<85 and own.get('wallet',500)>=g['price'] and own['busy_until']<=g['start'] and not self.engine._conflict(actor,g['start'],g['reserve_end']) and (choice!=0 or g['venue']==preferred or needs.get('curiosity',0)>45))
    self.engine.dispatch(actor,Action('group_respond',{'group':g['id'],'accept':willing}),f'group-choice:{g["id"]}:{actor}')
  plans=sorted((g for g in self.visible(actor) if g['status']=='planned' and g['responses'][actor]=='accepted'),key=lambda g:g['start'])
  if plans:
   g=plans[0]
   if own['busy_until']>tick:return True
   e=self.session.space.entities[actor]
   if e['scene']!=g['venue']:
    if self.session.space.flags.get('journeys',{}).get(actor)!=g['venue']:self.session.space.route_to(actor,g['venue'])
   else:
    spot=g['spots'][actor]
    if not e['path'] and (e['x'],e['y'])!=(spot['x'],spot['y']):self.session.space.walk_to(actor,spot['x'],spot['y'])
   return True
  if own.get('group_id'):return True
  # Native, clearly labelled desire rule; never fabricated speech/model calls.
  if tick>0 and tick%180==index*7 and own['busy_until']<=tick and own['goal']['progress']>=own['goal']['target'] and not any(g['status'] in OPEN and g['host']==actor for g in self.groups().values()):
   nearby=[a['id'] for a in self.engine.view(actor)['nearby']]
   if len(nearby)>=2:
    self.engine.dispatch(actor,Action('group_create',{'venue':'park','item':'','title':'一起到公園走走','participants':nearby[:2],'start':tick+20,'duration':10}),f'group-native:{actor}:{tick}')
    return True
  return False

 def browse(self,actor):
  result=[]
  for g in self.visible(actor)[-30:]:
   row={k:copy.deepcopy(g[k]) for k in ('id','host','venue','title','item_title','price','start','duration','status','responses','attendees','messages','created')}
   row['members']=[{'id':a,'name':self.own(a)['name']} for a in g['members']]
   row['messages']=[{k:m[k] for k in ('id','actor','text','tick')} for m in g['messages'] if actor in m['audience']]
   row['ends_at']=g.get('ends_at');row['arrived']=self.arrived(actor,g);row['self_response']=g['responses'][actor]
   row['can_speak']=g['status']=='active' and actor in g['attendees'] and row['arrived'];row['anchor']=copy.deepcopy(g['anchor'])
   result.append(row)
  return {'groups':result,'native_consent':'邀約以每人的安排、喜好、需要及可負擔金額判斷；交談才按操作使用 Grok 4.3。'}

 def context(self,actor):
  rows=self.browse(actor)['groups'];compact=[]
  for g in rows:
   if g['status'] in OPEN:compact.append({k:g[k] for k in ('id','host','venue','title','start','status','self_response','members','attendees','can_speak')})
  return {'plans':compact,'rule':'只扮演你自己。接受邀約不等於已到場；只有實際在同一活動的成員聽到 group_say。其他人的背景、錢包和私有記憶不可臆測。'}

 def planner(self):
  s=self.session;venues=[{'id':'shared','name':'公共庭院','items':[]}]
  for venue,v in s.facilities.data.items():
   rows=s.facilities.items(venue)
   if venue=='cinema':rows=rows[:1]
   rows=[r for r in rows if not r.get('command') and (venue!='library' or r.get('text'))]
   venues.append({'id':venue,'name':v['name'],'items':[{k:r[k] for k in ('id','title','price','minutes')} for r in rows]})
  return {'venues':venues,'rules':'每個人自行接受邀約、走到集合點，各付自己的費用。開始時間後最多等十分鐘；邀請者與至少一位同伴到場才開始。'}
