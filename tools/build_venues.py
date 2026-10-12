"""Reproducible public maps and text catalog from official/open sources."""
import datetime, hashlib, json, re, sys
from pathlib import Path
from urllib.parse import urljoin, urlparse, parse_qs
from sync_venues import fetch, batch, ROOT

ASSETS=ROOT/'prototype/web/assets'
DATA=ROOT/'prototype/data'; DATA.mkdir(exist_ok=True)
NAMES={'library':'拾光圖書館','cafe':'街角咖啡廳','zoo':'木柵動物園','gallery':'光影美術館','cinema':'小星電影院','restaurant':'暖桌餐廳'}
def item(id,title,category,url,**kw):
    return dict(id=id,title=title,category=category,url=url,**kw)
def catalog():
    previous=json.loads((DATA/'venues.json').read_text(encoding='utf-8'))['venues'] if (DATA/'venues.json').exists() else {}
    venues={k:{'name':v,'items':[],'checked_at':datetime.datetime.now(datetime.timezone.utc).isoformat()} for k,v in NAMES.items()}
    base='https://www.starbucks.com.tw'
    pages=batch([base+'/products/drinks.jspx',base+'/products/food.jspx'])
    seen={p['url'] for p in pages}; cats={}
    # Follow all categories (including nested seasonal categories), never product images.
    for depth in range(4):
        links={urljoin(p['url'],u):t for p in pages for u,t in p['links'] if '/view.jspx?catId=' in u and '/products/' in u}
        cats.update(links); todo=[u for u in links if u not in seen]
        if not todo: break
        more=batch(todo);seen.update(todo);pages+=more
    products={}
    for p in pages:
        for u,t in p['links']:
            if '/product.jspx?id=' not in u or not t: continue
            url=urljoin(p['url'],u); q=parse_qs(urlparse(url).query); kind='drinks' if '/drinks/' in u else 'food'
            id=kind+'-'+q['id'][0]; title=re.split(r'\s+(?=[A-Za-z])',t,maxsplit=1)[0]
            products[id]=item(id,title,cats.get(p['url'],'飲品' if kind=='drinks' else '糕點'),url,
                price=12 if kind=='drinks' else 18,minutes=3,mode='用餐',facts='官方公開品項；遊戲代幣價格，門市庫存與真實價格請看官方。')
    venues['cafe'].update(items=list(products.values()),url=base+'/products/drinks.jspx',note='星巴克台灣公開飲品／糕點目錄；遊戲代幣價格。')
    zoo='https://www.zoo.gov.taipei/Content_List.aspx?n=2A2A438C69D87202'; index=fetch(zoo)
    zones={urljoin(zoo,u):t.replace('動物圖鑑','') for u,t in index['links'] if '動物圖鑑' in t and 'News_Photo.aspx?' in u}
    zonepages=batch(zones); allpages=list(zonepages); visited=set(zones)
    for depth in range(5):
        # Official atlas pagination: collect every page within the zone, bounded crawl.
        more={urljoin(p['url'],u) for p in allpages for u,t in p['links'] if ('News_Photo.aspx?' in u or 'News.aspx?' in u) and ('Page=' in u or 'page=' in u)}-visited
        if not more: break
        visited.update(more); allpages+=batch(sorted(more)[:100])
    animals={}
    for p in allpages:
        n=parse_qs(urlparse(p['url']).query).get('n',[None])[0]
        category=next((name for u,name in zones.items() if parse_qs(urlparse(u).query).get('n',[None])[0]==n),'動物圖鑑')
        for u,t in p['links']:
            if 'News_Content.aspx?' not in u or 's=' not in u or not t: continue
            q=parse_qs(urlparse(u).query)
            if q.get('n',[None])[0]!=n: continue
            title=re.split(r'\s+\d{2,3}-\d\d-\d\d\s*',t,maxsplit=1)[0].strip()
            title=re.sub(r'^\d+[.、\s]*','',title).strip()
            if not title or len(title)>45: continue
            id='animal-'+q['s'][0].lower()
            brief=re.split(r'\s+\d{2,3}-\d\d-\d\d\s*',t,maxsplit=1)[-1]
            animals[id]=item(id,title,category,urljoin(p['url'],u),price=0,minutes=4,mode='讀動物解說',facts='木柵官方 '+category+'：'+brief[:220]+'。圖鑑快取；實際停展依園方公告。')
    venues['zoo'].update(items=list(animals.values()),url=zoo,note='按官方動物圖鑑分區；非即時動物所在位置。')
    # All Chinese catalog entries link straight into a large online library.
    library='https://www.gutenberg.org/browse/languages/zh'; p=fetch(library); books={}
    for u,t in p['links']:
        match=re.search(r'(?:/ebooks/|ebooks/)(\d+)',u)
        if match and t:
            id='book-'+match[1];books[id]=item(id,t,'中文館藏',urljoin(library,u),price=0,minutes=5,mode='讀一段',facts='Project Gutenberg 中文館藏；逐段閱讀，不把讀過片段當成讀完整本。')
    # Gutenberg language page currently uses /etext/ redirects as well.
    for u,t in p['links']:
        match=re.search(r'(?:/etext/|etext/)(\d+)',u)
        if match and t:
            id='book-'+match[1]; books[id]=item(id,t,'中文館藏','https://www.gutenberg.org/ebooks/'+match[1],price=0,minutes=5,mode='讀一段',facts='Project Gutenberg 中文館藏；逐段閱讀。')
    venues['library'].update(items=list(books.values()),url=library,note='直接連到 Project Gutenberg；可開啟完整原文，Agent 分段閱讀。')
    # Verified current exhibition, and an explicitly dated snapshot of current sources.
    venues['gallery'].update(url='https://www.nga.gov/calendar?tab=exhibitions',note='免費線上官方展覽介紹；依現實日期篩選當期，並附原館連結。',items=[
        item('digital-waves','Clifford Ross：Digital Waves','當期展覽','https://www.nga.gov/exhibitions/clifford-ross',price=0,minutes=4,mode='讀展覽導覽',start='2026-01-21',end='2026-10-18',facts='華盛頓國家藝廊免費展覽，Rotunda 的高螢幕以電腦生成像素模擬海浪；藝術家從海浪攝影發展到數位動態。線上資料是官方文字介紹，沒有進行視覺辨識。'),
        item('nocturnes','Nocturnes：夜的想像','當期展覽','https://www.nga.gov/exhibitions/nocturnes',price=0,minutes=4,mode='讀展覽導覽',start='2026-07-23',end='2027-01-31',facts='華盛頓國家藝廊免費展覽，八位攝影師以夜晚為題。作品可能引發平靜，也可能帶出神祕與不安；展場結合專門製作的音樂與燈光，官方網頁有精選作品與聲音介紹。'),
        item('directors-choice','The Director’s Choice：館長之選','常設線上虛擬展','https://www.nationalgallery.org.uk/visiting/virtual-tours/the-director-s-choice',price=0,minutes=4,mode='讀線上導覽',facts='倫敦國家美術館的免費虛擬展覽，選作由館長 Gabriele Finaldi 挑選及講述。可從官方連結進入虛擬展；此處角色先讀文字導覽。這是公開線上常設資源，並非本期實體特展。'),
    ])
    films=[('Sintel','Sintel','https://durian.blender.org/about/','https://durian.blender.org/sharing/',15),('Big Buck Bunny','Big Buck Bunny','https://peach.blender.org/about/','https://peach.blender.org/about/',10),('Spring','Spring','https://studio.blender.org/projects/spring/','https://studio.blender.org/remixing/',8)]
    for query,title,source,license_url,duration in films:
        p=fetch('https://video.blender.org/api/v1/search/videos?search='+query.replace(' ','%20'))
        rows=json.loads(p['html'])['data']
        rows=[r for r in rows if r.get('account',{}).get('host')=='video.blender.org' and r.get('account',{}).get('name')=='blender' and (r['name'].lower()==title.lower() or ('open movie' in r['name'].lower() and title.lower() in r['name'].lower())) and 'report' not in r['name'].lower() and 'trailer' not in r['name'].lower()]
        if not rows: raise ValueError('official full movie not found: '+title)
        r=min(rows,key=lambda r:abs(r.get('duration',duration*60)-duration*60))
        fetch(source); fetch(license_url)
        venues['cinema']['items'].append(item('film-'+query.lower().replace(' ','-'),title,'Blender 免費開放短片',r['url'],price=0,minutes=duration,mode='讀完整劇情',facts='Blender Foundation 開放電影；角色用文字劇情與文字評論理解，不分析影片影格。',embed='https://video.blender.org/videos/embed/'+r['uuid'],license='CC BY',license_url=license_url,source=source))
    venues['cinema'].update(url='https://video.blender.org/',note='Blender 官方免費開放短片，每個遊戲小時隨機輪映；保留片尾署名。角色採文字理解。')
    dishes=[('herb-chicken','香草烤雞飯','烤雞、蔬菜與米飯，鹹香溫暖。',24),('mushroom','奶油菇菇義大利麵','奶油醬、炒菇與義大利麵。',20),('veggie','時蔬豆腐定食','豆腐、季節蔬菜、白飯與熱湯。',18),('curry','咖哩蔬菜飯','溫和咖哩與根莖蔬菜。',18),('soup','南瓜濃湯與麵包','細滑南瓜湯與烤麵包。',14),('pudding','手作焦糖布丁','飯後的小份焦糖布丁。',8)]
    venues['restaurant'].update(url=None,note='本專案原創菜單，使用遊戲代幣。',items=[item(id,t,'暖桌菜單',None,price=price,minutes=6,mode='用餐',facts=f) for id,t,f,price in dishes])
    # Open-licensed complete story and reception sections are cached as text only.
    for film in venues['cinema']['items']:
        title=film['title'].replace(' ','_'); url='https://en.wikipedia.org/wiki/'+title+('_(2019_film)' if title=='Spring' else '')
        try:
            p=fetch(url); text=p['text']; start=text.find('\nPlot\n',text.find('\nPlot\n')+1)
            if start<0: start=text.find('\nPlot\n')
            section=text[start:] if start>=0 else ''
            stop=re.search(r'\n(?:Voice cast|Cast|Production|Technical information|Development|Credits|Reception|Announcements)\n',section[6:])
            plot=section[6:6+stop.start()] if stop else section[6:5000]
            film['plot_text']=plot[:8000];film['plot_url']=url;film['plot_license']='CC BY-SA; Wikipedia contributors'
            # Reception is evidence of other people's opinions, not the agent's own.
            header='\nReviews\n' if '\nReviews\n' in text else '\nReception\n';rstart=text.rfind(header); review=text[rstart+len(header):] if rstart>=0 else ''
            rstop=re.search(r'\n(?:Awards|See also|References|External links|Release|Game)\n',review)
            film['review_text']=(review[:rstop.start()] if rstop else review[:4000])[:5000]
            film['coverage']='完整劇情文字＋評論段落' if plot and review else '完整劇情文字' if plot else '官方概要'
        except Exception: film['coverage']='官方概要；完整文字暫不可用'
    # Cache several original classics, full text split only when an actor reads.
    old={i['id']:i for i in previous.get('library',{}).get('items',[])}
    for book in venues['library']['items']:
        if book['id'] in old:
            book.update({k:v for k,v in old[book['id']].items() if k in ('text','text_url','text_scope','text_license','coverage')})
    chosen=['紅樓夢','長恨歌','論語','詩經','山海經','道德經','三國演義','西遊記','李太白集','聊齋誌異'] if '--gutenberg-text' in sys.argv else []
    for book in venues['library']['items']:
        if book['title'] not in chosen: continue
        try:
            p=fetch(book['url']); texts=[urljoin(book['url'],u) for u,t in p['links'] if '.txt' in u and 'utf-8' in t.lower()]
            if not texts: texts=[urljoin(book['url'],u) for u,t in p['links'] if '.txt' in u]
            if texts:
                number=book['id'][5:]; direct='https://www.gutenberg.org/cache/epub/'+number+'/pg'+number+'.txt'
                raw=fetch(direct)['html']; body=re.split(r'\*\*\* START OF[^\n]*\n',raw,maxsplit=1)[-1];body=re.split(r'\*\*\* END OF',body,maxsplit=1)[0]
                book.update(text=body.strip(),text_url=texts[0],coverage='完整原文已快取；每次讀一段')
        except Exception: book['coverage']='館藏連結；原文快取暫不可用'
    catalog={'version':1,'venues':venues}
    (DATA/'venues.json').write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({k:{'items':len(v['items']),'text_ready':sum(bool(i.get('text') or i.get('plot_text')) for i in v['items'])} for k,v in venues.items()},ensure_ascii=False))

def maps():
    file=ASSETS/'maps.json'; spec=json.loads(file.read_text(encoding='utf-8')); maps=spec['maps']
    def base(id,name,w=28,h=20,outdoor=False):
        m=dict(id=id,name=name,width=w,height=h,ground=[[0 if outdoor else -1 for x in range(w)] for y in range(h)],decor=[[-1]*w for y in range(h)],blocked=[],portals=[],objects=[],labels=[],theme=id,props=[])
        for x in range(w): m['blocked']+=[[x,0],[x,h-1]]
        for y in range(1,h-1): m['blocked']+=[[0,y],[w-1,y]]
        maps[id]=m;return m
    town=maps['shared'];town['portals']=[p for p in town['portals'] if p['to']!='district']; town['labels']=[l for l in town['labels'] if l.get('text')!='公共街區 →']
    town['portals'].append(dict(x=34,y=18,to='district',spawn=[2,13]));town['labels'].append(dict(x=33,y=17,text='公共街區 →'));town['ground'][18][34]=25
    d=base('district','拾光公共街區',40,28,True)
    d['portals'].append(dict(x=1,y=13,to='shared',spawn=[33,18]));d['blocked']=[p for p in d['blocked'] if p!=[1,13]];d['labels'].append(dict(x=3,y=11,text='← 共居庭院'))
    for y in (11,12,13,14,15,16):
        for x in range(1,39): d['ground'][y][x]=25
    for index,(id,name) in enumerate(NAMES.items()):
        x=8+12*(index%3); y=4 if index<3 else 20; door=[x+2,y+3]
        for yy in range(y,y+4):
            for xx in range(x,x+5): d['blocked'].append([xx,yy]);d['decor'][yy][xx]=63 if yy<y+2 else 76
        d['blocked'].remove(door);d['decor'][door[1]][door[0]]=87;d['portals'].append(dict(x=door[0],y=door[1],to=id,spawn=[14,17]));d['labels'].append(dict(x=x+2,y=y-1,text=name))
        for yy in range(min(door[1],14),max(door[1],14)+1): d['ground'][yy][door[0]]=25
        m=base(id,name,outdoor=id=='zoo'); m['portals'].append(dict(x=14,y=18,to='district',spawn=[door[0],door[1]+1]));m['labels'].append(dict(x=14,y=18,text='出口'))
        obj=dict(id=id+'-desk',name={'library':'借閱桌','cafe':'點餐吧台','zoo':'動物解說站','gallery':'展覽導覽桌','cinema':'售票與場次','restaurant':'點餐桌'}[id],x=14,y=10,effect='venue',description='走近服務桌，按 E 查看內容。')
        m['objects'].append(obj);m['blocked'].append([14,10]);m['labels'].append(dict(x=14,y=9,text=obj['name']));m['props'].append(dict(kind='desk',x=14,y=10))
        if id=='library':
            for xx in (4,8,20,24):
                for yy in (4,5,6,7): m['blocked'].append([xx,yy]);m['props'].append(dict(kind='books',x=xx,y=yy))
            for xx in (7,21): m['props'].append(dict(kind='table',x=xx,y=13));m['blocked'].append([xx,13])
        elif id in ('cafe','restaurant'):
            for xx in (5,10,19,24):
                for yy in (5,14): m['props'].append(dict(kind='table',x=xx,y=yy));m['blocked'].append([xx,yy])
            for xx in range(10,19): m['props'].append(dict(kind='counter',x=xx,y=4));m['blocked'].append([xx,4])
        elif id=='zoo':
            for xx,yy,animal in [(5,4,'熊貓'),(21,4,'長頸鹿'),(5,13,'企鵝'),(21,13,'象')]:
                m['props'].append(dict(kind='habitat',x=xx,y=yy,animal=animal));m['blocked'] += [[a,b] for a in range(xx-2,xx+3) for b in range(yy-1,yy+2)]
                m['labels'].append(dict(x=xx,y=yy+2,text=animal+' · 示意展區'))
        elif id=='gallery':
            for xx in (5,10,18,23): m['props'].append(dict(kind='art',x=xx,y=4));m['blocked'].append([xx,4])
            for xx in (6,22):m['props'].append(dict(kind='sculpture',x=xx,y=13));m['blocked'].append([xx,13])
        elif id=='cinema':
            m['props'].append(dict(kind='screen',x=14,y=3));m['blocked']+=[[x,3] for x in range(9,20)]
            for yy in (6,7,13,14):
                for xx in (5,6,7,9,10,11,17,18,19,21,22,23): m['props'].append(dict(kind='seat',x=xx,y=yy));m['blocked'].append([xx,yy])
    file.write_text(json.dumps(spec,ensure_ascii=False,separators=(',',':')),encoding='utf-8');print('maps:',len(maps))
if __name__=='__main__':
    if '--maps-only' not in sys.argv:
        catalog()
        from library_texts import run
        run()
    maps()
    from build_economy import run as build_economy
    build_economy()

    from build_wardrobe import run as build_wardrobe
    build_wardrobe()
