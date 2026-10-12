"""Open classical texts from Wikisource when Gutenberg format downloads fail."""
import json,re
from urllib.parse import quote
from sync_venues import fetch,batch,ROOT,Page
from html.parser import HTMLParser
class MainText(HTMLParser):
 def __init__(self,html):
  super().__init__();self.active=0;self.depth=0;self.skip=0;self.parts=[];self.feed(html)
 def handle_starttag(self,tag,attrs):
  a=dict(attrs)
  if tag=='div':
   self.depth+=1
   if not self.active and 'mw-parser-output' in a.get('class',''):self.active=self.depth
  if tag in ('script','style'):self.skip+=1
 def handle_endtag(self,tag):
  if tag in ('script','style'):self.skip=max(0,self.skip-1)
  if tag=='div':
   if self.depth==self.active:self.active=0
   self.depth-=1
 def handle_data(self,data):
  if self.active and not self.skip and data.strip():self.parts.append(data.strip())
def run():
 file=ROOT/'prototype/data/venues.json';data=json.loads(file.read_text(encoding='utf-8'));v=data['venues']['library']
 selected={'長恨歌':'長恨歌','紅樓夢':'紅樓夢/第001回','論語':'論語/學而','道德經':'道德經_(王弼本)','山海經':'山海經/南山經','西遊記':'西遊記/第001回','三國演義':'三國演義/第001回','詩經':'詩經/國風/周南','聊齋誌異':'聊齋志異/卷一'}
 urls={title:'https://zh.wikisource.org/wiki/'+quote(path,safe='/') for title,path in selected.items()}
 pages={p['url']:p for p in batch(urls.values())}
 for book in v['items']:
  title=book['title'];p=pages.get(urls.get(title))
  if not p:continue
  text='\n'.join(MainText(p['html']).parts)
  marker={'山海經':r'南山經之首曰','紅樓夢':r'作者自云','西遊記':r'詩曰：','長恨歌':r'漢\s*皇','道德經':r'道可道'}.get(title)
  if marker:
   start=re.search(marker,text)
   if start:text=text[start.start():]
  text=re.split(r'此作品在全世界都属于|此作品在全世界都屬於',text,maxsplit=1)[0]
  # Navigation and edit UI are not instructions; preserve scope of the actual text.
  if len(text)>100:
   book.update(text=text[:250000],text_url=p['url'],coverage='維基文庫公開原文：'+selected[title]+'；每次讀一段',text_scope=selected[title],text_license='古典原文公有領域；維基文庫編輯內容 CC BY-SA')
 v['items'].sort(key=lambda b:(not bool(b.get('text')),b['title']))
 file.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
 print(json.dumps({'readable':[(b['title'],len(b.get('text','')),b.get('text_scope')) for b in v['items'] if b.get('text')],'zoo':len(data['venues']['zoo']['items'])},ensure_ascii=False))
if __name__=='__main__':run()
