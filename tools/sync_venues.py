"""Fetch public text catalogs. No API key or paid model is used."""
import concurrent.futures, datetime, hashlib, json, re, time, sys
sys.stdout.reconfigure(encoding='utf-8')
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

ROOT=Path(__file__).resolve().parents[1]
CACHE=ROOT/'work/source-cache'
class Page(HTMLParser):
    def __init__(self,html):
        super().__init__(); self.links=[]; self.text=[]; self.href=None; self.label=[]; self.skip=0; self.feed(html)
    def handle_starttag(self,tag,attrs):
        a=dict(attrs)
        if tag in ('script','style'): self.skip+=1
        if tag=='a': self.href=a.get('href'); self.label=[]
    def handle_endtag(self,tag):
        if tag in ('script','style'): self.skip=max(0,self.skip-1)
        if tag=='a' and self.href: self.links.append((self.href,' '.join(self.label).strip())); self.href=None
    def handle_data(self,data):
        if not self.skip:
            t=data.strip()
            if t: self.text.append(t)
            if self.href: self.label.append(t)
def fetch(url):
    CACHE.mkdir(parents=True,exist_ok=True); path=CACHE/(hashlib.sha256(url.encode()).hexdigest()+'.json')
    if path.exists() and time.time()-path.stat().st_mtime<3600:
        return json.loads(path.read_text(encoding='utf-8'))
    try:
        with urlopen(Request(url,headers={'User-Agent':'LifeSandbox/0.6 (public text catalog)'}),timeout=25) as r:
            data=r.read(4*1024*1024+1)
            if len(data)>4*1024*1024: raise ValueError('source too large')
            detected=re.search(br'<meta[^>]+charset\s*=\s*["\']?([^\s"\'>;/]+)',data,re.I)
            charset=detected.group(1).decode('ascii') if detected else r.headers.get_content_charset() or 'utf-8'
            html=data.decode(charset,errors='replace')
        page=Page(html); value={'url':url,'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat(),'links':page.links,'text':'\n'.join(page.text),'html':html}
        path.write_text(json.dumps(value,ensure_ascii=False),encoding='utf-8'); return value
    except Exception:
        if path.exists(): return json.loads(path.read_text(encoding='utf-8'))
        raise
def batch(urls):
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        futures={pool.submit(fetch,u):u for u in dict.fromkeys(urls)}; pages=[]
        for f in concurrent.futures.as_completed(futures):
            try: pages.append(f.result())
            except Exception as e: print(json.dumps({'source_error':futures[f],'error':type(e).__name__}))
        return pages
if __name__=='__main__':
    import sys
    urls=sys.argv[1:] or ['https://www.starbucks.com.tw/products/drinks.jspx','https://www.starbucks.com.tw/products/food.jspx','https://www.zoo.gov.taipei/Content_List.aspx?n=2A2A438C69D87202','https://www.gutenberg.org/browse/languages/zh','https://video.blender.org/api/v1/search/videos?search=Sintel','https://www.nga.gov/calendar?tab=exhibitions']
    for p in batch(urls):
        print(json.dumps({'url':p['url'],'length':len(p['text']),'links':[(u,t) for u,t in p['links'] if ('catId=' in u or '圖鑑' in t or '/ebooks/' in u or '/exhibitions/' in u)][:30],'sample':p['text'][:500] if 'blender' in p['url'] else ''},ensure_ascii=False))
