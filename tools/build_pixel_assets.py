"""Author a playable layout from CC0 tiles, plus original RPG-style character sheets."""
import json, random
from pathlib import Path
from PIL import Image, ImageDraw

PROJECT = Path(__file__).parent
if not (PROJECT / 'prototype').is_dir(): PROJECT = PROJECT.parent
ROOT = PROJECT / 'prototype/web/assets'
ROOT.mkdir(parents=True, exist_ok=True)
NAMES = ['曉晴','雨澄','以寧','若涵','季夏','庭羽','知秋','映彤','芷禾','書瑤']
PALETTES = [('#653b28','#dc7659'),('#263547','#639eaf'),('#62517c','#b19cc9'),
            ('#aa7543','#84a07b'),('#292d36','#e9b85b'),('#a95845','#689cab'),
            ('#6d4e32','#d7c7a0'),('#232932','#a06c82'),('#656b43','#849c56'),
            ('#544341','#7488af'),('#4b514c','#f1e9d5')]

def character(i):
    hair, outfit = PALETTES[i]; skin = '#edb68c'; shade = '#d09473'
    sheet = Image.new('RGBA',(72,128))
    for row in range(4):
        for frame in range(3):
            sprite=Image.new('RGBA',(24,32)); d=ImageDraw.Draw(sprite)
            def box(x0,y0,x1,y1,c): d.rectangle((x0,y0,x1,y1),fill=c)
            bob = int(frame != 1)
            # Different silhouettes: long hair, bob, side pony, bun, short cut.
            style = i % 5
            box(7,2+bob,16,13+bob,hair); box(6,4+bob,17,10+bob,hair)
            if style==0: box(5,7+bob,8,22+bob,hair); box(15,7+bob,18,22+bob,hair)
            if style==2: box(17,5+bob,20,18+bob,hair)
            if style==3: box(9,0+bob,14,3+bob,hair)
            box(8,5+bob,15,12+bob,skin); box(8,3+bob,15,5+bob,hair)
            box(8,5+bob,10,6+bob,hair)
            if row==3: box(7,3+bob,16,13+bob,hair)
            elif row==1: box(7,5+bob,11,11+bob,hair); box(14,8+bob,14,9+bob,'#333936')
            elif row==2: box(12,5+bob,16,11+bob,hair); box(9,8+bob,9,9+bob,'#333936')
            else:
                box(9,8+bob,9,9+bob,'#333936'); box(14,8+bob,14,9+bob,'#333936')
                box(11,11+bob,12,11+bob,shade)
            box(10,13+bob,13,15+bob,skin)
            box(7,15+bob,16,23+bob,outfit); box(6,16+bob,6,21+bob,outfit)
            box(17,16+bob,17,21+bob,outfit); box(6,22+bob,7,24+bob,skin); box(16,22+bob,17,24+bob,skin)
            box(9,15+bob,14,16+bob,'#eee0c7')
            if i in (0,3,6,8):
                box(6,23+bob,17,26+bob,outfit); box(7,25+bob,8,26+bob,'#544843')
            else: box(8,23+bob,15,26+bob,'#485468'); box(11,24+bob,12,27+bob,'#384350')
            # Distinct accessories as well as colour: glasses, flower, apron, scarf, camera.
            if i==1 and row==0: box(8,7+bob,10,9+bob,'#38454f'); box(13,7+bob,15,9+bob,'#38454f'); box(11,8+bob,12,8+bob,'#38454f')
            if i==3: box(9,18+bob,14,25+bob,'#e7debe')
            if i==4: box(7,1+bob,16,3+bob,'#dbc98b')
            if i==6: box(12,20+bob,16,23+bob,'#354344'); box(13,21+bob,14,22+bob,'#9bb9aa')
            if i==7: box(8,15+bob,13,17+bob,'#d5a96d')
            if i==8: box(15,4+bob,17,6+bob,'#f3df9b')
            if i==2: box(7,7+bob,8,10+bob,'#d3b555')
            stride=1 if frame==0 else -1 if frame==2 else 0
            box(8,27+stride,10,29+stride,'#443b3b'); box(13,27-stride,15,29-stride,'#443b3b')
            sheet.alpha_composite(sprite,(frame*24,row*32))
    ident = f'member-{i+1:02d}' if i<10 else 'player'
    sheet.save(ROOT / (ident+'.png'))
    # Larger original pixel bust for dialogue; deterministic and reusable, no paid generation.
    p=Image.new('RGBA',(48,64)); d=ImageDraw.Draw(p)
    d.rectangle((10,6,37,42),fill=hair); d.rectangle((7,12,40,31),fill=hair)
    if i%5==3: d.rectangle((17,1,30,8),fill=hair)
    if i%5==2: d.rectangle((37,12,44,49),fill=hair)
    d.rectangle((14,15,33,37),fill=skin); d.rectangle((13,11,34,17),fill=hair)
    d.rectangle((14,16,21,20),fill=hair)
    d.rectangle((17,25,19,27),fill='#38413c'); d.rectangle((28,25,30,27),fill='#38413c')
    d.rectangle((21,34,26,34),fill=shade); d.rectangle((20,38,28,44),fill=skin)
    d.rectangle((8,45,40,63),fill=outfit); d.rectangle((4,51,44,63),fill=outfit)
    d.rectangle((17,44,31,46),fill='#eee0c7')
    if i==1:
        d.rectangle((15,23,22,29),outline='#38454f',width=2); d.rectangle((26,23,33,29),outline='#38454f',width=2); d.line((22,25,26,25),fill='#38454f',width=2)
    if i==4: d.rectangle((10,5,37,11),fill='#dbc98b')
    if i==8: d.rectangle((33,12,38,17),fill='#f3df9b')
    if i==3: d.rectangle((16,48,33,63),fill='#e7debe')
    if i==7: d.rectangle((16,44,29,49),fill='#d5a96d')
    if i==6: d.rectangle((27,56,38,63),fill='#354344')
    p.save(ROOT / (ident+'-portrait.png'))

def town():
    w,h=36,28; rng=random.Random(32)
    ground=[[rng.choices([0,1,2],[80,18,2])[0] for x in range(w)] for y in range(h)]
    decor=[[-1]*w for _ in range(h)]; blocked=set(); portals=[]; labels=[]
    def tile(x,y,n,solid=False):
        decor[y][x]=n
        if solid: blocked.add((x,y))
    # Wide connected paths, ten distinct homes, and a shared garden courtyard.
    for y in (9,10,18,19):
        for x in range(2,w-2): ground[y][x]=25
    for x in (4,11,18,25,32):
        for y in range(7,24):
            for dx in (0,1): ground[y][x+dx]=25
    for y in range(11,18):
        for x in range(14,23): ground[y][x]=25 if (x+y)%5 else 43
    for i in range(10):
        x=2+(i%5)*7; y=3 if i<5 else 21
        red=i%3==0
        rows=[[52,53,53,54],[64,65,65,66],[72,84,73,73],[72,73,85,73]] if red else [[48,49,49,50],[60,61,61,62],[76,88,77,77],[76,77,89,77]]
        for dy,row in enumerate(rows):
            for dx,n in enumerate(row): tile(x+dx,y+dy,n,True)
        door=(x+2,y+3); blocked.remove(door)
        portals.append({'x':door[0],'y':door[1],'to':f'room-{i+1:02d}','spawn':[10,11]})
        labels.append({'x':x+2,'y':y-1,'text':NAMES[i]+'的家'})
    for x,y in [(2,13),(3,16),(8,13),(11,13),(27,14),(30,15),(33,12),(8,17),(25,17)]:
        tile(x,y-1,4); tile(x,y,16,True)
    for x,y in [(1,2),(7,2),(13,1),(21,1),(28,2),(34,3),(1,25),(7,26),(13,26),(23,26),(29,26),(34,25)]:
        tile(x,y,16,True)
    tile(16,12,44,True); tile(17,12,45,True); tile(18,12,46,True)
    tile(21,14,104,True); tile(21,13,57,True)
    tile(14,15,28,True); tile(22,16,29,True)
    return {'id':'shared','name':'午後小聚落','width':w,'height':h,'ground':ground,'decor':decor,
            'blocked':[list(p) for p in sorted(blocked)],'portals':portals,'labels':labels,
            'objects':[{'id':'bench','x':17,'y':12,'name':'庭院長椅','description':'坐下歇一會兒，時間會繼續流動。','effect':'rest'},
                       {'id':'garden','x':14,'y':15,'name':'小花圃','description':'替花圃澆水。今天澆過後就不用重複了。','effect':'water'},
                       {'id':'well','x':21,'y':14,'name':'庭院水井','description':'井水很涼。附近的長椅適合等人。','effect':'inspect'}]}

maps={'shared':town()}
for i in range(10):
    w,h=20,15; ground=[[109]*w for _ in range(h)]; decor=[[-1]*w for _ in range(h)]
    blocked={(x,y) for y in range(h) for x in range(w) if x in (0,w-1) or y in (0,h-1)}
    for x in range(w): decor[0][x]=96+(x%3); decor[h-1][x]=120+(x%3)
    for y in range(1,h-1): decor[y][0]=108; decor[y][w-1]=110
    for x,y in [(5,5),(6,5),(7,5),(14,4),(15,4),(14,5),(15,5),(15,9)]: blocked.add((x,y))
    door=maps['shared']['portals'][i]
    maps[f'room-{i+1:02d}']={'id':f'room-{i+1:02d}','name':NAMES[i]+'的家','width':w,'height':h,
        'ground':ground,'decor':decor,'blocked':[list(p) for p in sorted(blocked)],'labels':[],
        'portals':[{'x':10,'y':13,'to':'shared','spawn':[door['x'],door['y']+1]}],
        'objects':[{'id':'desk','x':6,'y':5,'name':'工作桌','description':'她留在桌上的物品。私人內容需要她自己願意分享。','effect':'inspect'},
                   {'id':'bed','x':14,'y':5,'name':'床','description':'這是她的私人生活空間。','effect':'inspect'},
                   {'id':'plant','x':15,'y':9,'name':'窗邊植物','description':'葉片在光裡微微發亮。','effect':'inspect'}]}
(ROOT/'maps.json').write_text(json.dumps({'version':1,'tile_size':16,'atlas':'/assets/tiny-town.png','source':'https://kenney.nl/assets/tiny-town','license':'CC0','maps':maps},ensure_ascii=False,separators=(',',':')),encoding='utf-8')
for i in range(11): character(i)
print('11 original walking sheets + portraits; 11 maps; Kenney CC0 atlas')
