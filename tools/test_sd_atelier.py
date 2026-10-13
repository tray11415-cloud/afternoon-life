from pathlib import Path
import sys,copy,json,tempfile,unittest,threading,urllib.request,urllib.error
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'prototype'))
from lifebox.pixel import PixelSession
from lifebox.character_art import CharacterStudio
from lifebox.speech import SpeechStudio
from lifebox.demo_backend import DemoBackend
from lifebox.art_atelier import ArtAtelier
from lifebox.play import make_server
from PIL import Image

class SDAtelierTests(unittest.TestCase):
 def setUp(self):
  self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name)
  with patch.object(CharacterStudio,'discover',lambda s,extra=None:s.state()),patch.object(CharacterStudio,'probe',lambda s:s.state()),patch.object(SpeechStudio,'refresh_windows',lambda s:s.state()):self.s=PixelSession(self.root,DemoBackend(),clock=lambda:100)
 def tearDown(self):self.s.close();self.s.studio.thread.join(2);self.temp.cleanup()
 def call(self,command,**params):return self.s.art_action({'operation':'atelier','params':{'command':command,**params}})
 def job(self,kind='portrait',actor='player'):
  outfit=self.s.wardrobe.appearance(actor);ident=('1' if actor=='player' else '2')*64;file=ident+('-cg.png' if kind=='cg' else '-sprite.png' if kind=='pixel' else '-portrait-neutral.png');Image.new('RGBA',(192,256) if kind=='pixel' else (96,128),'green').save(self.s.studio.assets/file)
  files={'cg':file} if kind=='cg' else {'sprite':file} if kind=='pixel' else {'portraits':{'neutral':file}}
  j={'id':ident,'actor':actor,'kind':kind,'outfit':outfit,'scene':{'scene':'shared','place_name':'Courtyard','description':'an art illustration'} if kind=='cg' else None,'status':'ready','done':1,'total':1,'message':'mock SD fixture','files':files,'recipe':{'gender':'male' if actor=='player' else 'female'}};self.s.studio.jobs[ident]=j;return j
 def test_state_read_only_and_public_cg_places(self):
  old=self.s.engine.journal();config=copy.deepcopy(self.s.studio.config);data=self.call('state');self.assertIn('player',data['atelier']['bindings']);self.assertNotIn('room-01',data['atelier']['public_scenes']);self.assertEqual(old,self.s.engine.journal());self.assertEqual(config,self.s.studio.config)
 def test_cg_creation_uses_actor_worn_snapshot_not_events(self):
  old=self.s.engine.journal();outfit=self.s.wardrobe.appearance('member-03');seen=[]
  def submit(actor,worn,prompt,kind,scene,**kwargs):
   seen.append((actor,worn,kind,scene));j=self.job('cg',actor);return j
  with patch.object(self.s.studio,'submit',submit):self.call('generate',actor='member-03',kind='cg',scene='park',description='quiet afternoon')
  self.assertEqual(seen[0][0],'member-03');self.assertEqual(seen[0][1],outfit);self.assertEqual(seen[0][3]['scene'],'park');self.assertEqual(self.s.engine.journal(),old);self.assertEqual(self.s.backend.stats()['calls'],0)
 def test_private_place_and_explicit_cg_rejected(self):
  with patch.object(self.s.studio,'submit') as submit:
   for scene,desc in [('room-01','quiet afternoon'),('park','nude')]:
    with self.assertRaises(ValueError):self.call('generate',actor='player',kind='cg',scene=scene,description=desc)
   submit.assert_not_called()
 def test_apply_cg_persists_selection_without_world_events(self):
  j=self.job('cg');old=self.s.engine.journal();self.call('apply',actor='player',id=j['id'],expression='neutral');selected=self.s.screen()['cg']['selected'];self.assertEqual(selected['job_id'],j['id']);self.assertEqual(ArtAtelier(self.s).selected_cg(),selected);self.assertEqual(old,self.s.engine.journal())
 def test_apply_sd_prioritizes_over_import_without_deleting_it(self):
  j=self.job();outfit=self.s.wardrobe.appearance('player');old=self.s.engine.journal()
  with patch.object(self.s.art_assets,'appearance',return_value={'portrait':'/art-assets/import.png'}):
   self.call('apply',actor='player',id=j['id'],expression='neutral');player=next(e for e in self.s.screen()['space']['entities'] if e['id']=='player');self.assertTrue(player['art']['portrait'].startswith('/character-art/'));self.call('restore',actor='player');player=next(e for e in self.s.screen()['space']['entities'] if e['id']=='player');self.assertEqual(player['art']['portrait'],'/art-assets/import.png')
  self.assertEqual(old,self.s.engine.journal());self.assertTrue((self.s.studio.assets/j['files']['portraits']['neutral']).exists())
 def test_cannot_apply_another_actor_unfinished_or_wrong_outfit(self):
  j=self.job(actor='member-01')
  with self.assertRaises(ValueError):self.call('apply',actor='player',id=j['id'],expression='neutral')
  j['status']='running'
  with self.assertRaises(ValueError):self.call('apply',actor='member-01',id=j['id'],expression='neutral')
  j['status']='ready';j['outfit']={**j['outfit'],'render_key':'old-outfit'}
  with self.assertRaises(ValueError):self.call('apply',actor='member-01',id=j['id'],expression='neutral')
 def test_stale_binding_and_unknown_fields_rejected(self):
  p=copy.deepcopy(self.call('state')['config']['profiles']['player'])
  with self.assertRaises(ValueError):self.call('binding',actor='player',profile=p,before='old')
  with self.assertRaises(ValueError):self.call('state',api_key='invalid')
  with self.assertRaises(ValueError):self.call('generate',actor='npc-cafe',kind='portrait',scene=None,description='')
 def test_binding_only_updates_selected_actor_and_disables_new_auto(self):
  self.s.studio.folders=[{'id':'fixture','backend':'a1111','path':str(self.root)}];self.s.studio.config.update(installation='fixture',backend='a1111')
  path=self.root/'local-lora.safetensors';path.write_bytes(b'fixture');self.s.studio.resources={'local':{'id':'local','category':'lora','name':path.name,'path':str(path),'selectable':True,'installations':['fixture'],'base':'sdxl'}}
  state=self.call('state');p=copy.deepcopy(state['config']['profiles']['player']);p['lora']='local';self.call('binding',actor='player',profile=p,before=state['atelier']['bindings']['player']);self.assertEqual(set(self.s.studio.config['profiles']),{'player'});self.assertFalse(self.s.studio.config['profiles']['player']['auto']);self.assertEqual(self.s.studio.jobs,{})
 def test_partial_new_identity_does_not_reactivate_old_sprite(self):
  pixel=self.job('pixel');self.s.studio.jobs.pop(pixel['id']);pixel['id']='4'*64;pixel['recipe']['profile']={'identity':'old identity'};self.s.studio.jobs[pixel['id']]=pixel;self.call('apply',actor='player',id=pixel['id'],expression='neutral')
  portrait=self.job('portrait');portrait['recipe']['profile']={'identity':'new identity'};self.call('apply',actor='player',id=portrait['id'],expression='neutral');active=self.s.studio.config['active'][self.s.art_atelier.scope('player')];self.assertNotIn('sprite',active);self.assertIn('portraits',active);self.assertTrue((self.s.studio.assets/pixel['files']['sprite']).is_file())
 def test_partial_matching_identity_keeps_sprite_and_portrait(self):
  pixel=self.job('pixel');self.s.studio.jobs.pop(pixel['id']);pixel['id']='5'*64;self.s.studio.jobs[pixel['id']]=pixel;self.call('apply',actor='player',id=pixel['id'],expression='neutral')
  portrait=self.job('portrait');self.call('apply',actor='player',id=portrait['id'],expression='neutral');active=self.s.studio.config['active'][self.s.art_atelier.scope('player')];self.assertEqual(active['sprite'],pixel['files']['sprite']);self.assertEqual(active['portraits'],portrait['files']['portraits'])
 def test_http_guard_and_new_script(self):
  server=make_server(self.s,0);threading.Thread(target=server.serve_forever,daemon=True).start();base=f'http://127.0.0.1:{server.server_port}'
  def req(path,body=None,token='',origin=None):
   headers={'X-Play-Token':token};raw=None
   if body is not None:headers.update({'Origin':origin or base,'Content-Type':'application/json'});raw=json.dumps(body).encode()
   with urllib.request.urlopen(urllib.request.Request(base+path,raw,headers),timeout=10) as r:return r.read()
  try:
   token=json.loads(req('/api/state'))['token'];body={'operation':'atelier','params':{'command':'state'}}
   for auth,origin in [('',base),(token,'https://evil.example')]:
    with self.assertRaises(urllib.error.HTTPError) as e:req('/api/art',body,auth,origin)
    self.assertEqual(e.exception.code,403)
   self.assertIn('atelier',json.loads(req('/api/art',body,token)));self.assertTrue(req('/atelier.js'))
  finally:server.shutdown();server.server_close()

if __name__=='__main__':unittest.main()
