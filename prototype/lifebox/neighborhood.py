"""Recurring town life and scripted adults, with observed interactions only."""
import copy
from .model import Action,Rejected

NPCS={
 'npc-library':{'name':'林館員','age':42,'gender':'female','venue':'library','line':'今天想找哪一類的書？讀完這一段，也可以聊聊你的想法。'},
 'npc-cafe':{'name':'阿哲','age':31,'gender':'male','venue':'cafe','line':'想喝點什麼？點好之後我來準備，你們可以先坐。'},
 'npc-gallery':{'name':'周策展人','age':38,'gender':'female','venue':'gallery','line':'這次展覽談的是日常裡的微小變化。你對哪件作品最有興趣？'},
 'npc-market':{'name':'陳攤主','age':47,'gender':'male','venue':'market','line':'歡迎逛市集。自己的作品可以寄售，成交之後才有收入。'},
 'npc-park':{'name':'葉志工','age':35,'gender':'female','venue':'park','line':'河岸今天很舒服。活動開始時我們會在公告欄集合。'},
 'npc-pool':{'name':'泳池管理員','age':32,'gender':'male','venue':'pool','line':'下水前先到更衣區換泳裝。請慢慢走，留意其他泳客。'}
}
FESTIVALS=[
 {'id':'river-festival','title':'河岸小祭典','venue':'park','period':7,'offset':0,'hour':17,'minutes':180,'description':'燈飾、街頭音樂與河岸散步；可和在場的人交流。'},
 {'id':'daily-exhibition','title':'日常創作展','venue':'gallery','period':3,'offset':1,'hour':10,'minutes':480,'description':'一般 NPC 策展人的原創遊戲內展覽，展出手作、攝影和日常速寫。'},
 {'id':'makers-market','title':'創作市集','venue':'market','period':4,'offset':2,'hour':14,'minutes':240,'description':'居民帶著自己的作品出攤；實際庫存、付款和成交沿用市集交易。'},
 {'id':'pool-social','title':'泳池交流日','venue':'pool','period':5,'offset':3,'hour':15,'minutes':120,'description':'一般泳池活動；實際下水前必須換泳裝。'}]

def apply_city(state,event):
 d=event['data'];kind=event['kind'];city=state.setdefault('city',{'events':{},'visits':{},'greetings':{},'policy':{'auto_ai':False,'interval':60,'daily_limit':2},'ai_calls':{}})
 if kind=='city_initialized':
  for ident,p in d['npcs'].items():state['actors'][ident]=copy.deepcopy(p)
 elif kind=='city_event_opened':city['events'][d['id']]=copy.deepcopy(d)
 elif kind=='city_event_closed':city['events'][d['id']]['status']='ended'
 elif kind=='city_attended':city['visits'][event['actor']]=copy.deepcopy(d)
 elif kind=='city_greeted':city['greetings'][d['key']]=event['tick']
 elif kind=='city_policy':city['policy']=copy.deepcopy(d)
 elif kind=='city_spoken':pass
 elif kind=='city_ai_budget':city['ai_calls'][str(d['day'])]=d['calls'];city['next_ai']=d['next']
 elif kind=='city_swimwear':
  a=state['actors'][event['actor']];w=a['wardrobe'];a['wallet']-=d['price'];w['owned'][d['item']['id']]=copy.deepcopy(d['item']);w['before_pool']=w['wearing'];w['wearing']=d['item']['id']
 elif kind=='city_pool_return':
  w=state['actors'][event['actor']]['wardrobe'];borrowed=w['wearing'];w['wearing']=w.pop('before_pool');w['owned'].pop(borrowed,None)
 else:raise ValueError('unknown town event')

class Neighborhood:
 def __init__(self,session):self.s=session;self.bind()
 @property
 def npcs(self):return {k:self.s.components.get('npc:'+k) for k in NPCS} if getattr(self.s,'components',None) else NPCS
 @property
 def festivals(self):return self.s.components.get('events:calendar') if getattr(self.s,'components',None) else FESTIVALS
 @property
 def pool_rules(self):return self.s.components.get('rules:pool') if getattr(self.s,'components',None) else {'water':[9,4,22,12],'locker':[5,15],'rental_price':12,'swim_minutes':15}
 @property
 def engine(self):return self.s.engine
 def emit(self,kind,actor,data,audience=(),remember=False):self.engine._emit('city_'+kind,actor,data,audience,remember=remember)
 def bind(self):
  missing={}
  for ident,p in self.npcs.items():
   if ident in self.engine._state['actors']:continue
   item={'id':'initial-'+ident,'title':'工作服','style':'neat','sfw':True,'prompt':'opaque daily work clothes, long sleeves, full length trousers','palette':{'top':'#648b9f','bottom':'#525f64'},'shape':'original','source':{'site':'本作原創'},'lora':{'status':'not_installed','file':None}}
   missing[ident]={'id':ident,'name':p['name'],'age':p['age'],'role':'npc','gender':p['gender'],'location':p['venue'],'goal':{'title':'場所服務','target':0,'progress':0},'activity':'idle','activity_ref':None,'busy_until':0,'memories':[],'relationships':{},'wallet':500,
    'wardrobe':{'owned':{item['id']:item},'wearing':item['id'],'preference':'neat','purchases':{},'pending_wear':None,'plan':None,'next_plan':self.engine.tick},
    'life':{'needs':{'hunger':15,'thirst':15,'fatigue':10,'curiosity':20},'inventory':{},'income':{'wages':0,'sales':0},'shifts':{},'crafted':{},'job':None,'plan':None,'next_plan':self.engine.tick,'purchases':0,'consumed':0}}
  if missing:self.emit('initialized',None,{'npcs':missing})
  self.engine.city_clock=self.clock;self.engine.pool_handler=self.perform_pool;self.s.space.movement_guard=self.may_walk;self.s.space.on_portal=self.clock
  for ident in NPCS:
   if ident not in self.s.space.entities:
    venue=self.engine._state['actors'][ident]['location'];obj=self.s.map_spec['maps'][venue]['objects'][0]
    positions=[(obj['x']+dx,obj['y']+dy) for dx,dy in [(2,0),(-2,0),(0,-2),(3,0),(0,3)]]
    pos=next((p for p in positions if self.s.space.passable(venue,*p) and not self.s.space.occupied(venue,*p)),None)
    if not pos:raise ValueError('沒有一般 NPC 的站立位置')
    self.s.space.entities[ident]={'id':ident,'scene':venue,'x':pos[0],'y':pos[1],'direction':'down','path':[],'destination':None,'walking':False}
  self.clock()
 def day(self):return (self.engine.tick+840)//1440
 def schedule(self,days=4):
  rows=[]
  for day in range(self.day(),self.day()+days):
   for f in self.festivals:
    if day%f['period']==f['offset']:
     start=day*1440+f['hour']*60-840;end=start+f['minutes']
     if end<=self.engine.tick:continue
     rows.append({**f,'id':f['id']+'-'+str(day),'day':day+1,'start':start,'end':end,'status':'active' if start<=self.engine.tick<end else 'upcoming'})
  return sorted(rows,key=lambda r:r['start'])
 def clock(self):
  state=self.engine._state.setdefault('city',{'events':{},'visits':{},'greetings':{},'policy':{'auto_ai':False,'interval':60,'daily_limit':2},'ai_calls':{}})
  for row in self.schedule():
   if row['status']=='active' and row['id'] not in state['events']:self.emit('event_opened',None,row,list(self.engine._state['actors']),True)
  for ident,row in list(state['events'].items()):
   if row['status']=='active' and row['end']<=self.engine.tick:self.emit('event_closed',None,{'id':ident})
  for actor,a in self.engine._state['actors'].items():
   w=a.get('wardrobe',{})
   if w.get('before_pool') and a['location']!='pool':self.emit('pool_return',actor,{},[actor],True)
 def active(self):return [r for r in self.engine._state.get('city',{}).get('events',{}).values() if r['status']=='active' and r['start']<=self.engine.tick<r['end']]
 def step_npcs(self):
  hour=((self.engine.tick+840)%1440)//60
  for index,(n,p) in enumerate(self.npcs.items()):
   if self.s.social.native(n,index):continue
   own=self.engine._state['actors'][n];e=self.s.space.entities[n];target=p['venue'] if 8<=hour<23 else 'shared'
   if own['busy_until']>self.engine.tick or e['path'] or e['destination'] or self.s.space.flags.get('journeys',{}).get(n):continue
   if own['location']!=target:self.s.space.route_to(n,target)
 def native(self,actor,index):
  own=self.engine._state['actors'][actor];e=self.s.space.entities[actor]
  if own['busy_until']>self.engine.tick:return False
  if own['goal']['progress']<own['goal']['target']:return False
  # Reservations and personal income plans have precedence over festivals.
  if self.engine._conflict(actor,self.engine.tick,self.engine.tick+8) or own.get('life',{}).get('job'):return False
  events=self.active();visit=self.engine._state['city']['visits'].get(actor)
  if visit and visit['until']>self.engine.tick:events=[r for r in events if r['id']==visit['event']]
  if not events:return False
  if e['path'] or e['destination']:return True if visit and visit['until']>self.engine.tick else False
  event=events[index%len(events)]
  if not visit or visit['event']!=event['id']:
   self.emit('attended',actor,{'event':event['id'],'until':min(event['end'],self.engine.tick+35)},[actor])
  elif visit['until']<=self.engine.tick:return False
  if e['scene']!=event['venue']:self.s.space.route_to(actor,event['venue']);return True
  if event['venue']=='pool' and index%3!=1 and own.get('wallet',0)>=self.pool_rules['rental_price']:
   if not self.in_swimwear(actor):
    if not self.near_locker(actor):self.s.space.walk_to(actor,self.pool_rules['locker'][0],self.pool_rules['locker'][1]-1);return True
    self.s._do(actor,Action('pool_change',{}));return True
   if not self.water(e['scene'],e['x'],e['y']):
    self.walk_water(actor,index)
    return True
   if not visit.get('swam'):
    result=self.s._do(actor,Action('pool_swim',{}))
    if result.accepted:self.emit('attended',actor,{**visit,'swam':True},[actor])
    return True
  obj=self.s.map_spec['maps'][event['venue']]['objects'][0]
  if abs(e['x']-obj['x'])+abs(e['y']-obj['y'])>5:self.s._desk_walk(actor);return True
  npc=next((n for n,p in self.npcs.items() if p['venue']==event['venue'] and self.s.space.entities[n]['scene']==event['venue']),None)
  if npc and not self.s.space.near(actor,npc):self.s._approach(actor,npc);return True
  if npc:
   key=event['id']+':'+actor+':'+npc
   if key not in self.engine._state['city']['greetings']:
    result=self.s._do(npc,Action('say',{'target':actor,'text':self.npcs[npc]['line']}))
    if result.accepted:self.emit('greeted',npc,{'key':key},[actor,npc])
  return True
 def walk_water(self,actor,index):
  x1,y1,x2,y2=self.pool_rules['water'];points=[(x,y) for y in range(y1,y2+1) for x in range(x1,x2+1)];points=points[index%len(points):]+points[:index%len(points)]
  return any(self.s.space.walk_to(actor,*p) for p in points if self.s.space.passable('pool',*p) and not self.s.space.occupied('pool',*p,actor))
 def pool_native(self,actor,index):
  own=self.engine._state['actors'][actor];e=self.s.space.entities[actor];plan=own.get('life',{}).get('plan')
  if e['scene']!='pool' or not plan or plan.get('kind')!='use' or plan.get('target')!='pool' or own['busy_until']>self.engine.tick or e['path'] or e['destination']:return False
  if not self.in_swimwear(actor):
   if not self.near_locker(actor):self.s.space.walk_to(actor,self.pool_rules['locker'][0],self.pool_rules['locker'][1]-1);return True
   result=self.s._do(actor,Action('pool_change',{}))
   if not result.accepted:self.s.economy.plan(actor,None,self.engine.tick+20)
   return True
  if not self.water(e['scene'],e['x'],e['y']):
   self.walk_water(actor,index);return True
  result=self.s._do(actor,Action('pool_swim',{}))
  self.s.economy.plan(actor,None,self.engine.tick+16 if result.accepted else self.engine.tick+20);return True
 def context(self,actor):
  own=self.engine._state['actors'][actor]
  return {'public_events':[{k:r[k] for k in ('id','title','venue','start','end','description')} for r in self.schedule()[:6]],'nearby_scripted_npcs':[{'id':n,'name':self.npcs[n]['name'],'type':'固定日程／台詞 NPC'} for n in NPCS if self.s.space.near(actor,n)],'rule':'公告是公共活動資訊，未到場不能宣稱已參加；一般 NPC 沒有語言模型，請只寫你自己的台詞。'}
 def browse(self):
  e=self.s.space.entities['player'];rows=self.schedule()
  return {'calendar':rows[:8],'active':self.active(),'npcs':[{'id':n,'name':p['name'],'age':p['age'],'gender':p['gender'],'venue':p['venue'],'type':'scripted'} for n,p in self.npcs.items()],
   'policy':copy.deepcopy(self.engine._state['city']['policy']),'pool':{**self.pool_rules,'here':e['scene']=='pool','near_locker':self.near_locker('player'),'swimwear':self.in_swimwear('player'),'in_water':self.water(e['scene'],e['x'],e['y']),'rental':12},
   'observed':[v for v in self.engine.view('player',100)['memories'] if v['kind'] in {'city_event_opened','city_swimwear'}][-8:]}
 def water(self,scene,x,y):
  x1,y1,x2,y2=self.pool_rules['water'];return scene=='pool' and x1<=x<=x2 and y1<=y<=y2
 def in_swimwear(self,actor):return self.s.wardrobe.appearance(actor)['id'] in {'swim-onepiece','swim-trunks'} if self.s.wardrobe else False
 def may_walk(self,actor,scene,x,y):return not self.water(scene,x,y) or self.in_swimwear(actor)
 def near_locker(self,actor):
  e=self.s.space.entities[actor]
  return e['scene']=='pool' and abs(e['x']-self.pool_rules['locker'][0])+abs(e['y']-self.pool_rules['locker'][1])<=2
 def change_swimwear(self,actor):
  own=self.engine._state['actors'][actor]
  if own['busy_until']>self.engine.tick:raise ValueError('先完成手邊活動')
  if not self.near_locker(actor):raise ValueError('請先走到泳池更衣櫃旁')
  if self.in_swimwear(actor):raise ValueError('已經穿著泳裝')
  if own.get('wallet',500)<self.pool_rules['rental_price']:raise ValueError('租借泳裝需要 '+str(self.pool_rules['rental_price'])+' 代幣')
  male=own.get('gender')=='male';ident='swim-trunks' if male else 'swim-onepiece'
  item={'id':ident,'title':'運動泳褲與泳衣上衣' if male else '運動連身泳裝','style':'sport','sfw':True,
   'prompt':'opaque navy athletic swim trunks, opaque athletic swim shirt' if male else 'opaque navy athletic one-piece swimsuit, high neckline, closed back, nonsexual public swimming',
   'negative_prompt':'nudity, transparent fabric, lingerie, erotic pose, child, teen','palette':{'top':'#416383','bottom':'#26466d'},'shape':'swim','source':{'site':'本作泳池租借'},'lora':{'status':'user_binding','file':None}}
  self.emit('swimwear',actor,{'item':item,'price':self.pool_rules['rental_price']},[actor],True)
 def swim(self,actor):
  if not self.in_swimwear(actor):raise ValueError('必須先在更衣區換泳裝才能下水')
  e=self.s.space.entities[actor]
  if not self.water(e['scene'],e['x'],e['y']):raise ValueError('請先走到泳池水域')
  own=self.engine._state['actors'][actor]
  if own['busy_until']>self.engine.tick:raise ValueError('正在游泳或進行其他活動')
  if self.engine._conflict(actor,self.engine.tick,self.engine.tick+self.pool_rules['swim_minutes']):raise ValueError('這個時段已有其他安排')
  self.engine._emit('venue_started',actor,{'venue':'pool','item':'pool-swim','title':'游泳'+str(self.pool_rules['swim_minutes'])+'分鐘','price':0,'minutes':self.pool_rules['swim_minutes'],'ends_at':self.engine.tick+self.pool_rules['swim_minutes'],'mode':'游泳','part':0,'knowledge':'我在泳池穿著運動泳裝游了'+str(self.pool_rules['swim_minutes'])+'分鐘。','scope':'實際完成游泳','source':'遊戲內泳池','progress_key':'pool-swim'},[actor])
 def perform_pool(self,actor,action):
  try:
   if action.kind=='pool_change':self.change_swimwear(actor)
   else:self.swim(actor)
  except ValueError:raise Rejected('pool_requirements')
 def npc_reply(self,npc,target):
  if npc not in NPCS or not self.s.space.near(npc,target):return
  self.s._do(npc,Action('say',{'target':target,'text':self.npcs[npc]['line']}))
 def public_say(self,speaker,target,text,provider):
  if not isinstance(text,str) or not text.strip() or len(text)>2000 or not self.s.space.near(speaker,target):return False
  audience=self.engine._at(self.engine._state['actors'][speaker]['location'],speaker)
  if target not in audience:audience.append(target)
  self.emit('spoken',speaker,{'text':text.strip(),'target':target,'provider':provider},audience,True);self.engine._set_activity(speaker,'talking',self.engine.tick+1)
  return True
 def policy(self,data):
  if set(data)!={'auto_ai','interval','daily_limit'} or type(data['auto_ai']) is not bool or type(data['interval']) is not int or not 30<=data['interval']<=240 or type(data['daily_limit']) is not int or not 1<=data['daily_limit']<=4:raise ValueError('無效自主交流設定')
  self.emit('policy',None,data);return self.browse()
