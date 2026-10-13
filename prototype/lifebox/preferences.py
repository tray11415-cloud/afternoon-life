"""Small, per-world interface preferences; separate from voices and memories."""
import copy,json
from pathlib import Path
from .character_art import atomic

LANGUAGES={'zh-TW':'繁體中文','zh-CN':'简体中文','ja':'日本語','en':'English'}
DEFAULT={'language':'en','camera_zoom':1.0,'show_names':True,'show_minimap':True,'reduce_motion':False,'large_text':False,'pause_in_settings':True}
class Preferences:
 def __init__(self,root):
  self.path=Path(root)/'preferences.json';self.config=copy.deepcopy(DEFAULT)
  try:self.config=self.validate(json.loads(self.path.read_text(encoding='utf-8')))
  except (OSError,ValueError,TypeError):pass
 @staticmethod
 def validate(value):
  if not isinstance(value,dict) or 'language' not in value or set(value)-set(DEFAULT) or not isinstance(value['language'],str) or value['language'] not in LANGUAGES:raise ValueError('請選繁體中文、简体中文、日本語或English')
  result={**DEFAULT,**value}
  if type(result['camera_zoom']) not in (int,float) or not .75<=result['camera_zoom']<=1.5:raise ValueError('視野縮放需為0.75–1.5')
  for key in ('show_names','show_minimap','reduce_motion','large_text','pause_in_settings'):
   if type(result[key]) is not bool:raise ValueError('遊戲開關需為布林值')
  return copy.deepcopy(result)
 def configure(self,value):
  if not isinstance(value,dict):raise ValueError('無效遊戲設定')
  data=self.validate({**self.config,**value});atomic(self.path,data);self.config=data;return self.state()
 def state(self):return {'config':copy.deepcopy(self.config),'languages':LANGUAGES}
