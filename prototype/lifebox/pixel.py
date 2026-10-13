"""Playable physical world over the existing private, event-sourced agent core."""
from __future__ import annotations
import json, os, secrets, sqlite3, tempfile, time
from pathlib import Path
from .engine import Engine
from .model import Action, Outcome, canonical, digest
from .play import PlaySession, PEOPLE, REASONS, play_world
from .spatial import SpatialWorld
from .memory import VectorMemory, OllamaEmbedding
from .venues import Facilities, VENUES
from .economy import Economy, KINDS
from .wardrobe import Wardrobe
from .xai import AIError, DIALOGUE_TRIGGERS, ERRORS
from .media import CGPrompt, StableDiffusionRenderer, RenderQueue, MediaError
from .neighborhood import NPCS

def atomic_json(path,payload):
    data=canonical({'payload':payload,'checksum':digest(payload)}).encode()
    if len(data)>32*1024*1024: raise ValueError('save too large')
    fd,temporary=tempfile.mkstemp(prefix=path.name+'.',suffix='.tmp',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as f: f.write(data); f.flush(); os.fsync(f.fileno())
        os.replace(temporary,path)
    finally:
        if os.path.exists(temporary): os.unlink(temporary)

class PixelSession(PlaySession):
    def __init__(self,root,backend,clock=time.monotonic):
        self.components=None;self.space=None; self.facilities=None; self.economy=None; self.wardrobe=None; self.social=None;self.neighborhood=None; self.clock=clock
        super().__init__(root,backend)
        source=Path(__file__).resolve().parents[1]/'web/assets/maps.json'
        self.map_spec=json.loads(source.read_text(encoding='utf-8'))
        registry=self.root/'components/registry.json'
        if registry.exists():
            overrides=json.loads(registry.read_text(encoding='utf-8'))['overrides']
            for k,v in overrides.items():
                if k.startswith('map:'):self.map_spec['maps'][k[4:]]=v
            for k,v in overrides.items():
                if k.startswith('object:'):
                    _,scene,ident=k.split(':',2);self.map_spec['maps'][scene]['objects']=[v if o['id']==ident else o for o in self.map_spec['maps'][scene]['objects']]
        self.auto_path=self.root/'pixel-autosave.json'; self.manual_path=self.root/'pixel-save.json'
        self.last_motion=clock(); self.last_minute=clock(); self.last_step=0
        self.memory=VectorMemory(self.root/'vector-memory.sqlite3',OllamaEmbedding(os.environ.get('LIFEBOX_EMBED_URL','http://127.0.0.1:11434'),os.environ['LIFEBOX_EMBED_MODEL']) if os.environ.get('LIFEBOX_EMBED_MODEL') else None)
        if self.auto_path.exists(): self._load_pixel(self.auto_path)
        else: self.space=SpatialWorld(self.map_spec['maps'],self.engine)
        self.facilities=Facilities(self)
        self.economy=Economy(self)
        self.wardrobe=Wardrobe(self)
        from .social import GroupActivities
        from .characters import CharacterSetup
        self.social=GroupActivities(self)
        self.character_setup=CharacterSetup(self.root)
        from .preferences import Preferences
        self.preferences=Preferences(self.root)
        self.memory.sync(self.engine)
        sd=os.environ.get('LIFEBOX_SD_URL')
        self.cg_root=self.root/'cg-cache'; self.cg_jobs=[]
        self.renderer=RenderQueue(StableDiffusionRenderer(sd,self.cg_root),workers=1,capacity=4) if sd else None
        from .character_art import CharacterStudio
        self.studio=CharacterStudio(self.root/'character-studio')
        from .speech import SpeechStudio
        self.speech=SpeechStudio(self.root/'speech')
        from .neighborhood import Neighborhood
        self.neighborhood=Neighborhood(self)
        from .art_assets import ArtAssets
        self.art_assets=ArtAssets(self.root/'replaceable-art')
        from .components import Components
        self.components=Components(self)
        from .looks import LookStudio
        self.look_studio=LookStudio(self)
        from .art_atelier import ArtAtelier
        self.art_atelier=ArtAtelier(self)
        self._save()

    def _load_pixel(self,path):
        raw=path.read_bytes()
        if len(raw)>32*1024*1024: raise ValueError('save too large')
        envelope=json.loads(raw); payload=envelope['payload']
        if set(envelope)!={'payload','checksum'} or envelope['checksum']!=digest(payload) or set(payload)!={'version','world','space'} or payload['version']!=1:
            raise ValueError('invalid pixel save')
        engine=Engine.replay(payload['world']);snapshot=payload['space']
        if (self.root/'components/registry.json').exists():
            snapshot=json.loads(json.dumps(snapshot))
            for e in snapshot['entities'].values():e.update(path=[],destination=None,walking=False)
        space=SpatialWorld(self.map_spec['maps'],engine,snapshot)
        self.engine,self.space=engine,space
        if self.facilities: self.facilities.bind()
        if self.economy:self.economy.bind()
        if self.wardrobe:self.wardrobe.bind()
        if self.social:self.social.bind()
        if self.neighborhood:self.neighborhood.bind()
        if self.components:self.components.bind(clear=False)
        self.last_motion=self.clock(); self.last_minute=self.clock()

    def _save(self):
        if self.space is None: return
        atomic_json(self.auto_path,{'version':1,'world':self.engine.journal(),'space':self.space.snapshot()})

    def _do(self,actor,action):
        if action.kind=='visit' and self.facilities:
            if set(action.params)!={'location'} or action.params['location'] not in VENUES: return Outcome(False,'invalid_location')
            if self.engine.view(actor)['self']['busy_until']>self.engine.tick: return Outcome(False,'actor_busy')
            self.space.flags.setdefault('outings',{})[actor]={'venue':action.params['location'],'due':self.engine.tick}
            return Outcome(self.space.route_to(actor,action.params['location']),'ok')
        if action.kind=='move' and self.space is not None:
            own=self.engine.view(actor)['self']
            if own['busy_until']>self.engine.tick: return Outcome(False,'actor_busy')
            return Outcome(self.space.travel(actor,action.params.get('location')),'ok')
        return super()._do(actor,action)

    def _native_step(self,exempt=()):
        tick=self.engine.tick
        self._player_trip()
        if self.neighborhood:self.neighborhood.step_npcs()
        for index,actor in enumerate(self.engine.agent_ids()):
            if self.social and self.social.native(actor,index):continue
            if self.neighborhood and self.neighborhood.pool_native(actor,index):continue
            if self.neighborhood and self.neighborhood.native(actor,index):continue
            if actor in exempt: continue
            view=self.engine.view(actor,memory_limit=2); own=view['self']; e=self.space.entities[actor]
            if own['busy_until']>tick or e['path'] or e['destination'] or self.space.flags.get('journeys',{}).get(actor): continue
            plans=[inv for inv in view['invitations'] if inv['status']=='accepted']
            if plans:
                plan=min(plans,key=lambda inv:inv['start'])
                if own['location']!=plan['location']:
                    self.space.route_to(actor,plan['location'])
                else:
                    other=plan['sender'] if plan['recipient']==actor else plan['recipient']
                    if self.space.entities[other]['scene']==own['location'] and not self.space.near(actor,other):
                        self._approach(actor,other)
                continue
            home=f'room-{index+1:02d}'
            wants_work=own['goal']['progress']<own['goal']['target'] and (tick+index)%16>=7
            if wants_work:
                if own['location']!=home: self.space.route_to(actor,home)
                elif (e['x'],e['y'])!=self.work_spot(home): self.space.walk_to(actor,*self.work_spot(home))
                else: super()._do(actor,Action('work',{'minutes':min(3,own['goal']['target']-own['goal']['progress'])}))
            elif own['goal']['progress']>=own['goal']['target'] and self.economy:
                if not self.wardrobe or not self.wardrobe.native(actor,index):self.economy.native(actor,index)
            elif own['goal']['progress']>=own['goal']['target'] and self.facilities:
                outings=self.space.flags.setdefault('outings',{})
                plan=outings.setdefault(actor,{'venue':VENUES[index%6],'due':tick})
                if plan['due']>tick: continue
                if own['location']!=plan['venue']: self.space.route_to(actor,plan['venue']);continue
                if not self.facilities.near_desk(actor): self._desk_walk(actor); continue
                rows=self.facilities.items(plan['venue'])
                if plan['venue']=='library': rows=[r for r in rows if r.get('text')]
                if rows:
                    row=rows[0] if plan['venue']=='cinema' else rows[(index+tick//30)%len(rows)]
                    result=super()._do(actor,Action('use',{'item':row['id']}))
                    if result.accepted:
                        plan['due']=tick+row['minutes']+8;plan['venue']=VENUES[(VENUES.index(plan['venue'])+1)%6]
                    else: plan['due']=tick+8
            elif own['location']!='shared': self.space.route_to(actor,'shared')
            else:
                # Per-character deterministic leisure destinations; no fake AI speech.
                spots=[(16,13),(18,13),(16,15),(20,16),(13,16),(22,15),(17,11),(19,11),(13,13),(23,17)]
                self.space.walk_to(actor,*spots[index])
        self.engine.advance()

    def work_spot(self,scene):
        obj=next((o for o in self.map_spec['maps'][scene]['objects'] if o['id']=='desk'),None)
        if not obj:return (7,7)
        desired=(obj['x']+1,obj['y']+2)
        if self.space.passable(scene,*desired):return desired
        return next(((obj['x']+dx,obj['y']+dy) for dx,dy in ((0,1),(1,0),(-1,0),(0,-1)) if self.space.passable(scene,obj['x']+dx,obj['y']+dy)),desired)

    def _desk_walk(self,actor):
        e=self.space.entities[actor];obj=self.facilities.desk_object(e['scene'])
        for dx,dy in [(0,1),(-1,0),(1,0),(0,-1)]:
            if self.space.walk_to(actor,obj['x']+dx,obj['y']+dy): return True
        for dx,dy in [(1,1),(-1,1),(1,-1),(-1,-1),(0,2),(-2,0),(2,0),(0,-2)]:
            if self.space.walk_to(actor,obj['x']+dx,obj['y']+dy):return True
        return False

    def _player_trip(self):
        group_id=self.space.flags.get("group_trip")
        if group_id and self.social:
            group=self.social.groups().get(group_id);e=self.space.entities["player"]
            if not group or group["status"] not in {"planned","active"}:self.space.flags.pop("group_trip",None)
            elif e["scene"]==group["venue"] and not e["path"]:
                spot=group["spots"]["player"]
                if (e["x"],e["y"])==(spot["x"],spot["y"]):self.space.flags.pop("group_trip",None)
                else:self.space.walk_to("player",spot["x"],spot["y"])
        target=self.space.flags.get('player_trip')
        if target and self.space.entities['player']['scene']==target and not self.space.entities['player']['path']:
            if not self.facilities.near_desk('player'): self._desk_walk('player')
            else: self.space.flags.pop('player_trip',None)

    def _approach(self,actor,target):
        p=self.space.entities[target]
        candidates=[(p['x']+dx,p['y']+dy) for dx,dy in [(0,1),(-1,0),(1,0),(0,-1)]]
        for point in candidates:
            if self.space.walk_to(actor,*point): return True
        return False

    def _ai(self,actor,trigger):
        own=self.engine.view(actor,memory_limit=6)
        if own['self']['busy_until']>self.engine.tick:
            self.notice=PEOPLE[actor]['name']+'正在忙自己的事。'; return None
        last=next((e['data'].get('text','') for e in reversed(own['memories']) if e['kind']=='message_spoken'),'')
        view=self.memory.context(self.engine,actor,last+' '+own['self']['goal']['title'])
        view['response_language']=self.preferences.config['language']
        if self.components:view['interactive_objects']=self.components.object_context(actor)
        if self.social:view['social']=self.social.context(actor)
        if self.neighborhood:view['town']=self.neighborhood.context(actor)
        e=self.space.entities[actor]
        view['self']['position']={'x':e['x'],'y':e['y']}
        if self.facilities:
            view['facilities']=self.facilities.context(actor);view['actions']+=['visit']
        if self.economy:view['economy']=self.economy.context(actor)
        if self.wardrobe:
            view['self'].pop('wardrobe',None)
            view['wardrobe']=self.wardrobe.context(actor)
            for person in view['nearby']:person['outfit']=self.wardrobe.appearance(person['id'])['title']
        self.space.entities[actor]['path']=[]; self.space.entities[actor]['destination']=None
        try:
            action=self.backend.decide(view,self._persona(actor),trigger)
            if action.kind=='say' and trigger not in DIALOGUE_TRIGGERS and getattr(self.backend,'dialogue_model',None):
                action=self.backend.express(view,self._persona(actor),action)
            result=self._do(actor,action)
            if result.accepted:
                try: self.memory.presented(self.engine,actor,view)
                except (OSError, sqlite3.Error): self.memory.error='local_memory_write_unavailable'
            if not result.accepted: self.notice='這次行動無法執行：'+REASONS.get(result.reason,'距離、地點或時間不符。')
            elif action.kind!='say':
                self.notice=PEOPLE[actor]['name']+{'work':'選擇先處理自己的事。','move':'準備離開這裡。','respond':'回應了邀約。','invite':'提出了邀約。'}.get(action.kind,'暫時沒有接話。')
            return action if result.accepted else None
        except AIError as exc:
            self.error={'code':str(exc),'message':ERRORS.get(str(exc),'AI 暫時無法回應。')}; return None

    def _persona(self,actor):
        from .characters import persona
        return persona(self.engine,actor)

    def _town_reply(self,speaker,target):
        if speaker not in self.engine.agent_ids() or not self.space.near(speaker,target):return False
        if self.engine._state['actors'][speaker]['busy_until']>self.engine.tick:return False
        view=self.memory.context(self.engine,speaker,'公共場所聊天')
        view['response_language']=self.preferences.config['language']
        view['town']=self.neighborhood.context(speaker)
        view['conversation_target']={'id':target,'name':self.engine._state['actors'][target]['name'],'public':True,'rule':'你在公共場所與這個對象交流，附近的人可以聽到。只生成你自己的一句話，用 say 指向這個 id；也可以 wait 表示不想聊。不要代替別人發言。'}
        view['wardrobe']=self.wardrobe.context(speaker)
        try:
            action=self.backend.decide(view,self._persona(speaker),'另一位成員向你說話')
            if action.kind!='say' or action.params.get('target') not in (target,None):return False
            result=self.neighborhood.public_say(speaker,target,action.params.get('text'),'grok-4.3')
            if result:self.memory.presented(self.engine,speaker,view)
            return result
        except AIError as exc:self.error={'code':str(exc),'message':ERRORS.get(str(exc),'AI 暫時無法回應。')};return False

    def _town_pair(self,speaker,target):
        if speaker not in PEOPLE or target not in self.engine._state['actors'] or speaker==target or target=='player':raise ValueError('請選擇 AI 成員與另一位在場的人')
        if not self.space.near('player',speaker) or not self.space.near(speaker,target):raise ValueError('請先走到兩人附近，兩人也需要彼此靠近')
        if any(self.engine._state['actors'][a]['busy_until']>self.engine.tick for a in (speaker,target)):raise ValueError('兩人正忙，稍後再試')
        if not self._town_reply(speaker,target):self.notice='她這次沒有開口。';return
        if target in NPCS:self.neighborhood.public_say(target,speaker,self.neighborhood.npcs[target]['line'],'scripted')
        elif target in PEOPLE:self._town_reply(target,speaker)
        self.notice='在場交流已留下各自的記憶；一般 NPC 使用固定台詞。'

    def _auto_town_pair(self):
        city=self.engine._state['city'];p=city['policy'];today=self.neighborhood.day()
        if not p['auto_ai'] or self.engine.tick<city.get('next_ai',0) or city['ai_calls'].get(str(today),0)>=p['daily_limit']:return
        pairs=[(a,b) for a in self.engine.agent_ids() for b in self.engine._state['actors'] if b!=a and b!='player' and self.space.near(a,b) and all(self.engine._state['actors'][x]['busy_until']<=self.engine.tick for x in (a,b))]
        if not pairs:return
        speaker,target=pairs[self.engine.tick%len(pairs)]
        self.neighborhood.emit('ai_budget',None,{'day':today,'calls':city['ai_calls'].get(str(today),0)+1,'next':self.engine.tick+p['interval']})
        if self._town_reply(speaker,target):
            if target in NPCS:self.neighborhood.public_say(target,speaker,self.neighborhood.npcs[target]['line'],'scripted')
            # A scheduled turn calls one speaker. The other keeps its own next turn.

    def _group_ai(self,group_id,speaker):
        group=self.social._get('player',group_id)
        if not self.social.browse('player')['groups'] or speaker not in group['attendees'] or speaker=='player' or not self.social.arrived(speaker,group):return
        if speaker in NPCS:
            self._do(speaker,Action('group_say',{'group':group_id,'text':self.neighborhood.npcs[speaker]['line']}));return
        own=self.engine.view(speaker,memory_limit=6)
        view=self.memory.context(self.engine,speaker,'共同活動 '+group['title'])
        view['response_language']=self.preferences.config['language']
        view['social']=self.social.context(speaker)
        view['group_conversation']={'id':group_id,'members':[{'id':a,'name':self.engine._state['actors'][a]['name']} for a in group['attendees']],
            'recent':next(g for g in self.social.browse(speaker)['groups'] if g['id']==group_id)['messages'][-8:],
            'rule':'只生成你自己的一次回應，使用 group_say 或 say；不要代替其他人發言。'}
        view['self'].pop('wardrobe',None)
        from .model import canonical
        while len(canonical(view).encode())>12500 and view['memories']:view['memories'].pop(0)
        while len(canonical(view).encode())>12500 and len(view['group_conversation']['recent'])>1:view['group_conversation']['recent'].pop(0)
        try:
            action=self.backend.decide(view,self._persona(speaker),'共同活動交談')
            if action.kind=='say':action=Action('group_say',{'group':group_id,'text':action.params.get('text','')})
            if action.kind not in {'group_say','group_leave'} or action.params.get('group')!=group_id:self.notice='她沒有接話。';return
            outcome=self._do(speaker,action)
            if not outcome.accepted:self.notice='她現在無法參與這次交談。'
        except AIError as exc:self.error={'code':str(exc),'message':ERRORS.get(str(exc),'AI 暫時無法回應。')}

    def screen(self):
        result=super().screen()
        if self.space is None: return result
        scene=self.space.entities['player']['scene']; near={p['id'] for p in result['nearby']}
        result['location_name']=self.map_spec['maps'][scene]['name']
        result['location_names']={key:m['name'] for key,m in self.map_spec['maps'].items()}
        result['space']={'scene':scene,'revision':self.space.revision,'entities':self.space.public('player'),
                         'objects':self.map_spec['maps'][scene]['objects'],'watered_today':self.space.flags.get('water_day')==self.engine.tick//1440}
        result['roster']=[{**p,'near':p['id'] in near} for p in result['roster']]
        if self.social:result['social']=self.social.browse('player')
        if self.neighborhood:
            result['town']=self.neighborhood.browse()
            for ident,p in self.neighborhood.npcs.items():
                result['roster'].append({'id':ident,'name':p['name'],'age':p['age'],'gender':p['gender'],'profile':'一般 NPC · 固定日程與台詞','scripted':True,'here':ident in near,'near':ident in near,'activity':'場所服務'})
        if self.components:result['components']=self.components.public()
        result['player']={k:self.engine._state['actors']['player'][k] for k in ('name','age','gender')}
        result['preferences']=self.preferences.state()
        result['start_menu']={'ready':True,'has_progress':self.engine.tick>0 or self.manual_path.exists(),'manual_save':self.manual_path.exists(),'location':result['location_name'],'tick':self.engine.tick}
        result['events']=[e for e in self.engine.view('player',100)['memories'] if e['kind'] in {'message_spoken','city_spoken','actor_moved','work_started','work_completed','invitation_created','invitation_status'}]
        for scene_id in result['location_names']:
            if scene_id.startswith('room-'):
                owner='member-'+scene_id.split('-')[-1]
                if owner in self.engine._state['actors']:result['location_names'][scene_id]=self.engine._state['actors'][owner]['name']+'的家'
        result['location_name']=result['location_names'][scene]
        result['memory']={'provider':self.memory.embedding.name,'status':self.memory.error or 'ready'}
        result['cg']={'selected':self.art_atelier.selected_cg(),'connected':self.renderer is not None,'jobs':self.renderer.visible_jobs('player') if self.renderer else []}
        if hasattr(self,'studio'):
            result['cg']['connected']=result['cg']['connected'] or self.studio.services.get(self.studio.config['url'],{}).get('ready',False)
            with self.studio.lock:
                for j in list(self.studio.jobs.values())[-80:]:
                    if j['kind']=='cg':result['cg']['jobs'].append({'job_id':j['id'],'status':j['status'],'scene':{'character':j['actor'],'scene':j['scene']['scene'],'outfit':j['outfit']['render_key']},'asset_id':j['id'],'url':'/character-art/'+j['files']['cg'] if j['files'].get('cg') else None})
        if self.facilities:
            result['places']=[{'id':k,'name':v['name'],'count':len(self.facilities.items(k))} for k,v in self.facilities.data.items()]
            result['facility']=self.facilities.browse('player')
            own=self.engine.view('player')['self'];result['wallet']=own.get('wallet',500)
            result['outing_events']=[e for e in self.engine.view('player',memory_limit=100)['memories'] if e['kind'] in {'venue_completed','venue_observed'}][-10:]
        if self.economy:result['economy']=self.economy.browse('player')
        if self.wardrobe:
            result['wardrobe']=self.wardrobe.browse('player')
            for entity in result['space']['entities']:
                entity['outfit']=self.wardrobe.appearance(entity['id'])
                if entity['id'] in self.character_setup.profiles:
                    profile=self.character_setup.current(self,entity['id']);entity['art']=self.look_studio.render(entity['id'],profile,entity['outfit'])
                if hasattr(self,'studio'):entity.setdefault('art',{}).update(self.studio.appearance(entity['id'],entity['outfit']))
                if hasattr(self,'art_assets'):
                    active=self.studio.config['active'].get(entity['id']+':'+entity['outfit']['render_key'],{})
                    entity.setdefault('art',{}).update(self.art_assets.appearance(entity['id'],entity['outfit'],active.get('expression',self.studio.config['profiles'].get(entity['id'],{}).get('expression','neutral'))))
                if self.art_atelier.prefers(entity['id'],entity['outfit']):entity.setdefault('art',{}).update(self.studio.appearance(entity['id'],entity['outfit']))
        if hasattr(self,'art_assets'):result['art_backgrounds']=self.art_assets.backgrounds()
        if hasattr(self,'studio') and self.studio.config['auto']:
            self.studio.maybe_auto([(actor,self.wardrobe.appearance(actor),self.art_outfit_prompt(actor)) for actor in self.studio.config['profiles']])
        return result

    def art_outfit_prompt(self,actor):
        # Only actual worn clothing, never another character's private closet.
        from .looks import color_name
        own=self.engine._state['actors'][actor];look=own.get('character_profile',{}).get('look')
        if look and look.get('enabled') and own['wardrobe']['wearing']=='original':
            return f"fully clothed, modest {color_name(look['top_color'])} long-sleeved jacket, {color_name(look['bottom_color'])} full-length trousers, everyday shoes"
        return self.wardrobe.render_prompt(actor,'shared','portrait').prompt.split('plain background, ',1)[-1]

    def speech_action(self,body):
        if not isinstance(body,dict) or set(body)!={'operation','params'} or not isinstance(body['params'],dict):raise ValueError('無效語音操作')
        op,p=body['operation'],body['params']
        if op=='configure':return self.speech.configure(p)
        if op=='probe' and not p:return self.speech.probe()
        if op=='voices' and not p:return self.speech.refresh_windows()
        if op=='preview' and set(p)=={'actor'}:
            from .speech import PREVIEW,PREVIEWS
            return self.speech.render(p['actor'],PREVIEWS.get(self.speech.config['language'],PREVIEW),preview=True)
        if op=='speak' and set(p)=={'event'}:
            from .speech import authorized_line
            with self.lock:actor,text=authorized_line(self.engine,p['event'])
            # Audio work happens outside the simulation lock.
            return self.speech.render(actor,text)
        raise ValueError('未知語音操作')

    def art_action(self,body):
        if not isinstance(body,dict) or set(body)!={'operation','params'} or not isinstance(body['params'],dict):raise ValueError('無效生圖操作')
        op,p=body['operation'],body['params']
        if op=='atelier':return self.art_atelier.operation(p)
        if op=='asset_state' and not p:return self.art_assets.state()
        if op=='asset_upload':
            with self.lock:
                result=self.art_assets.upload(p,self)
                if p['kind']=='portrait':
                    from .character_art import atomic
                    outfit=self.wardrobe.appearance(p['target']);scope=p['target']+':'+outfit['render_key'];self.studio.config['active'].setdefault(scope,{})['expression']=p['expression'];atomic(self.studio.config_path,self.studio.config)
                return result
        if op=='asset_remove' and set(p)=={'slot'}:return self.art_assets.remove(p['slot'])
        if op=='portrait_use' and set(p)=={'id'}:
            entry=self.studio.portrait_library.get(p['id'])
            if not entry:raise ValueError('找不到立繪差分')
            actor=entry['actor'];outfit=self.wardrobe.appearance(actor)
            if entry.get('gender') and entry['gender']!=self.engine._state['actors'][actor].get('gender','female'):raise ValueError('這張是舊版不同性別的主角立繪，請改用新的男性立繪或手動替換素材')
            if outfit['render_key']!=entry['outfit']['render_key']:raise ValueError('這張立繪屬於其他穿著，請先穿回同一套')
            if actor not in self.studio.config['profiles']:raise ValueError('請先為角色保存身份設定')
            scope=actor+':'+outfit['render_key'];active=self.studio.config['active'].setdefault(scope,{})
            active.setdefault('portraits',{})[entry['expression']]=entry['file'];active['expression']=entry['expression']
            from .character_art import atomic
            atomic(self.studio.config_path,self.studio.config);return self.studio.state()
        if op=='configure':return self.studio.configure(p)
        if op=='scan' and set(p)<= {'folder'}:return self.studio.discover(p.get('folder'))
        if op=='probe' and not p:return self.studio.probe()
        if op=='start' and not p:return self.studio.launch()
        if op=='start_native' and set(p)=={'installation','url'}:return self.studio.launch(p['installation'],p['url'])
        if op=='native_prepare' and set(p)<= {'document','title','png'}:return self.studio.native_prepare(p)
        if op=='native_save':return self.studio.native_save(p)
        if op=='native_select' and set(p) in ({'kind','id'},{'selections'}):return self.studio.native_select(p)
        if op=='native_read' and set(p)=={'id'}:return self.studio.native_read(p['id'])
        if op=='native_delete' and set(p)=={'id'}:return self.studio.native_delete(p['id'])
        if op=='native_history' and set(p)<= {'id'}:return self.studio.native_history(p.get('id'))
        if op=='native_resource' and set(p)=={'id'}:return self.studio.native_resource(p['id'])
        if op=='open_folder' and set(p)=={'id'}:
            folder=next((f for f in self.studio.folders if f['id']==p['id']),None)
            if not folder:raise ValueError('未知資料夾')
            os.startfile(folder['path']);return self.studio.state()
        if op=='cancel' and set(p)=={'id'}:return self.studio.cancel(p['id'])
        if op=='activate' and set(p)=={'id','expression'}:return self.studio.activate(p['id'],p['expression'])
        if op=='generate' and set(p)=={'actor','kind'}:
            if p['actor'] not in PEOPLE and p['actor']!='player':raise ValueError('未知角色')
            with self.lock:outfit=self.wardrobe.appearance(p['actor']);prompt=self.art_outfit_prompt(p['actor'])
            self.studio.submit(p['actor'],outfit,prompt,p['kind']);return self.studio.state()
        if op=='generate_bound' and not p:
            for actor,profile in self.studio.config['profiles'].items():
                if profile.get('lora'):
                    with self.lock:outfit=self.wardrobe.appearance(actor);prompt=self.art_outfit_prompt(actor)
                    self.studio.submit(actor,outfit,prompt,'both')
            return self.studio.state()
        raise ValueError('未知生圖操作')

    def _pulse(self,focus=None):
        now=self.clock()
        if focus and not self.space.near('player',focus): focus=None
        if now-self.last_motion>=.18:
            self._player_trip()
            self.space.animate(focus=focus); self.last_motion=now
        if now-self.last_minute>=8:
            self._native_step(exempt=(focus,) if focus else ()); self.last_minute=now
            self._auto_town_pair()
        # No catch-up flood after a paused tab or slow API. Clock and AI requests
        # are deliberately independent; heartbeats never make model requests.

    def act(self,body):
        if not isinstance(body,dict) or set(body)!={'command','params'} or not isinstance(body['params'],dict): raise ValueError('invalid command')
        command,params=body['command'],body['params']
        with self.lock:
            if command not in {'pulse','ui_hold'}: self.error,self.notice=None,None
            if command=='ui_hold':
                if params:raise ValueError('無效選單時間操作')
                self.last_motion=self.clock();self.last_minute=self.clock()
            elif command=='pulse':
                if set(params)!={'focus'} or (params['focus'] is not None and params['focus'] not in self.engine._state['actors']): raise ValueError('invalid focus')
                self._pulse(params['focus'])
                # Write only on changes, at most one world checkpoint per native minute.
                if self.engine.revision!=getattr(self,'_saved_revision',None): self._save(); self._saved_revision=self.engine.revision
            elif command in {'pool_change','pool_swim','town_chat','town_policy'}:
                if command=='pool_change':
                    if params:raise ValueError('無效更衣操作')
                    self.neighborhood.change_swimwear('player');self.notice='已換上租借泳裝；現在可以下水，離開泳池會換回原本衣服。'
                elif command=='pool_swim':
                    if params:raise ValueError('無效游泳操作')
                    self.neighborhood.swim('player');self.notice='開始游泳'+str(self.neighborhood.pool_rules['swim_minutes'])+'分鐘，完成後會留下自己的記憶。'
                elif command=='town_chat':
                    if set(params)!={'speaker','target'}:raise ValueError('無效公共交流')
                    self._town_pair(params['speaker'],params['target'])
                else:self.neighborhood.policy(params);self.notice='自主交流設定已保存；啟用後依間隔與每日上限使用 Grok 4.3。'
                self.memory.sync(self.engine);self._save();self.last_motion=self.clock();self.last_minute=self.clock()
            elif command=='talk' and params.get('target') in NPCS:
                if set(params)!={'target','text'} or not self.space.near('player',params['target']):raise ValueError('請先走近一般 NPC')
                result=self._do('player',Action('say',params))
                if result.accepted:self.neighborhood.npc_reply(params['target'],'player')
                self.notice='一般 NPC 回應了你；沒有呼叫聊天模型。' if result.accepted else '先完成手邊活動。'
                self.memory.sync(self.engine);self._save()
            elif command.startswith('group_'):
                if command=='group_go':
                    if set(params)!={'group'}:raise ValueError('invalid group route')
                    group=self.social._get('player',params['group'])
                    if group['status'] not in {'planned','active'} or group['responses']['player']!='accepted' or self.engine.view('player')['self']['busy_until']>self.engine.tick:raise ValueError('目前不能前往這次活動')
                    self.space.flags.pop('player_trip',None);self.space.flags['group_trip']=group['id'];self.space.route_to('player',group['venue']);self._player_trip();self.notice='正走向集合點。'
                elif command in {'group_talk','group_reply'}:
                    expected={'group','speaker','text'} if command=='group_talk' else {'group','speaker'}
                    if set(params)!=expected:raise ValueError('invalid group conversation')
                    group=self.social._get('player',params['group'])
                    if group['status']!='active' or 'player' not in group['attendees'] or not self.social.arrived('player',group):raise ValueError('先到場並開始共同活動，才能交談')
                    if params['speaker'] and (params['speaker'] not in group['attendees'] or params['speaker']=='player'):raise ValueError('請選實際參與的成員')
                    if command=='group_talk':
                        outcome=self._do('player',Action('group_say',{'group':group['id'],'text':params['text']}))
                        if not outcome.accepted:raise ValueError('請輸入有效的活動對話')
                    if params['speaker']:self._group_ai(group['id'],params['speaker'])
                else:
                    from .social import SCHEMAS
                    if command not in SCHEMAS or set(params)!=SCHEMAS[command]:raise ValueError('invalid group command')
                    outcome=self._do('player',Action(command,params))
                    self.notice='共同活動安排已更新。' if outcome.accepted else {'commitment_conflict':'已有安排、正在忙或代幣不足，無法接受。','insufficient_funds':'代幣不足。','group_not_here':'先到集合點並開始活動。','group_invitation_closed':'這次邀約已結束。','group_space_full':'集合點沒有足夠空間。','not_now_showing':'這部電影現在沒有上映。'}.get(outcome.reason,'活動內容、時間或參與資格不合適。')
                self.memory.sync(self.engine);self._save()
            elif command=='restore_cast':
                import re
                if set(params)!={'archive'} or not isinstance(params['archive'],str) or not re.fullmatch(r'before-creation-[0-9a-f]{16}',params['archive']):raise ValueError('無效的原存檔')
                archive=self.root/'archives'/params['archive']/'pixel-autosave.json'
                if not archive.is_file():raise ValueError('找不到原存檔')
                self.character_setup.archive_current(self);self._load_pixel(archive);self.memory.sync(self.engine);self._save()
                self.notice='已恢復原存檔；剛才的進度亦已保留，API 用量不會回退。'
            elif command=='create_cast':
                if params:raise ValueError('invalid creation command')
                archive=self.character_setup.archive_current(self)
                self.engine=Engine(self.character_setup.world());self.space=SpatialWorld(self.map_spec['maps'],self.engine)
                self.character_setup.initialize(self.engine);self.facilities.bind();self.economy.bind();self.wardrobe.bind();self.social.bind()
                self.neighborhood.bind()
                from .characters import PRIVATE_FIELDS
                changes=[]
                for actor,p in self.character_setup.profiles.items():
                    value={f:p[f] for f in ('name','age','gender')};value['character_profile']={f:(p[f] if f!='background' or p['background_enabled'] else '') for f in PRIVATE_FIELDS}
                    changes.append({'target':'actor:'+actor,'value':value})
                proposal=self.components.prepare({'instruction':'依人物模板建立新存檔','changes':changes})
                self.components.apply(proposal['id'])
                self.components.bind(clear=False)
                self.last_motion=self.clock();self.last_minute=self.clock();self.memory.sync(self.engine);self._save()
                self.notice='已依創角模板建立新存檔；原存檔保留於 '+archive+'，API 用量不會重置。'
            elif command in {'visit','use','rest'}:

                if command=='visit':
                    if set(params)!={'location'} or params['location'] not in VENUES: raise ValueError('invalid venue')
                    if self.engine.view('player')['self']['busy_until']>self.engine.tick: self.notice='先完成手邊的活動。'
                    else:
                        self.space.flags['player_trip']=params['location'];self.space.route_to('player',params['location'])
                        self.notice='沿路走到'+self.facilities.data[params['location']]['name']+'。';self._player_trip()
                elif command=='use':
                    if set(params)!={'item'}: raise ValueError('invalid item')
                    result=super()._do('player',Action('use',params))
                    self.notice='活動開始；時間會照常前進。' if result.accepted else {'facility_too_far':'請先走近服務桌。','unknown_item':'目前沒有這個品項。','not_now_showing':'請選目前上映的電影。','text_unavailable':'這本書尚未快取原文，可先開啟官方完整館藏。','insufficient_funds':'遊戲代幣不足。','actor_busy':'先完成手邊的活動。','reading_complete':'這本書的所有片段已讀完。'}.get(result.reason,'時間或安排不合適。')
                else:
                    if params: raise ValueError('invalid rest')
                    for _ in range(10):
                        for _ in range(12): self.space.animate()
                        self._native_step()
                    self.memory.sync(self.engine);self.notice='過了十分鐘。'
                self._save()
            elif command in KINDS|{'buy_clothes','wear'}:
                result=self._do('player',Action(command,params))
                messages={'job_too_far':'走近場所服務桌才能打工。','craft_too_far':'到屋內工作桌或庭院長椅旁創作。','materials_missing':'需要一份創作材料，可去市集購買。','market_too_far':'走近市集服務桌才能交易。','stock_missing':'手上沒有足夠的物品。','shift_limit':'今天已完成或預約兩班，明天再來。','insufficient_funds':'代幣不足。','actor_busy':'先完成手邊的活動。','unknown_listing':'這件商品已售完或收攤。','self_purchase':'這是你的攤位。','stall_full':'同一商品已上架，或攤位已滿。','not_consumable':'這件物品不能直接消耗。','not_seller':'只能收回自己的商品。','not_sellable':'只能出售已擁有的創作品。'}
                self.notice={'shift':'打工開始，完成後領取工資。','craft':'創作開始，完成後作品放入口袋。','offer':'商品已上架；有人買下才有收入。','buy':'成交，商品放入口袋。','buy_supply':'已買好，收入口袋。','consume':'已使用一份，需求已改變。','withdraw':'已收攤，剩餘商品回到口袋。'}.get(command) if result.accepted else messages.get(result.reason,'地點、數量、價格或安排不合適。')
                if command in {'buy_clothes','wear'}:
                    self.notice=({'buy_clothes':'衣服已放入衣櫃；回房間就能換裝。','wear':'已換上衣服，之後的立繪與 CG 使用這套服裝描述。'}[command] if result.accepted else {'shop_too_far':'走近衣間的選購桌才能買衣服。','already_owned':'衣櫃裡已經有這套衣服。','clothes_not_owned':'先買下這套衣服。','change_at_home':'回房間再換裝。','already_wearing':'現在已經穿著這套。','insufficient_funds':'代幣不足。','actor_busy':'先完成手邊的活動。'}.get(result.reason,'目前無法取得這套衣服。'))
                self.memory.sync(self.engine);self._save()
            elif command in {'step','walk','approach','interact'}:
                if command!='interact':
                    self.space.flags.get('journeys',{}).pop('player',None);self.space.flags.pop('player_trip',None)
                player=self.space.entities['player']; player['path']=[]; player['destination']=None
                if command=='step':
                    if set(params)!={'direction'} or params['direction'] not in {'up','down','left','right'}: raise ValueError('invalid step')
                    if self.clock()-self.last_step<.12: return self.screen()
                    self.last_step=self.clock()
                    if not self.space.step('player',params['direction']): self.notice='前面走不過去。'
                elif command=='walk':
                    if set(params)!={'x','y'} or any(type(params[k]) is not int for k in params): raise ValueError('invalid destination')
                    if not self.space.walk_to('player',params['x'],params['y']): self.notice='這裡無法走到。'
                elif command=='approach':
                    if set(params)!={'target'} or params['target'] not in self.engine._state['actors'] or params['target']=='player': raise ValueError('invalid target')
                    if not self.space.visible('player',params['target']): self.notice='她目前不在視野內。'
                    elif not self._approach('player',params['target']): self.notice='目前找不到可以靠近的路。'
                else:
                    if set(params)!={'object'}: raise ValueError('invalid object')
                    obj=next((o for o in self.map_spec['maps'][player['scene']]['objects'] if o['id']==params['object']),None)
                    if not obj or abs(obj['x']-player['x'])+abs(obj['y']-player['y'])>2: raise ValueError('object too far')
                    outcome=self._do('player',Action('interact',{'object':params['object']}))
                    if not outcome.accepted:self.notice='這個互動目前無法執行：'+outcome.reason
                self._save()
            elif command in {'save','load','reset'}:
                if params: raise ValueError('invalid params')
                if command=='save': atomic_json(self.manual_path,{'version':1,'world':self.engine.journal(),'space':self.space.snapshot()}); self.notice='已存檔。'
                elif command=='load':
                    if self.manual_path.exists(): self._load_pixel(self.manual_path); self.notice='已讀取存檔；API 用量不會回退。'
                    else: self.notice='還沒有存檔。'
                else:
                    self.engine=Engine(play_world()); self.space=SpatialWorld(self.map_spec['maps'],self.engine); self.facilities.bind(); self.economy.bind(); self.wardrobe.bind(); self.social.bind();self.neighborhood.bind(); self.components.bind(clear=False); self.notice='重新開始；API 用量不會回退。'
                    self.last_motion=self.clock(); self.last_minute=self.clock()
                self.memory.sync(self.engine); self._save()
            elif command=='cg':
                if set(params) not in ({'target'},{'target','description'}) or params['target'] not in PEOPLE and params['target']!='player': raise ValueError('invalid cg target')
                extra=params.get('description','')
                from .character_art import BLOCKED
                if not isinstance(extra,str) or len(extra)>700 or BLOCKED.search(extra):raise ValueError('一般 CG 描述需為 700 字以內的 SFW 公開場景')
                if not self.renderer and not self.studio.services.get(self.studio.config['url'],{}).get('ready'):
                    self.notice='一般 CG 尚未連接本機 Stable Diffusion，請到生圖設定測試連線。'
                elif params['target']!='player' and not self.space.near('player',params['target']): self.notice='請先走近她。'
                elif self.renderer:
                    scene=self.space.entities['player']['scene'];outfit=self.wardrobe.appearance(params['target']);prompt=self.wardrobe.render_prompt(params['target'],scene)
                    self.renderer.submit(prompt,'player',{'character':params['target'],'scene':scene,'outfit':outfit['render_key']});self.notice='一般 CG 已排入背景生成；相同場景會重用素材。'
                else:
                    scene=self.space.entities['player']['scene'];outfit=self.wardrobe.appearance(params['target'])
                    descriptions={'shared':'a peaceful shared courtyard with flowers and wooden benches','park':'a riverside park with trees, flower beds and a garden bench','library':'a warm library with bookshelves, reading tables and soft light','cafe':'a cozy cafe with coffee cups and wooden tables','zoo':'an outdoor zoo walkway with trees and habitat signs','gallery':'a quiet art gallery with framed paintings','cinema':'a small cinema lobby with soft lights','restaurant':'a warm restaurant with a set dining table','market':'an outdoor craft market with handmade goods on stalls','boutique':'a clothing shop with racks of daily clothes','district':'a quiet neighborhood street with shops'}
                    descriptions['pool']='a public outdoor swimming pool with clear blue water, swimming lanes, changing rooms and deck chairs'
                    description=descriptions.get(scene,'a cozy daily living room with a desk and window')+(', '+extra if extra else '')
                    try:
                        self.studio.submit(params['target'],outfit,self.art_outfit_prompt(params['target']),'cg',{'scene':scene,'place_name':self.map_spec['maps'][scene]['name'],'description':description})
                        self.notice='一般 CG 已用她的 LoRA 與當下穿著排入背景生成；不扣聊天 API。'
                    except ValueError as exc:self.notice=str(exc)
            elif command=='move': raise ValueError('use physical walking and doors')
            elif command=='wait':
                if set(params)!={'minutes'} or type(params['minutes']) is not int or not 1<=params['minutes']<=10: raise ValueError('invalid minutes')
                for _ in range(params['minutes']): self._native_step()
                ids=list(self.engine.agent_ids());pivot=self.engine.tick%len(ids);order=ids[pivot:]+ids[:pivot]
                candidates=[a for a in order if self.engine.view(a)['self']['busy_until']<=self.engine.tick]
                pending=[a for a in candidates if any(inv['status']=='pending' and inv['recipient']==a for inv in self.engine.view(a)['invitations'])]
                company=[a for a in candidates if self.engine.view(a)['nearby']]
                if candidates:
                    actor=(pending or company or candidates)[0];action=self._ai(actor,'自由活動')
                    if action and action.kind in {'say','invite'} and action.params.get('target') in PEOPLE:
                        self._ai(action.params['target'],'另一位成員邀約' if action.kind=='invite' else '另一位成員向你說話')
                self.engine.advance();self.memory.sync(self.engine);self._save()
                self.last_motion=self.clock();self.last_minute=self.clock()
            elif command in {'talk','invite','wait','respond'}:
                if command in {'talk','invite'}:
                    target=params.get('target')
                    if target not in PEOPLE: raise ValueError('invalid target')
                    if not self.space.near('player',target): self.notice='請先走近她再互動。'; return self.screen()
                    self.space.entities['player']['path']=[]; self.space.entities[target]['path']=[]; self.space.entities[target]['destination']=None
                result=super().act(body)
                # Exclude API latency from the simulation clock.
                self.last_motion=self.clock(); self.last_minute=self.clock()
                self.memory.sync(self.engine)
                return result
            else: raise ValueError('unknown command')
            self.engine.assert_consistent()
            return self.screen()

    def close(self):
        if hasattr(self,'studio'):self.studio.closed=True
        if self.renderer: self.renderer.close(wait=False)
