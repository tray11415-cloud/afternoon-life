"""Local needs, timed paid jobs, home production and real actor-to-actor trade.

All writes run inside Engine's command/clock transaction and enter its journal.
No model calls, global agent prompt or fabricated customers.
"""
from __future__ import annotations
import copy
from .model import Action, Rejected

EMPLOYERS={
 'library':'整理圖書與借閱桌','cafe':'備餐與清理吧台','zoo':'清潔步道與補充解說卡',
 'gallery':'協助展場導覽','cinema':'整理座位與場次','restaurant':'備料與整理餐桌',
 'park':'照顧花圃與清理步道','market':'整理攤位與協助收攤','boutique':'整理衣架與協助選購','pool':'整理泳池休息區與用品'}
SHIFT_MINUTES=20; WAGE=48; MAX_SHIFTS=2
KINDS={'shift','craft','offer','buy','buy_supply','consume','withdraw'}
NEEDS=('hunger','thirst','fatigue','curiosity')
SUPPLIES={
 'water':dict(title='一瓶飲用水',price=6,quantity=1,effects={'thirst':45},mode='喝掉'),
 'snack':dict(title='市集飯糰',price=8,quantity=1,effects={'hunger':35},mode='吃掉'),
 'materials':dict(title='創作材料包',price=12,quantity=3,effects={},mode='製作材料')}
RECIPE_NAMES=['手作小筆記本','雨澄調配的茶包','旋律小冊','手烤燕麥餅乾','旅行明信片',
              '手縫擦拭布','攝影明信片','練習心得小冊','乾燥花香包','詩句小卡','手繪明信片']
RECIPES={}
for i,name in enumerate(RECIPE_NAMES):
    owner=f'member-{i+1:02d}' if i<10 else 'player'
    effects={'curiosity':38,'fatigue':12}
    if i==1:effects={'thirst':40,'fatigue':10}
    if i==3:effects={'hunger':40}
    if i==8:effects={'fatigue':35}
    RECIPES[owner]={'id':'made-'+owner,'title':name,'price':24+(i%3)*2,'quantity':2,
                   'minutes':12,'effects':effects,'mode':'使用一份'}
PRODUCTS={r['id']:r for r in RECIPES.values()}

def day(tick):return (tick+840)//1440

def apply_economy(state,event):
    """Replay exact outcomes; no clock inference or runtime service on load."""
    data=event['data'];actor_id=event['actor'];kind=event['kind']
    if kind=='economy_initialized':
        state['economy']={'version':1,'listings':{},'wages_paid':0,'trade_volume':0}
        for owner,life in data['actors'].items():
            state['actors'][owner].setdefault('wallet',500)
            state['actors'][owner]['life']=copy.deepcopy(life)
        return
    actor=state['actors'][actor_id];life=actor['life'];economy=state['economy']
    if kind=='economy_needs':life['needs']=copy.deepcopy(data['needs'])
    elif kind=='economy_plan':life['plan']=copy.deepcopy(data['plan']);life['next_plan']=data['next_plan']
    elif kind=='economy_job_started':
        life['job']=copy.deepcopy(data);actor.update(activity=data['activity'],busy_until=data['ends_at'],activity_ref=event['id'])
        if data['kind']=='craft':life['inventory']['materials']-=1
        else:
            key=str(data['day']);life['shifts'][key]=life['shifts'].get(key,0)+1
    elif kind=='economy_job_completed':
        life['job']=None;actor.update(activity='idle',busy_until=event['tick'],activity_ref=None)
        if data['kind']=='shift':
            actor['wallet']+=data['wage'];life['income']['wages']+=data['wage'];economy['wages_paid']+=data['wage']
        else:
            item=data['item'];life['inventory'][item]=life['inventory'].get(item,0)+data['quantity']
            life['crafted'][str(data['day'])]=life['crafted'].get(str(data['day']),0)+1
    elif kind=='economy_offer':
        life['inventory'][data['item']]-=data['quantity'];economy['listings'][data['id']]=copy.deepcopy(data)
    elif kind=='economy_withdraw':
        listing=economy['listings'].pop(data['listing']);item=listing['item']
        life['inventory'][item]=life['inventory'].get(item,0)+listing['quantity']
    elif kind=='economy_bought':
        listing=economy['listings'][data['listing']];listing['quantity']-=1
        if listing['quantity']==0:del economy['listings'][data['listing']]
        actor['wallet']-=data['price'];life['inventory'][data['item']]=life['inventory'].get(data['item'],0)+1
        seller=state['actors'][data['seller']];seller['wallet']+=data['price'];seller['life']['income']['sales']+=data['price']
        economy['trade_volume']+=data['price'];life['purchases']+=1
    elif kind=='economy_supply':
        actor['wallet']-=data['price'];item=data['item'];life['inventory'][item]=life['inventory'].get(item,0)+data['quantity']
        life['purchases']+=1
    elif kind=='economy_consumed':
        life['inventory'][data['item']]-=1;life['consumed']+=1;life['needs']=copy.deepcopy(data['needs'])
    elif kind=='economy_observed':pass
    else:raise ValueError('unknown economy event')

class Economy:
    def rule(self,key,default):return self.session.components.get('rules:economy')[key] if getattr(self.session,'components',None) else default
    def __init__(self,session):self.session=session;self.bind()
    def bind(self):
        engine=self.session.engine
        if 'economy' not in engine._state:
            actors={}
            for i,(owner,actor) in enumerate(engine._state['actors'].items()):
                actors[owner]={'needs':{'hunger':20+(i%3)*6,'thirst':25,'fatigue':18,'curiosity':45+(i%4)*5},
                    'inventory':{'materials':3},'income':{'wages':0,'sales':0},'shifts':{},'crafted':{},
                    'job':None,'plan':None,'next_plan':engine.tick,'purchases':0,'consumed':0}
            engine._emit('economy_initialized',None,{'actors':actors},[],remember=False)
        engine.economy_handler=self.perform;engine.economy_clock=self.clock;engine.venue_completed=self.venue_finished

    @property
    def engine(self):return self.session.engine
    def own(self,actor):return self.engine.view(actor,memory_limit=1)['self']
    def emit(self,kind,actor,data,audience=None,remember=True):
        self.engine._emit('economy_'+kind,actor,data,[actor] if audience is None else audience,remember=remember)
    def needs_after(self,life,effects):
        return {k:max(0,min(100,life['needs'][k]-effects.get(k,0))) for k in NEEDS}
    def product(self,item):
        if item in {r['id']:r for r in self.rule('recipes',RECIPES).values()}:return {r['id']:r for r in self.rule('recipes',RECIPES).values()}[item]
        if item in self.rule('supplies',SUPPLIES):return self.rule('supplies',SUPPLIES)[item]
        for venue in ('cafe','restaurant'):
            row=next((r for r in self.session.facilities.items(venue) if r['id']==item),None)
            if row:
                effects={'thirst':40,'fatigue':10} if item.startswith('drinks-') else {'hunger':38}
                return {'title':row['title'],'price':row['price'],'quantity':1,'effects':effects,'mode':'用掉一份'}
        return None
    def listings(self):return list(self.engine._state['economy']['listings'].values())
    def at_market(self,actor):return self.own(actor)['location']=='market' and self.session.facilities.near_desk(actor)
    def at_craft(self,actor):
        e=self.session.space.entities[actor]
        index=int(actor[-2:]) if actor!='player' else None
        if e['scene'].startswith('room-') and (actor=='player' or e['scene']==f'room-{index:02d}'):
            desk=next(o for o in self.session.map_spec['maps'][e['scene']]['objects'] if o['id']=='desk')
            return abs(e['x']-desk['x'])+abs(e['y']-desk['y'])<=3 and self.session.space.line_clear(e['scene'],(e['x'],e['y']),(desk['x'],desk['y']))
        if actor=='player' and e['scene']=='shared':
            bench=next(o for o in self.session.map_spec['maps']['shared']['objects'] if o['id']=='bench');return abs(e['x']-bench['x'])+abs(e['y']-bench['y'])<=2
        return False
    def observe(self,actor,title):
        self.emit('observed',actor,{'title':title,'venue':self.own(actor)['location']},self.engine._at(self.own(actor)['location'],actor))
    def perform(self,actor,action):
        own=self.own(actor);life=own['life'];p=action.params;kind=action.kind;tick=self.engine.tick
        if kind in {'shift','craft'}:
            today=day(tick)
            if kind=='shift':
                venue=own['location']
                if venue not in self.rule('employers',EMPLOYERS) or not self.session.facilities.near_desk(actor):raise Rejected('job_too_far')
                if life['shifts'].get(str(today),0)>=self.rule('max_shifts',MAX_SHIFTS):raise Rejected('shift_limit')
                data={'kind':'shift','title':self.rule('employers',EMPLOYERS)[venue],'venue':venue,'wage':self.rule('wage',WAGE),'minutes':self.rule('shift_minutes',SHIFT_MINUTES),'activity':'earning','day':today}
            else:
                if not self.at_craft(actor):raise Rejected('craft_too_far')
                if life['inventory'].get('materials',0)<1:raise Rejected('materials_missing')
                recipe=self.rule('recipes',RECIPES)[actor]
                data={'kind':'craft','title':recipe['title'],'item':recipe['id'],'quantity':recipe['quantity'],'minutes':recipe['minutes'],'activity':'crafting','day':today}
            if self.engine._conflict(actor,tick,tick+data['minutes']):raise Rejected('commitment_conflict')
            self.emit('job_started',actor,{**data,'ends_at':tick+data['minutes']});self.observe(actor,('打工：' if kind=='shift' else '創作：')+data['title'])
        elif kind=='offer':
            if not self.at_market(actor):raise Rejected('market_too_far')
            item,qty,price=p['item'],p['quantity'],p['price']
            if not isinstance(item,str) or item not in {r['id']:r for r in self.rule('recipes',RECIPES).values()}:raise Rejected('not_sellable')
            if type(qty) is not int or not 1<=qty<=5 or type(price) is not int or not 1<=price<=100:raise Rejected('invalid_offer')
            if life['inventory'].get(item,0)<qty:raise Rejected('stock_missing')
            listings=[l for l in self.listings() if l['seller']==actor]
            if len(listings)>=2 or any(l['item']==item for l in listings):raise Rejected('stall_full')
            self.emit('offer',actor,{'id':f'offer-{self.engine.revision+1:08d}','seller':actor,'item':item,'title':{r['id']:r for r in self.rule('recipes',RECIPES).values()}[item]['title'],'quantity':qty,'price':price,'created_at':tick})
            self.observe(actor,'擺攤：'+{r['id']:r for r in self.rule('recipes',RECIPES).values()}[item]['title'])
        elif kind in {'buy','withdraw'}:
            if not self.at_market(actor):raise Rejected('market_too_far')
            if not isinstance(p['listing'],str):raise Rejected('unknown_listing')
            listing=next((l for l in self.listings() if l['id']==p['listing']),None)
            if not listing:raise Rejected('unknown_listing')
            if kind=='withdraw':
                if listing['seller']!=actor:raise Rejected('not_seller')
                self.emit('withdraw',actor,{'listing':listing['id'],'title':listing['title']})
            else:
                if listing['seller']==actor:raise Rejected('self_purchase')
                if own['wallet']<listing['price']:raise Rejected('insufficient_funds')
                self.emit('bought',actor,{'listing':listing['id'],'seller':listing['seller'],'item':listing['item'],'title':listing['title'],'price':listing['price'],'quantity':1},[actor,listing['seller']])
                self.observe(actor,'買下：'+listing['title'])
        elif kind=='buy_supply':
            item=p['item'];venue=own['location']
            if not isinstance(item,str):raise Rejected('unknown_item')
            if not self.session.facilities.near_desk(actor):raise Rejected('facility_too_far')
            if venue=='market' and item in self.rule('supplies',SUPPLIES):product=self.rule('supplies',SUPPLIES)[item]
            elif venue in {'cafe','restaurant'} and any(r['id']==item for r in self.session.facilities.items(venue)):product=self.product(item)
            else:raise Rejected('unknown_item')
            if own['wallet']<product['price']:raise Rejected('insufficient_funds')
            self.emit('supply',actor,{'item':item,'title':product['title'],'price':product['price'],'quantity':product['quantity'],'venue':venue})
            self.observe(actor,'買來帶走：'+product['title'])
        elif kind=='consume':
            item=p['item'];product=self.product(item) if isinstance(item,str) else None
            if not product or not product['effects']:raise Rejected('not_consumable')
            if life['inventory'].get(item,0)<1:raise Rejected('stock_missing')
            self.emit('consumed',actor,{'item':item,'title':product['title'],'needs':self.needs_after(life,product['effects'])})
            self.observe(actor,'使用：'+product['title']);self.engine._set_activity(actor,'idle',tick+1)

    def clock(self):
        tick=self.engine.tick
        for actor in list(self.engine._state['actors']):
            own=self.engine._state['actors'][actor];life=own['life'];job=life['job']
            if job and job['ends_at']<=tick:
                self.emit('job_completed',actor,job)
                effects={'fatigue':-8,'curiosity':10} if job['kind']=='craft' else {'fatigue':-15}
                self.emit('needs',actor,{'needs':self.needs_after(life,effects)},remember=False)
            if tick%15==0:
                effects={'hunger':-4,'thirst':-5,'fatigue':-2,'curiosity':-3}
                self.emit('needs',actor,{'needs':self.needs_after(life,effects)},remember=False)

    def venue_finished(self,actor,data):
        venue=data['venue'];life=self.engine._state['actors'][actor]['life']
        if venue in {'cafe','restaurant'}:
            p=self.product(data['item']);effects=p['effects'] if p else {'hunger':35}
        elif venue=='park':effects={'fatigue':35,'curiosity':18}
        elif venue=='pool':effects={'fatigue':12,'curiosity':28}
        elif venue in {'library','gallery','cinema','zoo'}:effects={'curiosity':30,'fatigue':5}
        elif venue in {'market','boutique'}:effects={'curiosity':10}
        else:effects={}
        if effects:self.emit('needs',actor,{'needs':self.needs_after(life,effects)},remember=False)

    def plan(self,actor,value,next_plan=None):
        self.emit('plan',actor,{'plan':value,'next_plan':self.engine.tick if next_plan is None else next_plan},remember=False)
    def native(self,actor,index):
        s=self.session;own=self.own(actor);life=own['life'];e=s.space.entities[actor];today=day(self.engine.tick)
        plan=life['plan'];inventory=life['inventory'];recipe=self.rule('recipes',RECIPES)[actor];needs=life['needs']
        if not plan:
            if life['next_plan']>self.engine.tick:return
            shifts=life['shifts'].get(str(today),0)
            if shifts==0 or (shifts<self.rule('max_shifts',MAX_SHIFTS) and (own['wallet']<80 or (self.engine.tick+840)%1440>=1080)):
                plan={'kind':'shift','target':list(self.rule('employers',EMPLOYERS))[index%len(self.rule('employers',EMPLOYERS))]}
            else:
                consumables=[item for item,count in inventory.items() if count>0 and item!=recipe['id'] and self.product(item) and any(needs[k]>=38 and v>0 for k,v in self.product(item)['effects'].items())]
                if consumables:plan={'kind':'consume','item':consumables[0],'target':own['location']}
                elif inventory.get(recipe['id'],0)>0 and not any(l['seller']==actor and l['item']==recipe['id'] for l in self.listings()):
                    plan={'kind':'offer','item':recipe['id'],'target':'market'}
                elif needs['hunger']>=55:plan={'kind':'use','target':'restaurant'}
                elif needs['thirst']>=55:plan={'kind':'use','target':'cafe'}
                elif life['crafted'].get(str(today),0)==0:
                    plan={'kind':'craft','target':f'room-{index+1:02d}'} if inventory.get('materials',0)>0 else {'kind':'buy_supply','item':'materials','target':'market'}
                elif needs['fatigue']>=48:plan={'kind':'use','target':'park'}
                else:
                    candidates=[l for l in self.listings() if l['seller']!=actor and l['price']<=own['wallet']-40]
                    if candidates and needs['curiosity']>=38:
                        preferred=next((l for l in candidates if any(needs[k]>=35 for k in self.product(l['item'])['effects'])),candidates[index%len(candidates)])
                        plan={'kind':'buy','listing':preferred['id'],'target':'market'}
                    else:
                        places=('park','library','gallery','cinema','zoo','cafe','restaurant','market','boutique','pool')
                        plan={'kind':'use','target':places[(index+self.engine.tick//60)%len(places)]}
            self.plan(actor,plan)
        target=plan['target']
        if own['location']!=target:s.space.route_to(actor,target);return
        kind=plan['kind']
        if kind=='craft':
            if not self.at_craft(actor):
                desk=next(o for o in s.map_spec['maps'][e['scene']]['objects'] if o['id']=='desk')
                for x,y in ((desk['x'],desk['y']+1),(desk['x']+1,desk['y']+1),(desk['x']-1,desk['y']+1),(desk['x'],desk['y']+2)):
                    if s.space.walk_to(actor,x,y):break
                return
            action=Action('craft',{})
        elif kind=='consume':action=Action('consume',{'item':plan['item']})
        else:
            if not s.facilities.near_desk(actor):s._desk_walk(actor);return
            if kind=='shift':action=Action('shift',{})
            elif kind=='offer':action=Action('offer',{'item':recipe['id'],'quantity':min(2,inventory.get(recipe['id'],0)),'price':recipe['price']})
            elif kind=='buy':action=Action('buy',{'listing':plan['listing']})
            elif kind=='buy_supply':action=Action('buy_supply',{'item':plan['item']})
            elif target=='market':
                candidates=[l for l in self.listings() if l['seller']!=actor and l['price']<=own['wallet']-40]
                item='snack' if needs['hunger']>needs['thirst'] else 'water'
                wanted=needs['hunger'] if item=='snack' else needs['thirst']
                if candidates and needs['curiosity']>=38:action=Action('buy',{'listing':candidates[index%len(candidates)]['id']})
                elif wanted>=40 and inventory.get(item,0)<2:action=Action('buy_supply',{'item':item})
                else:action=Action('use',{'item':'market-browse'})
            else:
                rows=s.facilities.items(target)
                if target=='library':rows=[r for r in rows if r.get('text')]
                if target=='cafe':rows=[r for r in rows if r['id'].startswith('drinks-')]
                if target=='boutique':rows=[r for r in rows if r['id']=='boutique-browse']
                if not rows:self.plan(actor,None,self.engine.tick+8);return
                row=rows[0] if target=='cinema' else rows[(index+self.engine.tick//30)%len(rows)]
                action=Action('use',{'item':row['id']})
        result=s._do(actor,action)
        self.plan(actor,None,self.engine.tick+(2 if result.accepted else 8))

    def context(self,actor):
        own=self.own(actor);life=own['life'];recipe=self.rule('recipes',RECIPES)[actor]
        data={'needs':life['needs'],'income':life['income'],'inventory':self.inventory(actor),
              'plan':life['plan'],'job':life['job'],'recipe':recipe,'shift':{'minutes':self.rule('shift_minutes',SHIFT_MINUTES),'wage':self.rule('wage',WAGE),'daily_limit':self.rule('max_shifts',MAX_SHIFTS),'today':life['shifts'].get(str(day(self.engine.tick)),0)},
              'rule':'這是本人欲望、物品與收入；價格是遊戲代幣。要實際工作、製作或成交才取得金錢與物品。不能用台詞宣稱交易完成。'}
        if self.at_market(actor):data['listings']=self.public_listings()[:6]
        return data
    def inventory(self,actor):
        return [{'id':item,'title':p['title'],'quantity':count,'consumable':bool(p['effects']),'price':p.get('price',24),'sellable':item in {r['id']:r for r in self.rule('recipes',RECIPES).values()}} for item,count in self.own(actor)['life']['inventory'].items() if count>0 and (p:=self.product(item))]
    def public_listings(self):
        return [{**l,'seller_name':self.engine._state['actors'][l['seller']]['name']} for l in self.listings()]
    def browse(self,actor):
        own=self.own(actor);life=own['life'];near=self.session.facilities.near_desk(actor);where=own['location']
        recipe=self.rule('recipes',RECIPES)[actor]
        return {'wallet':own['wallet'],'needs':life['needs'],'inventory':self.inventory(actor),'income':life['income'],'job':life['job'],'busy':own['busy_until']>self.engine.tick,
                'can_craft':self.at_craft(actor),'recipe':recipe,'shift':{'available':where in self.rule('employers',EMPLOYERS) and near,'minutes':self.rule('shift_minutes',SHIFT_MINUTES),'wage':self.rule('wage',WAGE),'today':life['shifts'].get(str(day(self.engine.tick)),0),'limit':self.rule('max_shifts',MAX_SHIFTS)},
                'market':{'near':where=='market' and near,'listings':self.public_listings()} if where=='market' else None,
                'supplies':[{'id':k,**v} for k,v in self.rule('supplies',SUPPLIES).items()] if where=='market' else []}
