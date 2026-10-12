import copy,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from lifebox.pixel import PixelSession
from lifebox.engine import Engine
from lifebox.model import Action
from lifebox.characters import validate_profiles,persona
from tests.test_play import FakeBackend

class SocialCharacterTests(unittest.TestCase):
 def setUp(self):
  root=Path(__file__).resolve().parents[2]/'work';root.mkdir(exist_ok=True)
  self.temp=tempfile.TemporaryDirectory(dir=root);self.backend=FakeBackend()
  self.patches=[patch('lifebox.character_art.CharacterStudio.discover',lambda self,extra=None:self.state()),patch('lifebox.character_art.CharacterStudio.probe',lambda self:self.state())]
  for p in self.patches:p.start()
  self.s=PixelSession(Path(self.temp.name),self.backend,clock=lambda:100.0)
 def tearDown(self):
  self.s.close();self.s.studio.thread.join(2)
  for p in self.patches:p.stop()
  self.temp.cleanup()
 def do(self,actor,kind,**p):return self.s._do(actor,Action(kind,p))
 def plan(self,venue='park',item='',participants=None,start=None):
  result=self.do('player','group_create',venue=venue,item=item,title='午後同遊',participants=participants or ['member-01','member-02'],start=start or self.s.engine.tick+5,duration=5)
  self.assertTrue(result.accepted,result.reason);return list(self.s.social.groups().values())[-1]
 def accept(self,g,actor):
  result=self.do(actor,'group_respond',group=g['id'],accept=True);self.assertTrue(result.accepted,result.reason)
 def place(self,g,actor):
  e=self.s.space.entities[actor];self.s.engine._emit('actor_moved',actor,{'from':e['scene'],'to':g['venue']},[actor]);e.update(scene=g['venue'],x=g['spots'][actor]['x'],y=g['spots'][actor]['y'],path=[],destination=None)
 def start(self,g,who=('player','member-01','member-02')):
  for a in who:
   if a!='player':self.accept(g,a)
   self.place(g,a)
  self.s.engine.advance(g['start']-self.s.engine.tick)
  self.assertEqual(g['status'],'active')
 def test_no_forced_consent_or_paid_calls(self):
  g=self.plan();self.assertEqual(g['responses']['member-01'],'pending');self.assertEqual(self.backend.contexts,[])
  r=self.do('member-01','group_respond',group=g['id'],accept=False);self.assertTrue(r.accepted);self.assertEqual(g['responses']['member-01'],'declined')
 def test_invalid_members_leave_no_partial_event(self):
  r=self.do('player','group_create',venue='park',item='',title='t',participants=['member-01','member-01'],start=5,duration=5);self.assertFalse(r.accepted);self.assertEqual(self.s.social.groups(),{})
 def test_group_reserves_each_individual_time(self):
  g=self.plan();self.accept(g,'member-01');second=self.do('member-01','group_create',venue='cafe',item='',title='conflict',participants=['member-03'],start=6,duration=5);self.assertFalse(second.accepted);self.assertEqual(second.reason,'commitment_conflict')
 def test_invitation_alone_is_not_attendance(self):
  g=self.plan();self.accept(g,'member-01');self.s.engine.advance(15);self.assertEqual(g['status'],'missed');self.assertFalse(any(e['kind']=='group_started' for e in self.s.engine.journal()['events']))
 def test_start_requires_host_and_two_physical_arrivals(self):
  g=self.plan();self.accept(g,'member-01');self.accept(g,'member-02');self.place(g,'member-01');self.place(g,'member-02');self.s.engine.advance(5);self.assertEqual(g['status'],'planned');self.place(g,'player');self.s.engine.advance();self.assertEqual(g['status'],'active');self.assertEqual(len(g['attendees']),3)
 def test_paid_activity_each_pays_once_and_gets_own_knowledge(self):
  row=self.s.facilities.items('cafe')[0];g=self.plan('cafe',row['id']);wallets={a:self.s.engine.view(a)['self'].get('wallet',500) for a in g['members']};self.start(g)
  for a in g['attendees']:self.assertEqual(self.s.engine.view(a)['self']['wallet'],wallets[a]-row['price'])
  self.s.engine.advance(row['minutes']);self.assertEqual(g['status'],'completed')
  for a in g['attendees']:self.assertTrue(any(e['kind']=='venue_completed' for e in self.s.engine.view(a)['memories']))
  self.assertFalse(any(e['kind']=='venue_completed' for e in self.s.engine.view('member-03')['memories']))
 def test_unaffordable_invitation_can_be_declined(self):
  row=self.s.facilities.items('cafe')[0];g=self.plan('cafe',row['id']);self.s.engine._state['actors']['member-01']['wallet']=0;r=self.do('member-01','group_respond',group=g['id'],accept=True);self.assertFalse(r.accepted);self.assertEqual(g['responses']['member-01'],'pending')
 def test_absent_member_has_no_group_chat_or_relationship(self):
  g=self.plan();self.start(g,('player','member-01'));r=self.do('player','group_say',group=g['id'],text='只有真正到場的人聽到');self.assertTrue(r.accepted)
  self.assertNotIn('只有真正到場的人聽到',json.dumps(self.s.engine.view('member-02'),ensure_ascii=False))
  self.assertEqual(self.s.social.browse('member-02')['groups'][0]['messages'],[])
  self.assertNotIn('player',self.s.engine.view('member-02')['relationships'])
 def test_early_departure_has_no_completion_reward(self):
  g=self.plan();self.start(g);self.do('member-01','group_leave',group=g['id']);self.s.engine.advance(5);self.assertEqual(g['responses']['member-01'],'left');self.assertIsNone(self.s.engine.view('member-01')['self']['group_id'])
 def test_cancel_before_start_does_not_charge(self):
  row=self.s.facilities.items('cafe')[0];g=self.plan('cafe',row['id']);before=self.s.engine.view('player')['self']['wallet'];self.do('player','group_cancel',group=g['id']);self.assertEqual(g['status'],'cancelled');self.assertEqual(self.s.engine.view('player')['self']['wallet'],before)
 def test_group_journal_replay_preserves_attendance_messages_and_cost(self):
  g=self.plan();self.start(g);self.do('player','group_say',group=g['id'],text='今天很舒服');replayed=Engine.replay(self.s.engine.journal());self.assertEqual(replayed.export_state(),self.s.engine.export_state());replayed.assert_consistent()
 def test_one_actor_per_group_model_context(self):
  profiles=copy.deepcopy(self.s.character_setup.profiles)
  for actor,story in [('member-01','甲的私有往事'),('member-02','乙的私有往事')]:profiles[actor].update(background_enabled=True,background=story)
  self.s.character_setup.configure(profiles);self.s.character_setup.initialize(self.s.engine);g=self.plan();self.start(g)
  self.backend.action=Action('say',{'target':'player','text':'我自己的回覆'})
  self.s._group_ai(g['id'],'member-01');self.s._group_ai(g['id'],'member-02')
  self.assertEqual(len(self.backend.contexts),2)
  for context,own,other in [(self.backend.contexts[0],'甲的私有往事','乙的私有往事'),(self.backend.contexts[1],'乙的私有往事','甲的私有往事')]:
   text=json.dumps(context,ensure_ascii=False);self.assertIn(own,text);self.assertNotIn(other,text)
  self.assertEqual(len(g['messages']),2)
 def test_background_defaults_off_and_draft_does_not_rewrite_current_world(self):
  self.assertTrue(all(not p['background_enabled'] for p in self.s.character_setup.profiles.values()));before=self.s.engine.journal();p=copy.deepcopy(self.s.character_setup.profiles);p['member-01'].update(background_enabled=True,background='曾在書店工作');self.s.character_setup.configure(p);self.assertEqual(self.s.engine.journal(),before)
 def test_background_only_enters_own_context_at_creation(self):
  p=copy.deepcopy(self.s.character_setup.profiles);p['member-01'].update(background_enabled=True,background='只屬於曉晴的背景');p['member-02'].update(background_enabled=False,background='沒有啟用的背景');self.s.character_setup.configure(p)
  self.s.act({'command':'create_cast','params':{}})
  self.assertIn('只屬於曉晴的背景',json.dumps(self.s.engine.view('member-01'),ensure_ascii=False));self.assertNotIn('只屬於曉晴的背景',json.dumps(self.s.engine.view('member-02'),ensure_ascii=False));self.assertNotIn('只屬於曉晴的背景',json.dumps(self.s.screen(),ensure_ascii=False));self.assertNotIn('沒有啟用的背景',json.dumps(self.s.engine.view('member-02'),ensure_ascii=False))
 def test_creation_preserves_and_restores_previous_save(self):
  before=self.s.engine.journal();self.s.act({'command':'create_cast','params':{}});archives=self.s.character_setup.state()['archives'];self.assertEqual(len(archives),1);self.s.act({'command':'restore_cast','params':{'archive':archives[0]['id']}});self.assertEqual(self.s.engine.journal(),before);self.assertEqual(len(self.s.character_setup.state()['archives']),2)
 def test_character_adult_and_unique_identity_validation(self):
  p=copy.deepcopy(self.s.character_setup.profiles);p['member-01']['age']=17
  with self.assertRaises(ValueError):validate_profiles(p)
  p=copy.deepcopy(self.s.character_setup.profiles);p['member-01']['name']=p['member-02']['name']
  with self.assertRaises(ValueError):validate_profiles(p)
 def test_group_chat_model_routing(self):
  from lifebox.xai import DIALOGUE_TRIGGERS
  self.assertIn('共同活動交談',DIALOGUE_TRIGGERS)
 def test_archive_path_traversal_rejected(self):
  with self.assertRaises(ValueError):self.s.act({'command':'restore_cast','params':{'archive':'../../private'}})

if __name__=='__main__':unittest.main()
