"""Small, per-world interface preferences; separate from voices and memories."""
import copy,json
from pathlib import Path
from .character_art import atomic

LANGUAGES={'zh-TW':'繁體中文','ja':'日本語','en':'English'}
class Preferences:
 def __init__(self,root):
  self.path=Path(root)/'preferences.json';self.config={'language':'zh-TW'}
  try:self.config=self.validate(json.loads(self.path.read_text(encoding='utf-8')))
  except (OSError,ValueError,TypeError):pass
 @staticmethod
 def validate(value):
  if not isinstance(value,dict) or set(value)!={'language'} or value['language'] not in LANGUAGES:raise ValueError('請選繁體中文、日本語或English')
  return copy.deepcopy(value)
 def configure(self,value):
  data=self.validate(value);atomic(self.path,data);self.config=data;return self.state()
 def state(self):return {'config':copy.deepcopy(self.config),'languages':LANGUAGES}
