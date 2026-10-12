import copy,json,unittest
from lifebox.engine import Engine
from lifebox.model import Action,canonical,digest
from lifebox.wardrobe import Wardrobe
import tests.test_economy as economy_tests

class WardrobeTests(unittest.TestCase):
 setUp=economy_tests.EconomyTests.setUp
 tearDown=economy_tests.EconomyTests.tearDown
 act=economy_tests.EconomyTests.act
 arrive=economy_tests.EconomyTests.arrive
 own=economy_tests.EconomyTests.own
 def buy(self,actor='member-01',item='cream-cardigan'):
  self.arrive(actor,'boutique');self.assertTrue(self.act('buy_clothes',{'item':item},actor).accepted)
 def change(self,actor='member-01',item='cream-cardigan'):
  self.arrive(actor,'room-01' if actor=='player' else 'room-'+actor[-2:],True)
  self.assertTrue(self.act('wear',{'item':item},actor).accepted);self.s.engine.advance()
 def test_curated_civitai_sources_are_prompt_only_and_reject_unsafe_records(self):
  items=self.s.wardrobe.catalog;self.assertEqual(len(items),6)
  for item in items.values():
   self.assertTrue(Wardrobe.valid_item(item));self.assertFalse(item['source']['nsfw'])
   self.assertTrue(item['source']['url'].startswith('https://civitai.com/models/'))
   self.assertFalse(item['source']['weights_downloaded']);self.assertIsNone(item['lora']['file'])
  bad=copy.deepcopy(next(iter(items.values())));bad['prompt']='transparent clothing, nude';self.assertFalse(Wardrobe.valid_item(bad))
  bad=copy.deepcopy(next(iter(items.values())));bad['source']['nsfw']=True;self.assertFalse(Wardrobe.valid_item(bad))
  bad=copy.deepcopy(next(iter(items.values())));bad['lora']['file']='unsafe-file';self.assertFalse(Wardrobe.valid_item(bad))
 def test_physical_shop_and_purchase_require_desk_not_spoken_claim(self):
  self.assertEqual(self.act('buy_clothes',{'item':'cream-cardigan'}).reason,'shop_too_far')
  self.arrive('player','boutique');before=self.own()['wallet']
  self.assertEqual(self.act('use',{'item':'cream-cardigan'}).reason,'use_buy_clothes')
  self.assertEqual(self.act('buy_clothes',{'item':'not-existing'}).reason,'unknown_clothes')
  self.assertEqual(self.own()['wallet'],before)
  self.assertTrue(self.act('buy_clothes',{'item':'cream-cardigan'}).accepted)
  self.assertEqual(self.own()['wallet'],before-64)
  self.assertEqual(self.s.wardrobe.appearance('player')['id'],'initial-player')
 def test_duplicate_commands_and_repeat_ownership_do_not_charge_twice(self):
  self.arrive('player','boutique');r=self.act('buy_clothes',{'item':'cream-cardigan'},request='buy-once')
  self.assertTrue(r.accepted);self.assertEqual(self.act('buy_clothes',{'item':'cream-cardigan'},request='buy-once'),r)
  self.assertEqual(self.act('buy_clothes',{'item':'cream-cardigan'}).reason,'already_owned')
  self.assertEqual(self.own()['wallet'],436);self.assertEqual(len(self.own()['wardrobe']['owned']),2)
  self.assertEqual(self.act('buy_clothes',{'item':'navy-blazer','price':1}).reason,'invalid_action_params')
 def test_insufficient_funds_keeps_wardrobe_and_wallet_unchanged(self):
  self.arrive('player','market')
  for _ in range(37):self.assertTrue(self.act('buy_supply',{'item':'materials'}).accepted)
  self.arrive('player','boutique');before=copy.deepcopy(self.own()['wardrobe'])
  self.assertEqual(self.act('buy_clothes',{'item':'cream-cardigan'}).reason,'insufficient_funds')
  self.assertEqual(self.own()['wallet'],56);self.assertEqual(self.own()['wardrobe'],before)
 def test_owned_only_home_only_and_busy_rules_apply_to_change(self):
  self.buy();self.assertEqual(self.act('wear',{'item':'navy-blazer'},actor='member-01').reason,'clothes_not_owned')
  self.assertEqual(self.act('wear',{'item':'cream-cardigan'},actor='member-01').reason,'change_at_home')
  self.arrive('member-01','room-02',True)
  self.assertEqual(self.act('wear',{'item':'cream-cardigan'},actor='member-01').reason,'change_at_home')
  self.arrive('member-01','room-01',True);self.assertTrue(self.act('craft',actor='member-01').accepted)
  self.assertEqual(self.act('wear',{'item':'cream-cardigan'},actor='member-01').reason,'actor_busy')
  self.s.engine.advance(12);self.assertTrue(self.act('wear',{'item':'cream-cardigan'},actor='member-01').accepted)
  self.assertEqual(self.s.wardrobe.appearance('member-01')['id'],'cream-cardigan')
 def test_clothes_stay_private_but_current_visible_outfit_is_public(self):
  self.buy();self.change();self.s._ai('member-02','自由活動');view=self.backend.contexts[-1]
  self.assertNotIn('cream-cardigan',canonical(view['wardrobe']['owned']))
  self.assertNotIn('wardrobe',view['self'])
  self.assertFalse(any(e['kind']=='wardrobe_bought' and e['actor']=='member-01' for e in view['memories']))
  self.arrive('player','room-01',True)
  public=next(e for e in self.s.screen()['space']['entities'] if e['id']=='member-01')
  self.assertEqual(public['outfit']['id'],'cream-cardigan')
  self.assertNotIn('owned',canonical(public));self.assertNotIn('prompt',canonical(public));self.assertNotIn('wallet',canonical(public))
 def test_save_replay_and_catalog_update_preserve_exact_owned_outfit(self):
  self.buy();self.change();before=self.s.wardrobe.appearance('member-01');journal=self.s.engine.journal()
  self.s._save();self.s.wardrobe.catalog['cream-cardigan']['prompt']='different catalog version'
  self.s._load_pixel(self.s.auto_path);self.assertEqual(self.s.wardrobe.appearance('member-01'),before)
  self.assertEqual(Engine.replay(journal).export_state(),self.s.engine.export_state())
  self.assertIn('cream crochet cardigan',self.s.wardrobe.render_prompt('member-01','park').prompt)
 def test_old_save_migration_is_once_and_does_not_change_money(self):
  before=self.s.engine.journal()['events'];wallet=self.own()['wallet']
  self.s.wardrobe.bind();self.s.wardrobe.bind()
  self.assertEqual(self.s.engine.journal()['events'],before);self.assertEqual(self.own()['wallet'],wallet)
  self.assertEqual(sum(e['kind']=='wardrobe_initialized' for e in before),1)
 def test_old_branch_cannot_recall_or_wear_future_purchase(self):
  self.arrive('member-01','boutique');self.s._save();before=self.s.auto_path.read_bytes()
  self.assertTrue(self.act('buy_clothes',{'item':'cream-cardigan'},actor='member-01').accepted)
  self.s.memory.sync(self.s.engine);self.s.auto_path.write_bytes(before);self.s._load_pixel(self.s.auto_path)
  self.assertNotIn('cream-cardigan',self.own('member-01')['wardrobe']['owned'])
  self.assertFalse(any(e['kind']=='wardrobe_bought' for e in self.s.memory.retrieve(self.s.engine,'member-01','奶油針織外套',limit=20)))
  self.assertEqual(self.act('wear',{'item':'cream-cardigan'},actor='member-01').reason,'clothes_not_owned')
 def test_cg_and_portrait_use_worn_clothes_keep_identity_and_have_no_inactive_lora(self):
  before=self.s.wardrobe.render_prompt('member-01','cafe');self.buy(item='navy-blazer');self.change(item='navy-blazer')
  after=self.s.wardrobe.render_prompt('member-01','cafe');portrait=self.s.wardrobe.render_prompt('member-01','room-01','portrait')
  self.assertIn('navy blazer',after.prompt);self.assertNotIn('terracotta jacket',after.prompt)
  self.assertIn('short brown hair',after.prompt);self.assertIn('cozy cafe',after.prompt)
  self.assertIn('full body standing portrait, plain background',portrait.prompt)
  self.assertNotEqual(digest(before.payload()),digest(after.payload()));self.assertNotIn('<lora:',after.prompt)
  self.assertEqual(before.seed,after.seed);self.assertIn('nudity',after.negative_prompt)
 def test_cg_submission_carries_snapshot_outfit_key(self):
  class Capture:
   def __init__(self):self.jobs=[]
   def submit(self,prompt,owner,scene):self.jobs.append((prompt,owner,scene));return 'test-job'
   def visible_jobs(self,viewer):return []
   def close(self,**kwargs):pass
  self.buy();self.change();self.arrive('player','room-01',True);self.s._approach('player','member-01')
  for _ in range(35):self.s.space.animate()
  self.s.engine.advance();self.assertTrue(self.s.space.near('player','member-01'))
  self.s.renderer=Capture();self.s.act({'command':'cg','params':{'target':'member-01'}})
  prompt,owner,scene=self.s.renderer.jobs[0]
  self.assertIn('cream crochet cardigan',prompt.prompt)
  self.assertEqual(scene['outfit'],self.s.wardrobe.appearance('member-01')['render_key']);self.assertEqual(owner,'player')
 def test_ten_agents_choose_buy_and_change_offscreen_without_paid_model(self):
  for _ in range(240):
   for _ in range(40):self.s.space.animate()
   self.s._native_step()
  actors=[self.own(a) for a in self.s.engine.agent_ids()]
  self.assertTrue(all(len(a['wardrobe']['owned'])>=2 for a in actors))
  self.assertTrue(all(not a['wardrobe']['wearing'].startswith('initial-') for a in actors))
  self.assertGreaterEqual(len({a['wardrobe']['wearing'] for a in actors}),3)
  self.assertTrue(all(a['life']['income']['wages']>=48 for a in actors))
  self.assertTrue(all(sum(a['wardrobe']['purchases'].values())<=1 for a in actors))
  self.assertEqual(self.backend.contexts,[]);self.s.engine.assert_consistent()
 def test_crowded_shop_portal_allows_opposite_journeys_without_overlap(self):
  self.arrive('member-01','boutique');self.arrive('member-02','boutique')
  self.s.space.entities['member-01'].update(x=14,y=19,path=[],destination=None)
  self.s.space.entities['member-02'].update(x=14,y=18,path=[],destination=None)
  for actor in ('member-01','member-02'):self.s.space.route_to(actor,'shared')
  for _ in range(15):
   for _ in range(45):
    self.s.space.animate()
    spots=[(e['scene'],e['x'],e['y']) for e in self.s.space.entities.values()]
    self.assertEqual(len(spots),len(set(spots)))
   self.s.engine.advance()
  self.assertEqual(self.s.space.entities['member-01']['scene'],'shared')
  self.assertEqual(self.s.space.entities['member-02']['scene'],'shared')

if __name__=='__main__':unittest.main()
