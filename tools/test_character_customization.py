from pathlib import Path
import sys,copy,json,tempfile,unittest
from unittest.mock import patch
source=Path(__file__).parent/'character-customization/prototype'
if not source.exists():source=Path(__file__).resolve().parents[1]/'prototype'
sys.path.insert(0,str(source))
from lifebox.pixel import PixelSession
from lifebox.engine import Engine
from lifebox.characters import CharacterSetup,persona
from lifebox.character_art import CharacterStudio
from lifebox.speech import SpeechStudio
from lifebox.model import digest
from tests.test_play import FakeBackend

class CustomizationTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory(dir=Path(__file__).parent);self.root=Path(self.tmp.name);self.backend=FakeBackend()
  with patch.object(CharacterStudio,'discover',lambda x,extra=None:x.state()),patch.object(CharacterStudio,'probe',lambda x:x.state()),patch.object(SpeechStudio,'refresh_windows',lambda x:x.state()):self.s=PixelSession(self.root,self.backend,clock=lambda:100)
 def tearDown(self):self.s.close();self.tmp.cleanup()
 def edit(self,actor,**changes):
  p=self.s.character_setup.current(self.s,actor);before=digest(p);p.update(changes)
  return self.s.character_setup.prepare_current(self.s,actor,p,before)
 def test_all_eleven_and_male_player_default(self):
  v=self.s.character_setup.state(self.s);self.assertEqual(len(v['current']),11);self.assertEqual(v['profiles']['player']['gender'],'male');self.assertEqual(len(self.s.engine.agent_ids()),10)
 def test_preview_is_read_only(self):
  journal=self.s.engine.journal();templates=copy.deepcopy(self.s.character_setup.profiles);self.edit('player',name='海人',appearance='short black hair');self.assertEqual(journal,self.s.engine.journal());self.assertEqual(templates,self.s.character_setup.profiles)
 def test_live_player_preserves_progress_and_replays(self):
  old=self.s.engine.journal();own=copy.deepcopy(self.s.engine._state['actors']['player']);p=self.edit('player',name='海人',age=34,voice='喜歡安靜',background_enabled=True,background='只屬於男主的背景');self.s.components.apply(p['id']);a=self.s.engine.view('player')['self'];self.assertEqual(a['name'],'海人');self.assertEqual(a['age'],34)
  for f in ('wallet','inventory','relationships','busy_until','location'):self.assertEqual(self.s.engine._state['actors']['player'].get(f),own.get(f))
  now=self.s.engine.journal();self.assertEqual(now['genesis'],old['genesis']);self.assertEqual(now['events'][:len(old['events'])],old['events']);self.assertEqual(Engine.replay(now).view('player')['self'],a);self.assertEqual(self.backend.contexts,[])
 def test_heroine_voice_goal_and_private_background(self):
  progress=self.s.engine.view('member-01')['self']['goal']['progress'];p=self.edit('member-01',voice='說話短而直接。',goal='完成自己的畫作',background_enabled=True,background='唯一秘密：古董店經歷');self.s.components.apply(p['id']);self.assertEqual(persona(self.s.engine,'member-01'),'說話短而直接。');self.assertEqual(self.s.engine.view('member-01')['self']['goal']['title'],'完成自己的畫作');self.assertEqual(self.s.engine.view('member-01')['self']['goal']['progress'],progress)
  for a in ('player','member-02'):self.assertNotIn('唯一秘密',json.dumps(self.s.engine.view(a),ensure_ascii=False))
  self.assertNotIn('唯一秘密',json.dumps(self.s.screen(),ensure_ascii=False))
 def test_disabled_background_not_applied(self):
  p=self.edit('member-02',background_enabled=False,background='沒有啟用的草稿');self.s.components.apply(p['id']);self.assertEqual(self.s.character_setup.current(self.s,'member-02')['background'],'')
 def test_stale_profile_and_changed_preview_rejected(self):
  original=self.s.character_setup.current(self.s,'player');p=self.edit('player',name='甲');other=self.edit('player',name='乙');self.s.components.apply(other['id'])
  with self.assertRaises(ValueError):self.s.character_setup.prepare_current(self.s,'player',original,digest(original))
  with self.assertRaises(ValueError):self.s.components.apply(p['id'])
 def test_rollback_restores_original_person(self):
  old=self.s.character_setup.current(self.s,'member-01');p=self.edit('member-01',name='新名字',appearance='blue eyes',voice='新的語氣',background_enabled=True,background='新背景');self.s.components.apply(p['id']);undo=self.s.components.rollback(p['id']);self.s.components.apply(undo['id']);self.assertEqual(self.s.character_setup.current(self.s,'member-01'),old)
 def test_old_ten_person_template_migrates_without_losing_story(self):
  v=copy.deepcopy(self.s.character_setup.profiles);v.pop('player')
  for p in v.values():p.pop('gender');p.pop('appearance')
  v['member-01'].update(background_enabled=True,background='舊模板故事');self.s.character_setup.path.write_text(json.dumps({'version':1,'profiles':v}),encoding='utf-8');loaded=CharacterSetup(self.root);self.assertEqual(loaded.profiles['member-01']['background'],'舊模板故事');self.assertIn('player',loaded.profiles)
 def test_new_templates_and_archive_restore_have_distinct_people(self):
  old=self.s.engine.journal();v=copy.deepcopy(self.s.character_setup.profiles);v['player'].update(name='新男主',age=40,background_enabled=True,background='新男主故事');v['member-01']['name']='新女主';self.s.character_setup.configure(v);self.s.act({'command':'create_cast','params':{}});self.assertEqual(self.s.screen()['player']['name'],'新男主');self.assertEqual(self.s.engine.view('member-01')['self']['name'],'新女主')
  archive=self.s.character_setup.state()['archives'][0]['id'];self.s.act({'command':'restore_cast','params':{'archive':archive}});self.assertEqual(self.s.engine.journal(),old)
  theme=self.s.components.get('theme:interface');theme['accent']='#112233';q=self.s.components.prepare({'instruction':'換顏色','changes':[{'target':'theme:interface','value':theme}]});self.s.components.apply(q['id']);self.assertEqual(self.s.engine.view('player')['self']['name'],old['genesis']['actors'][-1]['name'])
 def test_saved_live_profile_survives_reload(self):
  p=self.edit('player',name='存檔人物',appearance='silver hair');self.s.components.apply(p['id']);self.s._save();self.s._load_pixel(self.s.auto_path);self.assertEqual(self.s.screen()['player']['name'],'存檔人物');self.assertEqual(self.s.studio.actor_identities['player'],{'age':25,'appearance':'silver hair'})
 def test_adult_duplicate_and_bad_appearance_rejected(self):
  for changes in ({'age':17},{'name':'曉晴'},{'appearance':'a'*1001},{'gender':'invalid'}):
   with self.assertRaises(ValueError):self.edit('player',**changes)

if __name__=='__main__':unittest.main()
