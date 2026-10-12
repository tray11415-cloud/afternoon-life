import json,tempfile,unittest
from pathlib import Path
from lifebox.pixel import PixelSession,atomic_json
from lifebox.engine import Engine
from lifebox.play import play_world
from lifebox.model import Action,canonical
from lifebox.spatial import SpatialWorld
from tests.test_play import FakeBackend

class VenueTests(unittest.TestCase):
 def setUp(self):
  root=Path(__file__).resolve().parents[2]/'work';root.mkdir(exist_ok=True)
  self.temp=tempfile.TemporaryDirectory(dir=root);self.backend=FakeBackend();self.now=100
  self.s=PixelSession(Path(self.temp.name),self.backend,clock=lambda:self.now)
 def tearDown(self):self.s.close();self.temp.cleanup()
 def tick(self,n=1):
  for _ in range(n):
   for _ in range(40):self.s.space.animate()
   self.s._native_step()
 def arrive(self,actor,scene):
  self.assertTrue(self.s.space.route_to(actor,scene))
  for _ in range(25):
   for _ in range(45):self.s.space.animate()
   self.s.engine.advance()
   if self.s.space.entities[actor]['scene']==scene:break
  self.assertEqual(self.s.space.entities[actor]['scene'],scene)
  self.s._desk_walk(actor)
  for _ in range(40):self.s.space.animate()
  self.assertTrue(self.s.facilities.near_desk(actor))
 def test_old_save_migration_preserves_hashes_and_history(self):
  """舊存檔擴建以事件遷移，原事件及私人歷史保留。"""
  engine=Engine(play_world());engine.dispatch('member-01',Action('say',{'target':None,'text':'遷移前的一句話'}),'old')
  before=engine.journal()['events'];space=SpatialWorld(self.s.map_spec['maps'],engine)
  atomic_json(self.s.manual_path,{'version':1,'world':engine.journal(),'space':space.snapshot()})
  self.s._load_pixel(self.s.manual_path)
  self.assertEqual(self.s.engine.journal()['events'][:len(before)],before)
  self.assertIn('district',self.s.engine.export_state()['locations'])
  journal=self.s.engine.journal();self.assertEqual(Engine.replay(journal).export_state(),self.s.engine.export_state())
 def test_public_maps_have_physical_round_trips(self):
  """九個公共場所都能經真實門口往返，無瞬移。"""
  for scene in self.s.facilities.data:
   self.arrive('player',scene)
   self.assertEqual(self.s.engine.view('player')['self']['location'],scene)
   self.s.space.route_to('player','shared')
   for _ in range(10):
    self.s.engine.advance()
    for _ in range(70):self.s.space.animate()
   self.assertEqual(self.s.space.entities['player']['scene'],'shared')
  self.assertEqual(self.backend.contexts,[])
 def test_distance_wallet_busy_and_idempotency(self):
  """消費只用遊戲代幣，距離、忙碌與重送都由核心裁定。"""
  s=self.s;item=s.facilities.items('cafe')[0]
  result=s.engine.dispatch('player',Action('use',{'item':item['id']}),'far');self.assertFalse(result.accepted)
  self.arrive('player','cafe');action=Action('use',{'item':item['id']})
  r=s.engine.dispatch('player',action,'buy');self.assertTrue(r.accepted)
  wallet=s.engine.view('player')['self']['wallet'];self.assertEqual(wallet,500-item['price'])
  self.assertEqual(s.engine.dispatch('player',action,'buy'),r)
  self.assertFalse(s.engine.dispatch('player',action,'busy').accepted)
  self.assertFalse(s.space.step('player','down'));s.engine.advance(item['minutes'])
  self.assertEqual(s.engine.view('player')['self']['wallet'],wallet)
  self.assertTrue(any(e['kind']=='venue_completed' for e in s.engine.view('player')['memories']))
 def test_reader_knowledge_private_and_branch_safe(self):
  """讀到的原文只屬於讀者；回到讀前存檔不能檢索未來內容。"""
  s=self.s;self.arrive('member-01','library');s._save();before=s.auto_path.read_bytes()
  book=next(b for b in s.facilities.items('library') if b.get('text'))
  self.assertTrue(s.engine.dispatch('member-01',Action('use',{'item':book['id']}),'read').accepted);s.engine.advance(book['minutes']);s.memory.sync(s.engine)
  completed=[e for e in s.engine.view('member-01')['memories'] if e['kind']=='venue_completed'];self.assertTrue(completed)
  self.assertNotIn(completed[0]['id'],[e['id'] for e in s.engine.view('member-02')['memories']])
  self.assertNotIn(completed[0]['id'],[e['id'] for e in s.screen()['outing_events']])
  s.auto_path.write_bytes(before);s._load_pixel(s.auto_path)
  self.assertFalse(any(e['kind']=='venue_completed' for e in s.memory.retrieve(s.engine,'member-01',book['title'],limit=20)))
 def test_agents_visit_and_use_offscreen_without_paid_calls(self):
  """十人離開玩家視野後也會完成工作、出門、消費及閱讀。"""
  # A day now includes shopping and returning home to change before outings.
  self.tick(400)
  events=[e for e in self.s.engine.journal()['events'] if e['kind']=='venue_completed' and e['actor']!='player']
  self.assertEqual(len({e['actor'] for e in events}),10)
  self.assertEqual({e['data']['venue'] for e in events},set(self.s.facilities.data))
  self.assertTrue(any(e['kind']=='economy_bought' for e in self.s.engine.journal()['events']))
  self.assertEqual(self.backend.contexts,[])
  self.s.engine.assert_consistent()
 def test_catalog_provenance_coverage_and_current_dates(self):
  """公開目錄有來源，電影有完整劇情快取，過期展覽不標當期。"""
  f=self.s.facilities;self.assertGreater(len(f.items('library')),400);self.assertGreater(len(f.items('cafe')),100);self.assertGreater(len(f.items('zoo')),150)
  self.assertGreaterEqual(sum(bool(i.get('text')) for i in f.items('library')),4)
  for i in f.items('cinema'):
   self.assertTrue(i['url'].startswith('https://video.blender.org/'));self.assertGreater(len(i['plot_text']),500);self.assertTrue(i['license_url'])
  f.data['gallery']['items'].append({'id':'expired','start':'2000-01-01','end':'2001-01-01'})
  self.assertNotIn('expired',[i['id'] for i in f.items('gallery')])
  self.arrive('player','library');view=f.browse('player');self.assertNotIn('text',view['items'][0]);self.assertNotIn('plot_text',canonical(view))
 def test_film_schedule_and_activity_survive_reload(self):
  """隨機場次、遊戲錢包與活動進度跨讀檔保持一致。"""
  s=self.s;self.arrive('player','cinema');now=s.facilities.items('cinema')[0]
  self.assertTrue(s.engine.dispatch('player',Action('use',{'item':now['id']}),'movie').accepted)
  s._save();j=s.engine.journal();seed=s.space.flags['cinema_seed'];s._load_pixel(s.auto_path)
  self.assertEqual(s.engine.journal(),j);self.assertEqual(s.space.flags['cinema_seed'],seed);self.assertEqual(s.facilities.items('cinema')[0]['id'],now['id'])
  s.engine.advance(now['minutes']);e=[e for e in s.engine.view('player')['memories'] if e['kind']=='venue_completed'][-1]
  self.assertIn('非視覺觀影',e['data']['scope']);self.assertIn(now['plot_text'],e['data']['knowledge']);self.assertLessEqual(len(e['data']['knowledge']),8000)
 def test_model_gets_only_own_completed_film_text_in_bounded_context(self):
  """聊天上下文取得完整文字劇情，同時維持個人權限與輸入上限。"""
  s=self.s;self.arrive('member-01','cinema');film=s.facilities.items('cinema')[0]
  self.assertTrue(s.engine.dispatch('member-01',Action('use',{'item':film['id']}),'learn-film').accepted)
  s.engine.advance(film['minutes']);s.memory.sync(s.engine);s._ai('member-01','自由活動')
  view=self.backend.contexts[-1];self.assertEqual(view['self']['id'],'member-01')
  knowledge=[e['data']['knowledge'] for e in view['memories'] if e['kind']=='venue_completed'];self.assertTrue(knowledge)
  self.assertIn(film['plot_text'],knowledge[-1]);self.assertLessEqual(len(canonical(view).encode()),16000)
 def test_changed_book_text_restarts_progress_without_losing_old_memory(self):
  """來源文字更新後重新記錄閱讀進度，已讀的舊版本記憶仍保留。"""
  s=self.s;self.arrive('player','library');book=next(i for i in s.facilities.items('library') if i.get('text'))
  for n in range(2):
   self.assertTrue(s.engine.dispatch('player',Action('use',{'item':book['id']}),'version-read-'+str(n)).accepted);s.engine.advance(book['minutes'])
  book['text']='新的來源版本：'+book['text'];r=s.facilities.resolve('player',book['id'])
  self.assertEqual(r['part'],0);self.assertTrue(r['knowledge'].startswith('新的來源版本'))
  old=[e for e in s.engine.view('player')['memories'] if e['kind']=='venue_completed'];self.assertEqual(len(old),2)
 def test_crowded_door_retries_after_blocker_leaves(self):
  """有人暫時擋門後仍能重新尋路，不會讓其他角色永遠卡在街口。"""
  s=self.s;walker=s.space.entities['member-01'];blocker=s.space.entities['member-02']
  walker.update(x=34,y=19,path=[],destination='district');blocker.update(x=34,y=18,path=[],destination=None)
  s.space.animate();self.assertEqual(walker['scene'],'shared');self.assertEqual(walker['path'],[])
  blocker.update(x=31,y=18)
  for _ in range(5):s.space.animate();s.engine.advance()
  self.assertEqual(walker['scene'],'district');self.assertEqual(s.engine.view('member-01')['self']['location'],'district')

if __name__=='__main__':unittest.main()
