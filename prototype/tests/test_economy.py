import copy, tempfile, unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from lifebox.engine import Engine
from lifebox.model import Action, canonical
from lifebox.economy import RECIPES, day
from lifebox.pixel import PixelSession
from tests.test_play import FakeBackend

class EconomyTests(unittest.TestCase):
 def setUp(self):
  root=Path(__file__).resolve().parents[2]/'work';root.mkdir(exist_ok=True)
  self.temp=tempfile.TemporaryDirectory(dir=root);self.backend=FakeBackend()
  self.s=PixelSession(Path(self.temp.name),self.backend,clock=lambda:100)
 def tearDown(self):self.s.close();self.temp.cleanup()
 def own(self,actor='player'):return self.s.engine.view(actor)['self']
 def act(self,kind,params=None,actor='player',request=None):
  return self.s.engine.dispatch(actor,Action(kind,params or {}),request or str(self.s.engine.revision))
 def arrive(self,actor,scene,craft=False):
  self.assertTrue(self.s.space.route_to(actor,scene))
  for _ in range(30):
   for _ in range(50):self.s.space.animate()
   self.s.engine.advance()
   if self.s.space.entities[actor]['scene']==scene:break
  self.assertEqual(self.s.space.entities[actor]['scene'],scene)
  if craft:
   for x,y in ((6,6),(7,6),(5,6),(6,7)):
    if self.s.space.walk_to(actor,x,y):break
  else:self.s._desk_walk(actor)
  for _ in range(80):self.s.space.animate()
  if craft:self.assertLessEqual(abs(self.s.space.entities[actor]['x']-6)+abs(self.s.space.entities[actor]['y']-5),3)
  else:self.assertTrue(self.s.facilities.near_desk(actor))
 def make(self,actor='member-01'):
  self.arrive(actor,'room-01' if actor=='player' else 'room-'+actor[-2:],True)
  self.assertTrue(self.act('craft',actor=actor).accepted);self.s.engine.advance(12)
 def offer(self,actor='member-01',quantity=2,price=24):
  self.make(actor);self.arrive(actor,'market')
  self.assertTrue(self.act('offer',{'item':RECIPES[actor]['id'],'quantity':quantity,'price':price},actor).accepted)
  return self.s.economy.listings()[-1]['id']
 def test_shift_requires_presence_and_completion_and_blocks_leaving(self):
  self.assertEqual(self.act('shift').reason,'job_too_far');self.arrive('player','park')
  money=self.own()['wallet'];tick=self.s.engine.tick
  r=self.act('shift',request='shift-once');self.assertTrue(r.accepted)
  self.assertEqual(self.act('shift',request='shift-once'),r)
  self.assertEqual(self.own()['wallet'],money);self.assertFalse(self.s.space.step('player','down'))
  self.assertFalse(self.s._do('player',Action('visit',{'location':'market'})).accepted)
  self.s.engine.advance(19);self.assertEqual(self.own()['wallet'],money)
  self.s.engine.advance();self.assertEqual(self.own()['wallet'],money+48)
  self.assertEqual(self.own()['life']['income']['wages'],48)
  self.assertEqual(self.s.engine.tick,tick+20)
  self.s.engine.advance(3);self.assertEqual(self.own()['wallet'],money+48)
 def test_two_shifts_per_game_day_and_midnight_reserves_start_day(self):
  self.arrive('player','park')
  for _ in range(2):self.assertTrue(self.act('shift').accepted);self.s.engine.advance(20)
  self.assertEqual(self.act('shift').reason,'shift_limit')
  self.s.engine.advance(599-self.s.engine.tick)
  self.assertEqual(day(self.s.engine.tick),0)
  self.s.engine.advance();self.assertEqual(day(self.s.engine.tick),1)
  self.assertTrue(self.act('shift').accepted);self.s.engine.advance(20)
  self.assertEqual(self.own()['life']['shifts'],{'0':2,'1':1})
  self.s.engine.advance(2039-self.s.engine.tick)
  self.assertTrue(self.act('shift').accepted);self.s.engine.advance(20)
  self.assertEqual(day(self.s.engine.tick),2)
  self.assertEqual(self.own()['life']['shifts']['1'],2)
  self.assertTrue(self.act('shift').accepted)
 def test_mid_shift_load_and_replay_pay_exactly_once(self):
  self.arrive('player','market');self.assertTrue(self.act('shift').accepted)
  self.s.engine.advance(9);self.s._save();before=self.s.engine.journal();money=self.own()['wallet']
  self.s._load_pixel(self.s.auto_path);self.assertEqual(self.s.engine.journal(),before)
  self.s.engine.advance(11);self.assertEqual(self.own()['wallet'],money+48)
  self.s._save();self.s._load_pixel(self.s.auto_path);self.s.engine.advance(2)
  self.assertEqual(self.own()['wallet'],money+48)
  self.assertEqual(Engine.replay(self.s.engine.journal()).export_state(),self.s.engine.export_state())
 def test_home_craft_consumes_material_and_produces_only_after_time(self):
  self.assertEqual(self.act('craft',actor='member-01').reason,'craft_too_far')
  self.arrive('member-01','room-02',True)
  self.assertEqual(self.act('craft',actor='member-01').reason,'craft_too_far')
  self.arrive('member-01','room-01',True);money=self.own('member-01')['wallet']
  self.assertTrue(self.act('craft',actor='member-01').accepted)
  self.assertEqual(self.own('member-01')['life']['inventory'],{'materials':2})
  self.s.engine.advance(11);self.assertNotIn('made-member-01',self.own('member-01')['life']['inventory'])
  self.s.engine.advance();self.assertEqual(self.own('member-01')['life']['inventory']['made-member-01'],2)
  self.assertEqual(self.own('member-01')['wallet'],money)
 def test_market_transfers_stock_and_money_once_with_escrow(self):
  listing=self.offer();self.arrive('player','market')
  self.assertEqual(self.own('member-01')['life']['inventory']['made-member-01'],0)
  total=self.own()['wallet']+self.own('member-01')['wallet']
  r=self.act('buy',{'listing':listing},request='purchase-once');self.assertTrue(r.accepted)
  self.assertEqual(self.act('buy',{'listing':listing},request='purchase-once'),r)
  self.assertEqual(self.own()['wallet'],476);self.assertEqual(self.own('member-01')['wallet'],524)
  self.assertEqual(self.own()['wallet']+self.own('member-01')['wallet'],total)
  self.assertEqual(self.own()['life']['inventory']['made-member-01'],1)
  self.assertEqual(self.s.economy.listings()[0]['quantity'],1)
  self.assertEqual(self.own('member-01')['life']['income']['sales'],24)
 def test_two_buyers_compete_for_last_unit(self):
  listing=self.offer(quantity=1);self.arrive('player','market');self.arrive('member-02','market')
  before=sum(self.own(a)['wallet'] for a in ('player','member-01','member-02'))
  with ThreadPoolExecutor(2) as pool:
   results=list(pool.map(lambda a:self.act('buy',{'listing':listing},actor=a),('player','member-02')))
  self.assertEqual(sum(r.accepted for r in results),1)
  self.assertEqual(self.s.economy.listings(),[])
  self.assertEqual(sum(self.own(a)['wallet'] for a in ('player','member-01','member-02')),before)
  self.assertEqual(sum(self.own(a)['life']['inventory'].get('made-member-01',0) for a in ('player','member-02')),1)
 def test_market_rejects_self_purchase_forgery_and_foreign_withdraw(self):
  listing=self.offer();self.arrive('player','market')
  self.assertEqual(self.act('buy',{'listing':listing},actor='member-01').reason,'self_purchase')
  self.assertEqual(self.act('withdraw',{'listing':listing}).reason,'not_seller')
  self.assertEqual(self.act('buy',{'listing':listing,'price':1}).reason,'invalid_action_params')
  self.assertEqual(self.act('offer',{'item':'made-player','quantity':1,'price':25}).reason,'stock_missing')
  self.assertTrue(self.act('withdraw',{'listing':listing},actor='member-01').accepted)
  self.assertEqual(self.own('member-01')['life']['inventory']['made-member-01'],2)
  self.assertEqual(self.act('buy',{'listing':listing}).reason,'unknown_listing')
 def test_affordability_validation_is_atomic(self):
  listing=self.offer(price=100);self.arrive('player','market')
  for _ in range(35):self.assertTrue(self.act('buy_supply',{'item':'materials'}).accepted)
  self.assertEqual(self.own()['wallet'],80)
  stock=copy.deepcopy(self.s.economy.listings());seller=self.own('member-01')['wallet']
  self.assertEqual(self.act('buy',{'listing':listing}).reason,'insufficient_funds')
  self.assertEqual(self.s.economy.listings(),stock);self.assertEqual(self.own('member-01')['wallet'],seller)
  for _ in range(13):self.assertTrue(self.act('buy_supply',{'item':'water'}).accepted)
  self.assertEqual(self.act('buy_supply',{'item':'water'}).reason,'insufficient_funds')
  self.assertEqual(self.own()['wallet'],2);self.s.engine.assert_consistent()
 def test_supplies_consumption_and_needs_are_real_and_clamped(self):
  self.arrive('player','market');self.assertTrue(self.act('buy_supply',{'item':'water'}).accepted)
  before=self.own()['life']['needs'];self.assertTrue(self.act('consume',{'item':'water'}).accepted)
  after=self.own()['life'];self.assertEqual(after['inventory']['water'],0)
  self.assertEqual(after['needs']['thirst'],max(0,before['thirst']-45));self.assertEqual(after['consumed'],1)
  self.s.engine.advance();self.assertEqual(self.act('consume',{'item':'water'}).reason,'stock_missing')
  self.assertEqual(self.act('consume',{'item':'materials'}).reason,'not_consumable')
  self.s.engine.advance(30);self.assertGreater(self.own()['life']['needs']['hunger'],before['hunger'])
 def test_cafe_takeaway_uses_catalog_price_and_portable_inventory(self):
  self.arrive('player','cafe');item=self.s.facilities.items('cafe')[0]
  self.assertTrue(self.act('buy_supply',{'item':item['id']}).accepted)
  self.assertEqual(self.own()['wallet'],500-item['price'])
  self.arrive('player','park');self.assertTrue(self.act('consume',{'item':item['id']}).accepted)
  self.assertEqual(self.own()['life']['inventory'][item['id']],0)
 def test_park_relief_is_after_actual_activity(self):
  self.arrive('player','park');before=self.own()['life']['needs']['fatigue']
  self.assertTrue(self.act('use',{'item':'park-rest'}).accepted)
  self.assertEqual(self.own()['life']['needs']['fatigue'],before)
  self.s.engine.advance(6);self.assertLess(self.own()['life']['needs']['fatigue'],before)
 def test_low_need_market_browsing_does_not_hoard_supplies(self):
  self.arrive('member-01','market');e=self.s.economy
  e.emit('needs','member-01',{'needs':{'hunger':0,'thirst':0,'fatigue':0,'curiosity':0}},remember=False)
  for _ in range(5):
   e.plan('member-01',{'kind':'use','target':'market'});e.native('member-01',0)
   self.s.engine.advance(8)
  self.assertEqual(self.own('member-01')['life']['purchases'],0)
  self.assertEqual(self.own('member-01')['wallet'],500)
  self.assertTrue(any(x['kind']=='venue_completed' and x['data']['venue']=='market' for x in self.s.engine.journal()['events']))
 def test_personal_desires_income_and_inventory_stay_private(self):
  self.arrive('member-01','park');self.assertTrue(self.act('shift',actor='member-01').accepted);self.s.engine.advance(20)
  self.s._ai('member-02','自由活動');view=self.backend.contexts[-1]
  self.assertNotIn('income',canonical(view['nearby']))
  self.assertFalse(any(e['kind']=='economy_job_completed' and e['actor']=='member-01' for e in view['memories']))
  self.assertEqual(view['economy']['income']['wages'],0)
  self.assertIsNone(self.s.screen()['economy']['market'])
  public=canonical(self.s.screen()['roster']);self.assertNotIn('wallet',public);self.assertNotIn('inventory',public)
 def test_load_old_branch_restores_money_goods_and_private_memory(self):
  self.arrive('player','market');self.s._save();before=self.s.auto_path.read_bytes();money=self.own()['wallet']
  self.assertTrue(self.act('buy_supply',{'item':'water'}).accepted);self.s.memory.sync(self.s.engine)
  self.assertEqual(self.own()['life']['inventory']['water'],1)
  self.s.auto_path.write_bytes(before);self.s._load_pixel(self.s.auto_path)
  self.assertEqual(self.own()['wallet'],money);self.assertNotIn('water',self.own()['life']['inventory'])
  self.assertFalse(any(e['kind']=='economy_supply' for e in self.s.memory.retrieve(self.s.engine,'player','飲用水',limit=20)))
 def test_ten_agents_earn_make_trade_and_consume_offscreen_without_model(self):
  for _ in range(220):
   for _ in range(40):self.s.space.animate()
   self.s._native_step()
  actors=[self.own(a) for a in self.s.engine.agent_ids()]
  self.assertTrue(all(a['life']['income']['wages']>=48 for a in actors))
  self.assertTrue(all(sum(a['life']['crafted'].values())>=1 for a in actors))
  self.assertGreater(sum(a['life']['purchases'] for a in actors),0)
  self.assertGreater(sum(a['life']['consumed'] for a in actors),0)
  self.assertGreater(sum(a['life']['income']['sales'] for a in actors),0)
  self.assertEqual(self.backend.contexts,[]);self.s.engine.assert_consistent()
  self.assertEqual(Engine.replay(self.s.engine.journal()).export_state(),self.s.engine.export_state())

if __name__=='__main__':unittest.main()
