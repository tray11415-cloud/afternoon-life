from pathlib import Path
import sys,copy,json,tempfile,unittest,base64,io,threading
from unittest.mock import patch
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
source=Path(__file__).parent/'component-upgrade/prototype'
if not source.is_dir():source=Path(__file__).resolve().parents[1]/'prototype'
sys.path.insert(0,str(source))
from lifebox.pixel import PixelSession
from lifebox.model import Action
from lifebox.engine import Engine
from lifebox.character_art import CharacterStudio
from lifebox.speech import SpeechStudio
from tests.test_play import FakeBackend
from PIL import Image
from lifebox.xai import AIError

class ComponentsTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=Path(__file__).parent);self.root=Path(self.tmp.name)
  with patch.object(CharacterStudio,'discover',lambda x,extra=None:x.state()),patch.object(CharacterStudio,'probe',lambda x:x.state()),patch.object(SpeechStudio,'refresh_windows',lambda x:x.state()):self.s=PixelSession(self.root,FakeBackend(),clock=lambda:100)
  self.c=self.s.components
 def tearDown(self):self.s.close();self.tmp.cleanup()
 def replace(self,target,value):
  p=self.c.prepare({'instruction':'測試替換','changes':[{'target':target,'value':value}]});return p,self.c.apply(p['id'])
 def test_inventory_covers_all_layers(self):
  kinds={t['kind'] for t in self.c.state()['targets']};self.assertTrue({'map','object','visual','art','catalog','item','clothing','actor','npc','events','rules','service','theme'}<=kinds);self.assertGreater(len(self.c.targets()),1500)
 def test_preview_has_no_world_writes(self):
  before=self.s.engine.journal();self.c.plan({'instruction':'說明改成新更衣櫃','targets':['object:pool:pool-locker']});self.assertEqual(before,self.s.engine.journal());self.assertEqual(self.c.registry['revision'],0)
 def test_object_replacement_and_rollback(self):
  target='object:pool:pool-locker';old=self.c.get(target);p=self.c.plan({'instruction':'說明改成新更衣櫃','targets':[target]});self.assertEqual(p['changes'][0]['diff'][0]['field'],'/description');self.c.apply(p['id']);self.assertEqual(self.s.map_spec['maps']['pool']['objects'][1]['description'],'新更衣櫃')
  undo=self.c.rollback(p['id']);self.assertEqual(self.c.get(target)['description'],'新更衣櫃');self.c.apply(undo['id']);self.assertEqual(self.c.get(target),old)
 def test_stale_proposal_rejected(self):
  a=self.c.plan({'instruction':'說明改成A','targets':['object:pool:pool-locker']});b=self.c.plan({'instruction':'說明改成B','targets':['object:pool:pool-locker']});self.c.apply(b['id'])
  with self.assertRaises(ValueError):self.c.apply(a['id'])
 def test_invalid_bundle_is_atomic(self):
  before=copy.deepcopy(self.c.registry);m=self.c.get('map:pool');m['blocked'].append(m['portals'][0]['spawn'])
  with self.assertRaises(ValueError):self.c.prepare({'instruction':'無效套件','changes':[{'target':'theme:interface','value':{'paper':'#000000','ink':'#ffffff','accent':'#ffffff'}},{'target':'map:pool','value':{**m,'width':2}}]})
  self.assertEqual(self.c.registry,before)
 def test_blocking_current_actor_rejected(self):
  p=self.s.space.entities['player'];m=self.c.get('map:'+p['scene']);m['blocked'].append([p['x'],p['y']])
  with self.assertRaises(ValueError):self.replace('map:'+p['scene'],m)
 def test_portals_and_spawns_validated(self):
  m=self.c.get('map:pool');m['blocked'].append([m['portals'][0]['x'],m['portals'][0]['y']])
  with self.assertRaises(ValueError):self.replace('map:pool',m)
 def test_geometry_changes_real_collision_and_reload(self):
  m=self.c.get('map:pool');m['blocked'].append([1,1]);self.replace('map:pool',m);self.assertFalse(self.s.space.passable('pool',1,1));journal=self.s.engine.journal();self.s._load_pixel(self.s.auto_path);self.assertEqual(journal,self.s.engine.journal());self.assertFalse(self.s.space.passable('pool',1,1))
 def test_new_portal_graph_is_journaled(self):
  # Relocate a door while preserving its matching reverse connection.
  m=self.c.get('map:pool');m['portals'][0]['x']=2;m['portals'][0]['y']=18;m['blocked']=[p for p in m['blocked'] if p!=[2,18]];old=self.s.engine.journal()['genesis'];self.replace('map:pool',m);self.assertEqual(self.s.engine.journal()['genesis'],old);self.assertEqual(self.s.space.maps['pool']['portals'][0]['x'],2)
 def test_interaction_is_available_to_an_agent(self):
  actor='member-01';e=self.s.space.entities[actor];obj=next(o for o in self.s.map_spec['maps'][e['scene']]['objects'] if o['effect']=='water');e.update(x=obj['x'],y=obj['y']+1,path=[],destination=None)
  v=self.c.get('object:'+e['scene']+':'+obj['id']);v['handler']={'kind':'notify','text':'本人觸碰這個物件'};self.replace('object:'+e['scene']+':'+obj['id'],v)
  result=self.s._do(actor,Action('interact',{'object':obj['id']}));self.assertTrue(result.accepted);own=self.s.engine.view(actor,100)['memories'];other=self.s.engine.view('member-02',100)['memories'];self.assertTrue(any(e['kind']=='component_interacted' for e in own));self.assertFalse(any(e['data'].get('notice')=='本人觸碰這個物件' for e in other))
 def test_remote_and_executable_tools_rejected(self):
  for endpoint in ['https://example.com/tool','http://127.0.0.1:9000/tool?key=x','http://user:secret@localhost:9000/tool']:
   with self.assertRaises(ValueError):self.replace('tool:coffee',{'adapter':'local-tool','endpoint':endpoint,'enabled':True,'max_calls':10})
  v=self.c.get('object:pool:pool-locker');v['handler']={'kind':'command','action':{'kind':'reset','params':{}}}
  with self.assertRaises(ValueError):self.replace('object:pool:pool-locker',v)
 def test_own_actor_public_profile_replays(self):
  before=self.s.engine.journal()['genesis'];v=self.c.get('actor:player');v['name']='旅人';self.replace('actor:player',v);self.assertEqual(self.s.engine.view('player')['self']['name'],'旅人');self.assertEqual(Engine.replay(self.s.engine.journal()).view('player')['self']['name'],'旅人');self.assertEqual(before,self.s.engine.journal()['genesis'])
 def test_npc_script_replaced(self):
  v=self.c.get('npc:npc-pool');v.update(name='新管理員',line='先更衣再下水');self.replace('npc:npc-pool',v);self.assertEqual(self.s.neighborhood.npcs['npc-pool']['line'],'先更衣再下水');self.assertEqual(self.s.engine.view('npc-pool')['self']['name'],'新管理員')
 def test_new_prices_dont_reprice_purchased_items(self):
  original=self.s.wardrobe.appearance('player');v=self.c.get('clothing:cream-cardigan');v['title']='新款外套';v['price']=100;self.replace('clothing:cream-cardigan',v);self.assertEqual(self.s.wardrobe.appearance('player'),original);self.assertEqual(self.s.wardrobe.catalog['cream-cardigan']['price'],100)
 def test_item_price_updates_actual_catalog(self):
  item=self.s.facilities.data['restaurant']['items'][0];target='item:restaurant:'+item['id'];v=self.c.get(target);v['price']=17;self.replace(target,v);self.assertEqual(self.s.facilities.items('restaurant')[0]['price'],17)
 def test_economy_rules_bound_to_instance(self):
  v=self.c.get('rules:economy');v.update(wage=71,shift_minutes=8);self.replace('rules:economy',v);self.assertEqual(self.s.economy.rule('wage',0),71);self.assertEqual(self.s.economy.browse('player')['shift']['minutes'],8)
 def test_public_event_schedule_replaced(self):
  v=self.c.get('events:calendar');v[0]['title']='替換後祭典';self.replace('events:calendar',v);self.assertEqual(self.s.neighborhood.festivals[0]['title'],'替換後祭典')
 def test_pool_rules_apply_to_actual_gate(self):
  v=self.c.get('rules:pool');v.update(rental_price=9,swim_minutes=7,water=[10,5,21,11]);self.replace('rules:pool',v);self.assertFalse(self.s.neighborhood.water('pool',9,4));self.assertTrue(self.s.neighborhood.water('pool',10,5));self.assertEqual(self.s.neighborhood.pool_rules['rental_price'],9)
 def test_astar_has_legal_route(self):
  self.replace('rules:movement',{'algorithm':'astar'});e=self.s.space.entities['player'];route=self.s.space.path(e['scene'],(e['x'],e['y']),(e['x']+1,e['y']),'player');self.assertTrue(route);self.assertEqual(route[-1],[e['x']+1,e['y']])
 def test_art_png_real_asset_and_export(self):
  target='art:lpc-prop-books.png';size=self.c.get(target)['size'];im=Image.new('RGBA',size,'#ffeecc');buf=io.BytesIO();im.save(buf,format='PNG');p=self.c.prepare({'instruction':'換書架圖','changes':[{'target':target,'png':base64.b64encode(buf.getvalue()).decode()}]});self.assertEqual(self.c.registry['revision'],0);self.c.apply(p['id']);v=self.c.get(target);self.assertTrue(self.c.asset(v['file']));self.assertEqual(self.c.public()['art'][target[4:]],v['url']);export=self.c.operation({'operation':'export','params':{'targets':[target]}});self.assertIn('png',export['changes'][0])
 def test_visual_props_and_tiles_replaced(self):
  v=self.c.get('visual:pool');v['decor']=[{'id':'new-chair','image':'/assets/lpc-prop-books.png','x':32,'y':64,'depth':96}];v['tiles']=[{'image':'/assets/lpc-prop-books.png','source':[0,0,16,16],'x':0,'y':0,'width':32,'height':32}];self.replace('visual:pool',v);self.assertEqual(self.c.get('visual:pool')['decor'][0]['id'],'new-chair')
 def test_active_progress_and_money_preserved(self):
  old=self.s.engine.journal();wallet=self.s.screen()['wallet'];self.replace('theme:interface',{'paper':'#dddddd','ink':'#222222','accent':'#446644'});now=self.s.engine.journal();self.assertEqual(old['genesis'],now['genesis']);self.assertEqual(old['events'],now['events'][:len(old['events'])]);self.assertEqual(wallet,self.s.screen()['wallet']);self.assertEqual(self.s.backend.base.contexts,[])
 def test_memory_switch_preserves_rows(self):
  self.s.memory.sync(self.s.engine);old=self.s.memory.path;self.replace('service:memory',{'adapter':'lexical','endpoint':'http://127.0.0.1:11434','model':''});self.assertEqual(self.s.memory.path,old);self.assertIn('lexical',self.s.memory.provider)
 def test_schema_has_replace_and_world_contracts(self):
  schema=self.c.schema();self.assertIn('replacement',schema['adapter_contracts']);self.assertEqual({t['name'] for t in schema['tools']},{'get','plan','prepare','apply','rollback','export'})
 def test_each_decor_has_replaceable_id(self):
  target=next(k for k in self.c.targets() if k.startswith('decor:cafe:'));v=self.c.get(target);v['x']+=16;self.replace(target,v);self.assertEqual(next(d for d in self.c.get('visual:cafe')['decor'] if d['id']==v['id'])['x'],v['x'])
 def test_moved_work_desk_changes_craft_and_goal_location(self):
  v=self.c.get('object:room-01:desk');v.update(x=10,y=10);self.replace('object:room-01:desk',v);self.assertEqual(self.s.work_spot('room-01'),(11,12));e=self.s.space.entities['member-01'];e.update(scene='room-01',x=10,y=11,path=[],destination=None);self.assertTrue(self.s.economy.at_craft('member-01'))
 def test_agent_can_approach_an_object_physically(self):
  e=self.s.space.entities['member-01'];position=(e['x'],e['y']);result=self.s._do('member-01',Action('approach_object',{'object':'bench'}));self.assertTrue(result.accepted);self.assertEqual((e['x'],e['y']),position);self.assertTrue(e['path'])
 def test_object_context_is_current_scene_only(self):
  rows=self.c.object_context('member-01');self.assertTrue(rows);self.assertNotIn('desk',{r['id'] for r in rows});self.assertFalse(any('handler' in r for r in rows))
 def test_SD_service_preview_apply_and_rollback(self):
  studio=self.s.studio;studio.folders=[{'id':'f','backend':'a1111','path':str(self.root)}];studio.config.update(installation='f',backend='a1111');original=copy.deepcopy(studio.config);v=self.c.get('service:sd');v['templates']['portrait']['steps']=17;v['auto']=False
  p=self.c.prepare({'instruction':'替換SD參數','changes':[{'target':'service:sd','value':v}]});self.assertEqual(studio.config,original);self.c.apply(p['id']);self.assertEqual(studio.config['templates']['portrait']['steps'],17);undo=self.c.rollback(p['id']);self.c.apply(undo['id']);self.assertEqual(studio.config,original)
 def test_TTS_service_preview_apply_and_rollback(self):
  original=copy.deepcopy(self.s.speech.config);v=self.c.get('service:tts');v['language']='en-US';p=self.c.prepare({'instruction':'替換語言','changes':[{'target':'service:tts','value':v}]});self.assertEqual(self.s.speech.config,original);self.c.apply(p['id']);self.assertEqual(self.s.speech.config['language'],'en-US');undo=self.c.rollback(p['id']);self.c.apply(undo['id']);self.assertEqual(self.s.speech.config,original)

class LocalContracts(ComponentsTests):
 def setUp(self):
  super().setUp();self.received=[];owner=self
  class Handler(BaseHTTPRequestHandler):
   def log_message(self,*a):pass
   def do_POST(self):
    d=json.loads(self.rfile.read(int(self.headers['Content-Length'])));owner.received.append(d)
    if d['contract']=='lifebox.replace.v1':
     target,v=next(iter(d['components'].items()));v['description']='AI 指示替換的結果';out={'changes':[{'target':target,'value':v}]}
    elif d['contract']=='lifebox.interact.v1':out={'notice':'咖啡機完成了互動'}
    else:out={'action':{'kind':'wait','params':{}}}
    raw=json.dumps(out).encode();self.send_response(200);self.send_header('Content-Length',str(len(raw)));self.end_headers();self.wfile.write(raw)
  self.server=ThreadingHTTPServer(('127.0.0.1',0),Handler);self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start();self.endpoint='http://127.0.0.1:'+str(self.server.server_port)
 def tearDown(self):self.server.shutdown();self.server.server_close();super().tearDown()
 def test_local_ai_decide_receives_one_actor(self):
  self.replace('service:dialogue',{'adapter':'local-decide','endpoint':self.endpoint+'/decide','model':'my-model','max_calls':1});context=self.s.engine.view('member-01',4);self.s.backend.decide(context,'自身語氣','另一位成員向你說話');d=self.received[0];self.assertEqual(d['actor'],'member-01');self.assertNotIn('actors',d['context']);self.assertEqual(self.s.backend.base.contexts,[])
  with self.assertRaises(AIError):self.s.backend.decide(context,'自身語氣','另一位成員向你說話')
 def test_local_replacement_ai_previews_then_applies(self):
  self.replace('service:replacement',{'adapter':'local-plan','endpoint':self.endpoint+'/replace','model':'editor','max_calls':2});old=self.c.get('object:pool:pool-locker');p=self.c.plan({'instruction':'換成更清楚的說明','targets':['object:pool:pool-locker']});self.assertEqual(self.c.get('object:pool:pool-locker'),old);self.c.apply(p['id']);self.assertEqual(self.c.get('object:pool:pool-locker')['description'],'AI 指示替換的結果');self.assertNotIn('memories',self.received[0])
 def test_local_object_tool_is_invokable(self):
  self.replace('tool:coffee',{'adapter':'local-tool','endpoint':self.endpoint+'/interact','enabled':True,'max_calls':2});v=self.c.get('object:shared:bench');v['handler']={'kind':'tool','tool':'tool:coffee','arguments':{'drink':'tea'}};self.replace('object:shared:bench',v);e=self.s.space.entities['player'];e.update(x=v['x'],y=v['y']+1,path=[],destination=None);result=self.s._do('player',Action('interact',{'object':v['id']}));self.assertTrue(result.accepted);self.assertEqual(self.received[0]['actor'],'player');self.assertEqual(self.received[0]['context']['self']['id'],'player')

if __name__=='__main__':unittest.main()
