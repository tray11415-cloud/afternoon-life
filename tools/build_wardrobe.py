"""Rebuild the clothing map and shop from the curated, saved SFW catalog.
No downloads or paid model calls. Run after public venue catalog updates.
"""
import json
from pathlib import Path

def run(root=None):
 root=Path(root) if root else Path(__file__).resolve().parents[1]
 proto=root/'prototype'
 catalog=json.loads((proto/'data/clothing.json').read_text(encoding='utf-8'))
 items=catalog['items']
 mapsfile=proto/'web/assets/maps.json';spec=json.loads(mapsfile.read_text(encoding='utf-8'));maps=spec['maps'];d=maps['district']
 d['portals']=[p for p in d['portals'] if p['to']!='boutique'];d['portals'].append({'x':29,'y':26,'to':'boutique','spawn':[14,19]})
 d['blocked']=[p for p in d['blocked'] if p!=[29,26]];d['ground'][26][29]=25
 d['labels']=[p for p in d['labels'] if p['text']!='日常衣間 ↓'];d['labels'].append({'x':29,'y':25,'text':'日常衣間 ↓'})
 m={'id':'boutique','name':'日常衣間','width':30,'height':22,'theme':'boutique','ground':[[0]*30 for _ in range(22)],'decor':[[-1]*30 for _ in range(22)],
  'blocked':[[x,y] for y in range(22) for x in range(30) if x in (0,29) or y in (0,21)],
  'portals':[{'x':14,'y':20,'to':'district','spawn':[29,25]}],
  'objects':[{'id':'boutique-desk','name':'服飾與選購桌','x':14,'y':10,'effect':'venue','description':'在這裡選購衣服；回自己家換裝。'}],
  'props':[{'kind':'counter','x':14,'y':10},{'kind':'mirror','x':25,'y':6}],
  'labels':[{'x':14,'y':9,'text':'服飾與選購桌'},{'x':14,'y':20,'text':'公共街區 ↑'},{'x':25,'y':4,'text':'試衣鏡'}]}
 m['blocked']+=[[x,10] for x in range(12,17)]+[[25,6]]
 for i,item in enumerate(items):
  x=5+8*(i%3);y=5+9*(i//3)
  m['props'].append({'kind':'clothesrack','x':x,'y':y,'palette':item['palette'],'shape':item['shape']})
  m['blocked'] += [[x-1,y],[x,y],[x+1,y]]
  m['labels'].append({'x':x,'y':y-1,'text':item['title']})
 maps['boutique']=m;mapsfile.write_text(json.dumps(spec,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
 venuesfile=proto/'data/venues.json';venues=json.loads(venuesfile.read_text(encoding='utf-8'))
 venues['venues']['boutique']={'name':'日常衣間','url':None,'checked_at':catalog['checked_at'],'note':'用自己的代幣買衣服，放入衣櫃後回家換裝。穿著會保存為之後立繪與 CG 的服裝描述。','items':[
  {'id':i['id'],'title':i['title'],'category':'SFW · 日常服飾','price':i['price'],'minutes':0,'mode':'買下這套','command':'buy_clothes','url':i['source']['url'],
   'facts':'長袖與不透明布料的日常服裝。','color':i['palette']['top']} for i in items]+[
  {'id':'boutique-browse','title':'逛逛衣架與搭配','category':'本作原創','price':0,'minutes':6,'mode':'逛一會兒','url':None,'facts':'看了衣間的日常服飾與顏色搭配，沒有購買尚未付款的衣服。'}]}
 venuesfile.write_text(json.dumps(venues,ensure_ascii=False,indent=2),encoding='utf-8')
 print('Curated SFW prompt outfits:',len(items),'maps:',len(maps),'venues:',len(venues['venues']))

if __name__=='__main__':run()
