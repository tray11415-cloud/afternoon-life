import json,sys,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'prototype'))
from lifebox.preferences import Preferences

class FirstLanguageTests(unittest.TestCase):
 def test_first_launch_english_without_creating_preferences(self):
  root=Path(__file__).parent/'first-language-check/new-player';root.mkdir(parents=True,exist_ok=True)
  self.assertFalse((root/'preferences.json').exists())
  self.assertEqual(Preferences(root).config['language'],'en')
  self.assertFalse((root/'preferences.json').exists())
 def test_all_existing_language_choices_retained_without_rewriting(self):
  for language in ('zh-TW','zh-CN','ja','en'):
   with self.subTest(language=language):
    root=Path(__file__).resolve().parents[1]/'work/first-language-check'/language;root.mkdir(parents=True,exist_ok=True)
    path=root/'preferences.json';path.write_text(json.dumps({'language':language}),encoding='utf-8');before=path.read_bytes()
    self.assertEqual(Preferences(root).config['language'],language)
    self.assertEqual(path.read_bytes(),before)

if __name__=='__main__':unittest.main()
