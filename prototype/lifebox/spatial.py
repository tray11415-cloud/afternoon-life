"""Small original tile engine: collision, BFS paths, portals and visibility.

No model requests, private memories or model-authored coordinates. The server
owns positions. The browser interpolates these positions for animation only.
"""
from __future__ import annotations
import copy,heapq
from collections import deque
from .model import Action

DIRECTIONS={'down':(0,1),'left':(-1,0),'right':(1,0),'up':(0,-1)}

class SpatialWorld:
    def __init__(self,maps,engine,snapshot=None):
        self.maps=maps; self.engine=engine
        self.blocked={scene:{tuple(p) for p in m['blocked']} for scene,m in maps.items()}
        self.entities={}; self.flags={}; self.revision=0;self.movement_guard=None;self.on_portal=None
        starts=[(18,14),(20,15),(16,15)]
        for actor in engine._state['actors']:
            scene=engine.view(actor)['self']['location']
            index=int(actor[-2:])-1 if actor.startswith('member-') else 10
            pos=((18,17) if actor=='player' else starts[index] if index<3 else (15+(index%3),14+(index//3)%3)) if scene=='shared' else (7,7)
            occupied={(e['x'],e['y']) for e in self.entities.values() if e['scene']==scene}
            if not self.passable(scene,*pos) or pos in occupied:
                m=maps[scene]
                candidates=sorted(((x,y) for y in range(m['height']) for x in range(m['width'])),key=lambda p:abs(p[0]-pos[0])+abs(p[1]-pos[1]))
                pos=next(p for p in candidates if self.passable(scene,*p) and p not in occupied)
            self.entities[actor]={'id':actor,'scene':scene,'x':pos[0],'y':pos[1],'direction':'down','path':[],'destination':None,'walking':False}
        if snapshot is not None:
            if not isinstance(snapshot,dict) or set(snapshot)!={'entities','flags','revision'}: raise ValueError('invalid spatial save')
            if set(snapshot['entities'])!=set(self.entities): raise ValueError('invalid spatial actors')
            for actor,value in snapshot['entities'].items():
                if set(value)!=set(self.entities[actor]) or value['id']!=actor or value['scene']!=engine.view(actor)['self']['location']:
                    raise ValueError('spatial/world mismatch')
                if not self.passable(value['scene'],value['x'],value['y']) or value['direction'] not in DIRECTIONS:
                    raise ValueError('invalid saved position')
                if not isinstance(value['path'],list) or len(value['path'])>500: raise ValueError('invalid path')
                cursor=(value['x'],value['y'])
                for point in value['path']:
                    if not isinstance(point,list) or len(point)!=2 or not self.passable(value['scene'],*point) or abs(point[0]-cursor[0])+abs(point[1]-cursor[1])!=1:
                        raise ValueError('invalid saved path')
                    cursor=point
                if value['destination'] is not None and value['destination'] not in engine.view(actor)['paths']:
                    raise ValueError('invalid saved destination')
            if not isinstance(snapshot['flags'],dict) or type(snapshot['revision']) is not int: raise ValueError('invalid spatial state')
            self.entities=copy.deepcopy(snapshot['entities']); self.flags=copy.deepcopy(snapshot['flags']); self.revision=snapshot['revision']
            journeys=self.flags.get('journeys',{})
            if not isinstance(journeys,dict) or any(a not in self.entities or d not in maps for a,d in journeys.items()): raise ValueError('invalid journey')
            outings=self.flags.get('outings',{})
            if not isinstance(outings,dict) or any(a not in self.entities or not isinstance(p,dict) or set(p)!={'venue','due'} or p['venue'] not in maps or type(p['due']) is not int or p['due']<0 for a,p in outings.items()): raise ValueError('invalid outing')
        occupied=[(e['scene'],e['x'],e['y']) for e in self.entities.values()]
        if len(occupied)!=len(set(occupied)): raise ValueError('overlapping actors')
        engine.proximity=self.near

    def snapshot(self): return copy.deepcopy({'entities':self.entities,'flags':self.flags,'revision':self.revision})
    def route_to(self,actor,destination):
        if destination not in self.maps: return False
        self.flags.setdefault('journeys',{})[actor]=destination
        self.entities[actor]['path']=[]; self.entities[actor]['destination']=None
        self.revision+=1
        return self.continue_journey(actor)
    def continue_journey(self,actor):
        target=self.flags.get('journeys',{}).get(actor)
        if not target: return True
        e=self.entities[actor]
        if e['scene']==target:
            del self.flags['journeys'][actor]; self.revision+=1
            return True
        if e['path'] or e['destination'] or self.engine.view(actor)['self']['busy_until']>self.engine.tick: return True
        todo=deque([(e['scene'],[])]); seen={e['scene']}
        while todo:
            scene,route=todo.popleft()
            if scene==target: return self.travel(actor,route[0])
            for portal in self.maps[scene]['portals']:
                if portal['to'] not in seen: seen.add(portal['to']);todo.append((portal['to'],route+[portal['to']]))
        return False
    def passable(self,scene,x,y):
        return (scene in self.maps and type(x) is int and type(y) is int and
                0<=x<self.maps[scene]['width'] and 0<=y<self.maps[scene]['height'] and (x,y) not in self.blocked[scene])
    def occupied(self,scene,x,y,except_id=None):
        return any(e['id']!=except_id and e['scene']==scene and (e['x'],e['y'])==(x,y) for e in self.entities.values())
    def line_clear(self,scene,a,b):
        x,y=a; dx=b[0]-x; dy=b[1]-y; n=max(abs(dx),abs(dy))
        return all((round(x+dx*i/n),round(y+dy*i/n)) not in self.blocked[scene] for i in range(1,n)) if n else True
    def near(self,a,b):
        one,two=self.entities[a],self.entities[b]
        return one['scene']==two['scene'] and abs(one['x']-two['x'])+abs(one['y']-two['y'])<=2 and self.line_clear(one['scene'],(one['x'],one['y']),(two['x'],two['y']))
    def visible(self,observer,other):
        a,b=self.entities[observer],self.entities[other]
        return a['scene']==b['scene'] and max(abs(a['x']-b['x']),abs(a['y']-b['y']))<=14
    def path(self,scene,start,target,actor,queue=False,_crowded=False):
        def queued_at(point):
            return any(b['id'] not in (actor,'player') and b['scene']==scene and (b['x'],b['y'])==tuple(point) and
                       (b['path'] or b['destination'] or self.flags.get('journeys',{}).get(b['id'])) for b in self.entities.values())
        if not self.passable(scene,*target) or (not _crowded and self.occupied(scene,*target,actor)):
            return self.path(scene,start,target,actor,queue=True,_crowded=True) if queue and not _crowded and self.passable(scene,*target) and queued_at(target) else []
        doors={(p['x'],p['y']) for p in self.maps[scene]['portals']}
        astar=getattr(self,'algorithm','bfs')=='astar';target=tuple(target);initial=tuple(start);costs={initial:0};todo=[(0,0,initial)] if astar else deque([initial]);previous={initial:None}
        while todo:
            if astar:
                _,cost,p=heapq.heappop(todo)
                if cost!=costs[p]:continue
            else:p=todo.popleft();cost=costs[p]
            if p==target:
                result=[]
                while previous[p] is not None: result.append(list(p)); p=previous[p]
                return result[::-1]
            for dx,dy in DIRECTIONS.values():
                q=(p[0]+dx,p[1]+dy)
                if (q not in previous or astar and cost+1<costs.get(q,10**9)) and (q==target or q not in doors) and self.passable(scene,*q) and (self.movement_guard is None or self.movement_guard(actor,scene,*q)) and (not self.occupied(scene,*q,actor) or (_crowded and queued_at(q))):
                    previous[q]=p;costs[q]=cost+1
                    if astar:heapq.heappush(todo,(cost+1+abs(q[0]-target[0])+abs(q[1]-target[1]),cost+1,q))
                    else:todo.append(q)
        return self.path(scene,start,target,actor,queue=True,_crowded=True) if queue and not _crowded else []
    def walk_to(self,actor,x,y):
        e=self.entities[actor]; route=self.path(e['scene'],(e['x'],e['y']),(x,y),actor)
        if not route: return (e['x'],e['y'])==(x,y)
        e['path']=route; e['destination']=None; self.revision+=1
        return True
    def travel(self,actor,destination):
        e=self.entities[actor]
        if destination not in self.engine.view(actor)['paths']: return False
        portal=next(p for p in self.maps[e['scene']]['portals'] if p['to']==destination)
        if (e['x'],e['y'])==(portal['x'],portal['y']): return self._portal(actor,portal)
        route=self.path(e['scene'],(e['x'],e['y']),(portal['x'],portal['y']),actor,queue=True)
        if not route: return False
        e['path']=route; e['destination']=destination; self.revision+=1
        return True
    def _portal(self,actor,portal):
        e=self.entities[actor]; scene=portal['to']; x,y=portal['spawn']
        if self.occupied(scene,x,y,actor):
            candidates=[(x+dx,y+dy) for dx,dy in DIRECTIONS.values()]
            spot=next((p for p in candidates if self.passable(scene,*p) and not self.occupied(scene,*p,actor)),None)
            if spot is None: return False
            x,y=spot
        result=self.engine.dispatch(actor,Action('move',{'location':scene}),f'portal:{actor}:{self.revision}:{self.engine.tick}',expected_tick=self.engine.tick)
        if not result.accepted: return False
        e.update(scene=scene,x=x,y=y,path=[],destination=None,walking=False); self.revision+=1
        if self.on_portal:self.on_portal()
        return True
    def step(self,actor,direction):
        if direction not in DIRECTIONS: raise ValueError('invalid direction')
        e=self.entities[actor]; own=self.engine.view(actor)['self']
        if own['activity'] in {'working','meeting','visiting','earning','crafting'} and own['busy_until']>self.engine.tick: return False
        dx,dy=DIRECTIONS[direction]; x,y=e['x']+dx,e['y']+dy
        if self.movement_guard is not None and not self.movement_guard(actor,e['scene'],x,y):e['walking']=False;return False
        e['direction']=direction
        if not self.passable(e['scene'],x,y) or self.occupied(e['scene'],x,y,actor): e['walking']=False; return False
        e.update(x=x,y=y,walking=True); self.revision+=1
        portal=next((p for p in self.maps[e['scene']]['portals'] if (p['x'],p['y'])==(x,y)),None)
        if portal: self._portal(actor,portal)
        return True
    def animate(self,focus=None):
        for actor,e in self.entities.items():
            e['walking']=False
            if actor==focus: continue
            own=self.engine.view(actor)['self']
            if own['busy_until']>self.engine.tick: continue
            self.continue_journey(actor)
            if not e['path']:
                if e['destination']:
                    portal=next(p for p in self.maps[e['scene']]['portals'] if p['to']==e['destination'])
                    if (e['x'],e['y'])==(portal['x'],portal['y']): self._portal(actor,portal)
                    else:
                        # A crowded door can invalidate a route for one frame.
                        # Retry after others move instead of stranding the actor.
                        e['path']=self.path(e['scene'],(e['x'],e['y']),(portal['x'],portal['y']),actor,queue=True)
                continue
            next_point=e['path'][0]; dx=next_point[0]-e['x']; dy=next_point[1]-e['y']
            direction=next((key for key,value in DIRECTIONS.items() if value==(dx,dy)),None)
            if direction and self.step(actor,direction):
                # step may switch scene at a portal and clear the path.
                if e['path'] and e['path'][0]==next_point: e['path'].pop(0)
            elif e['path']:
                target=e['path'][-1]
                # Let two travellers pass in a narrow doorway. Never move the
                # player or an actor doing a timed activity out of the way.
                blocker=next((b for b in self.entities.values() if b['id']!=actor and b['scene']==e['scene'] and (b['x'],b['y'])==tuple(next_point)),None)
                if blocker and blocker['id'] not in ('player',focus) and (blocker['path'] or blocker['destination'] or self.flags.get('journeys',{}).get(blocker['id'])) and self.engine.view(blocker['id'])['self']['busy_until']<=self.engine.tick:
                    doors={(p['x'],p['y']) for p in self.maps[e['scene']]['portals']}
                    options=[(-dy,dx),(dy,-dx),(dx,dy)]
                    for sx,sy in options:
                        spot=(blocker['x']+sx,blocker['y']+sy)
                        if spot not in doors and self.passable(e['scene'],*spot) and not self.occupied(e['scene'],*spot,blocker['id']):
                            turn=next(key for key,value in DIRECTIONS.items() if value==(sx,sy))
                            self.step(blocker['id'],turn);blocker['path']=[]
                            break
                e['path']=self.path(e['scene'],(e['x'],e['y']),target,actor,queue=e['destination'] is not None)
    def public(self,viewer):
        result=[]
        for actor,e in self.entities.items():
            if actor==viewer or self.visible(viewer,actor):
                own=self.engine.view(actor)['self']
                result.append({k:e[k] for k in ('id','scene','x','y','direction','walking')}|{'activity':'moving' if e['path'] else own['activity'],'near':actor!=viewer and self.near(viewer,actor)})
        return result
