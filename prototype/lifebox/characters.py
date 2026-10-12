"""Optional authored backstories are creation inputs, not shared world facts."""
import copy,json,os,secrets,shutil
from pathlib import Path
from .play import PEOPLE,VOICES,GOALS,play_world
from .model import digest

PRIVATE_FIELDS=('voice','goal','background_enabled','background','appearance')

def default_profile(actor,identity=None):
 p=PEOPLE.get(actor,{'name':'玩家','age':25,'profile':'由玩家親自決定言行。'})
 v={'name':p['name'],'age':p['age'],'gender':'male' if actor=='player' else 'female','voice':p['profile'],'goal':GOALS[list(PEOPLE).index(actor)] if actor in PEOPLE else '在共居生活中找到自己的日常','background_enabled':False,'background':'','appearance':''}
 if identity:v.update({k:identity[k] for k in ('name','age','gender') if k in identity})
 return v

def validate_profile(p):
 if not isinstance(p,dict) or not {'name','age','voice','goal','background_enabled','background'}<=set(p) or set(p)-{'name','age','voice','goal','background_enabled','background','gender','appearance'}:raise ValueError('人物設定欄位不完整')
 for field,limit in (('name',32),('voice',500),('goal',100),('background',2000)):
  if not isinstance(p[field],str) or len(p[field])>limit or (field in ('name','voice','goal') and not p[field].strip()):raise ValueError('人物名稱／語氣／目標／背景長度不合適')
 if type(p['age']) is not int or not 18<=p['age']<=120 or type(p['background_enabled']) is not bool:raise ValueError('所有人物必須為成年人；背景為可選項')
 if p.get('gender','female') not in {'male','female'}:raise ValueError('請選男性或女性')
 if not isinstance(p.get('appearance',''),str) or len(p.get('appearance',''))>1000:raise ValueError('外觀描述最多1000字')
 return copy.deepcopy(p)

def validate_profiles(profiles):
 if not isinstance(profiles,dict) or set(profiles) not in (set(PEOPLE),set(PEOPLE)|{'player'}):raise ValueError('需保留玩家與十位成年角色的獨立欄位')
 for p in profiles.values():validate_profile(p)
 if len({p['name'].strip() for p in profiles.values()})!=len(profiles):raise ValueError('人物名稱需不同，方便區分邀約與對話')
 return copy.deepcopy(profiles)

def apply_character(state,event):
 if event['kind']!='character_profile_created':raise ValueError('unknown character event')
 p=validate_profile(event['data'])
 # Public identity is name/age only. Background belongs to the actor's self view.
 state['actors'][event['actor']]['character_profile']=p
 a=state['actors'][event['actor']]
 a.update(name=p['name'].strip(),age=p['age'],gender=p.get('gender','male' if event['actor']=='player' else 'female'))
 a['goal']['title']=p['goal'].strip()

def apply_customization(state,event):
 a=state['actors'][event['actor']];data=copy.deepcopy(event['data'])
 private=data.pop('character_profile',None)
 a.update(data)
 if private is not None:
  p=validate_profile({**{k:a[k] for k in ('name','age','gender')},**private})
  if not p['background_enabled']:p['background']=''
  a['character_profile']=p;a['goal']['title']=p['goal'].strip()
 elif a.get('character_profile'):
  a['character_profile'].update({k:a[k] for k in ('name','age','gender')})

class CharacterSetup:
 def __init__(self,root):
  self.path=Path(root)/'character-templates.json'
  defaults={a:default_profile(a) for a in ('player',*PEOPLE)}
  self.profiles=defaults
  if self.path.exists():
   try:
    loaded=validate_profiles(json.loads(self.path.read_text(encoding='utf-8'))['profiles'])
    self.profiles={a:{**defaults[a],**loaded.get(a,{})} for a in defaults}
   except (OSError,ValueError,KeyError,TypeError):pass
 def state(self,session=None):
  archive_root=self.path.parent/'archives';archives=[]
  if archive_root.is_dir():
   archives=[{'id':p.name,'label':f'原存檔 {i+1}'} for i,p in enumerate(sorted(archive_root.glob('before-creation-*'),key=lambda p:p.stat().st_mtime)) if (p/'pixel-autosave.json').is_file()]
  result={'profiles':copy.deepcopy(self.profiles),'background_optional':True,'archives':archives,'applies':'保存模板只影響新存檔；目前人物可另外預覽並套用，保留舊記憶與進度。'}
  if session:
   with session.lock:
    result['current']={a:self.current(session,a) for a in self.profiles}
    result['fingerprints']={a:digest(p) for a,p in result['current'].items()}
  return result
 def current(self,session,actor):
  if actor not in self.profiles:raise ValueError('請選玩家或共居角色')
  a=session.engine._state['actors'][actor]
  return {**default_profile(actor,a),**a.get('character_profile',{}),**{k:a[k] for k in ('name','age','gender')},'goal':a['goal']['title'] or default_profile(actor)['goal']}
 def prepare_current(self,session,actor,profile,before):
  with session.lock:
   current=self.current(session,actor)
   if before!=digest(current):raise ValueError('這位人物的設定已改變，請重新開啟人物設定')
   p={**default_profile(actor),**validate_profile(profile)}
   if any(a!=actor and self.current(session,a)['name'].strip()==p['name'].strip() for a in self.profiles):raise ValueError('人物名稱需不同')
   if not p['background_enabled']:p['background']=''
   value={k:p[k] for k in ('name','age','gender')};value['character_profile']={k:p[k] for k in PRIVATE_FIELDS}
   return session.components.prepare({'instruction':'人物設定：'+p['name'],'changes':[{'target':'actor:'+actor,'value':value}]})
 def configure(self,profiles):
  data=validate_profiles(profiles);data={a:{**default_profile(a),**data.get(a,{})} for a in self.profiles};tmp=self.path.with_suffix('.tmp');tmp.write_text(json.dumps({'version':2,'profiles':data},ensure_ascii=False,indent=2),encoding='utf-8');os.replace(tmp,self.path);self.profiles=data;return self.state()
 def world(self):
  world=play_world()
  for a in world['actors']:
   if a['id'] in self.profiles:
    p=self.profiles[a['id']];a.update(name=p['name'].strip(),age=p['age']);a['goal']['title']=p['goal'].strip()
  return world
 def initialize(self,engine):
  for a,p in self.profiles.items():
   p=copy.deepcopy(p)
   if not p['background_enabled']:p['background']=''
   engine._emit('character_profile_created',a,p,[a],remember=False)
  engine.assert_consistent()
 def archive_current(self,session):
  session._save();archive=session.root/'archives'/('before-creation-'+secrets.token_hex(8));archive.mkdir(parents=True)
  for path in (session.auto_path,session.manual_path):
   if path.is_file():shutil.copy2(path,archive/path.name)
  return archive.name

def persona(engine,actor):
 own=engine.view(actor,memory_limit=1)['self'];p=own.get('character_profile')
 return p['voice'] if p else PEOPLE[actor]['profile']

def public_identity(engine,actor):
 a=engine._state['actors'][actor]
 return {'id':actor,'name':a['name'],'age':a['age'],'profile':a.get('character_profile',{}).get('voice',PEOPLE.get(actor,{}).get('profile',''))}
