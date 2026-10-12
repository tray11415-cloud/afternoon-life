import tempfile,unittest
from pathlib import Path
from unittest.mock import patch
from lifebox.pixel import PixelSession
from tests.test_play import FakeBackend

class SDIntegrationTests(unittest.TestCase):
 def setUp(self):
  root=Path(__file__).resolve().parents[2]/'work';root.mkdir(exist_ok=True);self.temp=tempfile.TemporaryDirectory(dir=root)
  self.patches=[patch('lifebox.character_art.CharacterStudio.discover',lambda s,extra=None:s.state()),patch('lifebox.character_art.CharacterStudio.probe',lambda s:s.state()),patch('lifebox.speech.SpeechStudio.refresh_windows',lambda s:s.state())]
  for p in self.patches:p.start()
  self.s=PixelSession(Path(self.temp.name),FakeBackend(),clock=lambda:100);self.s.studio.services[self.s.studio.config['url']]={'ready':True}
 def tearDown(self):
  self.s.close();self.s.studio.thread.join(2)
  for p in self.patches:p.stop()
  self.temp.cleanup()
 def test_general_cg_uses_selected_actor_worn_snapshot_and_public_scene(self):
  actor='member-01';npc=self.s.space.entities[actor];self.s.space.entities['player'].update(scene=npc['scene'],x=npc['x']+1,y=npc['y'])
  with patch.object(self.s.studio,'submit',return_value={'id':'fixture'}) as submit:
   result=self.s.act({'command':'cg','params':{'target':actor}})
  args=submit.call_args.args;self.assertEqual(args[0],actor);self.assertEqual(args[1],self.s.wardrobe.appearance(actor));self.assertEqual(args[3],'cg');self.assertEqual(set(args[4]),{'scene','place_name','description'});self.assertEqual(args[4]['scene'],npc['scene']);self.assertIn('當下穿著',result['notice']);self.assertEqual(self.s.backend.contexts,[])
 def test_general_cg_cannot_render_remote_actor(self):
  self.s.space.entities['player'].update(x=2,y=2)
  with patch.object(self.s.studio,'submit') as submit:result=self.s.act({'command':'cg','params':{'target':'member-01'}})
  submit.assert_not_called();self.assertIn('走近',result['notice'])
 def test_missing_lora_is_reported_without_consuming_llm(self):
  npc=self.s.space.entities['member-01'];self.s.space.entities['player'].update(scene=npc['scene'],x=npc['x']+1,y=npc['y'])
  result=self.s.act({'command':'cg','params':{'target':'member-01'}});self.assertIn('LoRA',result['notice']);self.assertEqual(self.s.backend.contexts,[]);self.assertEqual(len(self.s.studio.jobs),0)
if __name__=='__main__':unittest.main()
