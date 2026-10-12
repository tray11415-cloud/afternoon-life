"""Replaceable PNG art, independent of the physical world and agent memory."""
import base64,copy,hashlib,io,json,os,re
from pathlib import Path
from .character_art import EXPRESSIONS,atomic
class ArtAssets:
 def __init__(self,root):
  self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.path=self.root/'settings.json';self.entries={}
  if self.path.is_file():
   try:self.entries=json.loads(self.path.read_text(encoding='utf-8'))
   except (ValueError,OSError):pass
 def state(self):return {'entries':copy.deepcopy(self.entries)}
 def upload(self,p,session):
  if set(p)!={'kind','target','expression','scope','frames','image','hide_decor'} or p['kind'] not in {'portrait','sprite','background'}:raise ValueError('無效美術替換')
  if p['scope'] not in {'all','outfit'} or type(p['hide_decor']) is not bool:raise ValueError('無效替換範圍')
  kind,target=p['kind'],p['target'];expression=p['expression']
  if kind=='background':
   if target not in session.map_spec['maps']:raise ValueError('未知場景')
  elif target not in session.engine._state['actors'] or expression not in EXPRESSIONS:raise ValueError('未知角色或表情')
  try:raw=base64.b64decode(p['image'],validate=True)
  except (ValueError,TypeError):raise ValueError('請使用 PNG 圖片')
  if len(raw)>3*1024*1024:raise ValueError('替換 PNG 需小於 3 MB')
  if not raw.startswith(b'\x89PNG\r\n\x1a\n'):raise ValueError('請使用有效 PNG 圖片')
  from PIL import Image
  try:
   with Image.open(io.BytesIO(raw)) as im:
    if im.format!='PNG' or max(im.size)>4096:raise ValueError('請使用 4096px 以內的 PNG')
    if kind=='sprite' and (p['frames'] not in (3,9) or im.size!=(64*p['frames'],256)):raise ValueError('行走圖需為四方向，64px 一格：192×256（3幀）或576×256（9幀）')
    if kind=='background':
     m=session.map_spec['maps'][target]
     if im.size!=(m['width']*32,m['height']*32):raise ValueError(f'這張地圖需為 {m["width"]*32}×{m["height"]*32}，碰撞和門口不變')
    if kind=='portrait' and min(im.size)<32:raise ValueError('立繪尺寸太小')
    image=im.convert('RGBA');buf=io.BytesIO();image.save(buf,format='PNG');raw=buf.getvalue()
  except (OSError, Image.DecompressionBombError):raise ValueError('PNG 已損壞或尺寸過大')
  key=hashlib.sha256(raw).hexdigest();file=self.root/(key+'.png');tmp=file.with_suffix('.tmp');tmp.write_bytes(raw);os.replace(tmp,file)
  outfit=session.wardrobe.appearance(target)['render_key'] if kind!='background' and p['scope']=='outfit' else '*'
  slot=kind+':'+target+':'+outfit+(':'+expression if kind=='portrait' else '')
  self.entries[slot]={'kind':kind,'target':target,'outfit':outfit,'expression':expression,'file':key+'.png','url':'/custom-art/'+key+'.png','frames':p['frames'],'hide_decor':p['hide_decor']};atomic(self.path,self.entries)
  return self.state()
 def remove(self,slot):
  if slot not in self.entries:raise ValueError('找不到替換素材')
  del self.entries[slot];atomic(self.path,self.entries);return self.state()
 def appearance(self,actor,outfit,expression='neutral'):
  result={}
  for scope in ('*',outfit['render_key']):
   sprite=self.entries.get('sprite:'+actor+':'+scope)
   portrait=self.entries.get('portrait:'+actor+':'+scope+':'+expression) or self.entries.get('portrait:'+actor+':'+scope+':neutral')
   if sprite:result.update(sprite=sprite['url'],frames=sprite['frames'])
   if portrait:result['portrait']=portrait['url']
  return result
 def backgrounds(self):return {v['target']:{'background':v['url'],'hide_decor':v['hide_decor']} for v in self.entries.values() if v['kind']=='background'}
 def asset(self,name):
  if not re.fullmatch(r'[a-f0-9]{64}\.png',name) or not any(e['file']==name for e in self.entries.values()):return None
  p=self.root/name;return p if p.is_file() else None
