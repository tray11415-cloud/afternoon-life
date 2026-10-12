"""Rebuild original park and consignment market after public catalog sync."""
import datetime,json
from pathlib import Path

def run(root=None):
    ROOT=(Path(root) if root else Path(__file__).resolve().parents[1])/'prototype'
    source=ROOT/'web/assets/maps.json';spec=json.loads(source.read_text(encoding='utf-8'));maps=spec['maps']
    def base(id,name,w=40,h=28):
        m={'id':id,'name':name,'width':w,'height':h,'ground':[[0]*w for _ in range(h)],'decor':[[-1]*w for _ in range(h)],
           'blocked':[[x,y] for y in range(h) for x in range(w) if x in (0,w-1) or y in (0,h-1)],'portals':[], 'objects':[], 'labels':[], 'props':[],'theme':id}
        maps[id]=m;return m
    d=maps['district']
    for id,x,y,label in [('park',38,12,'河畔公園 →'),('market',18,26,'共居市集 ↓')]:
        d['portals']=[p for p in d['portals'] if p['to']!=id];d['portals'].append({'x':x,'y':y,'to':id,'spawn':[20,25]})
        d['blocked']=[p for p in d['blocked'] if p!=[x,y]];d['ground'][y][x]=25
        d['labels']=[entry for entry in d['labels'] if entry['text']!=label]
        d['labels'].append({'x':x-2,'y':y-1,'text':label})
        m=base(id,'河畔公園' if id=='park' else '共居市集')
        m['portals'].append({'x':20,'y':26,'to':'district','spawn':[x-1,y] if id=='park' else [x,y-1]})
        m['labels'].append({'x':20,'y':26,'text':'公共街區 ↑'})
        for xx in range(3,37):
            for yy in range(19,23):m['ground'][yy][xx]=25
        for yy in range(2,27):m['ground'][yy][20]=25;m['ground'][yy][19]=25
    def obj(m,id,title,x,y,kind):
        m['objects'].append({'id':id,'name':title,'x':x,'y':y,'effect':'venue','description':'走近，按 E 查看活動或商品。'})
        m['blocked'].append([x,y]);m['props'].append({'kind':kind,'x':x,'y':y});m['labels'].append({'x':x,'y':y-1,'text':title})
    p=maps['park'];obj(p,'park-desk','花園休息站',20,16,'gazebo');obj(p,'riverside','河畔長椅',8,20,'bench');obj(p,'flower-path','花圃與鳥群',12,8,'flowerbed')
    for x in range(27,36):
        for y in range(4,16):p['ground'][y][x]=6;p['blocked'].append([x,y])
    p['props'].append({'kind':'pond','x':31,'y':10})
    for x,y in [(5,5),(8,12),(25,20),(34,22),(3,16),(24,3)]:p['props'].append({'kind':'tree','x':x,'y':y});p['blocked'].append([x,y])
    for x,y in [(6,22),(28,20)]:p['props'].append({'kind':'bench','x':x,'y':y});p['blocked'].append([x,y])
    m=maps['market'];obj(m,'market-desk','交易與招工看板',20,18,'marketboard')
    names=['曉晴','雨澄','以寧','若涵','季夏','庭羽','知秋','映彤','芷禾','書瑤']
    for i,name in enumerate(names):
        x=6+7*(i%5);y=5+8*(i//5)
        obj(m,'stall-'+str(i+1),name+'的寄售攤位',x,y,'stall')
        m['props'][-1]['index']=i
        m['blocked'] += [[x-1,y],[x+1,y]]
    for x in (8,32):m['props'].append({'kind':'table','x':x,'y':23});m['blocked'].append([x,23])
    source.write_text(json.dumps(spec,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    file=ROOT/'data/venues.json';catalog=json.loads(file.read_text(encoding='utf-8'));today=datetime.datetime.now(datetime.timezone.utc).isoformat()
    def row(id,title,minutes,mode,facts,price=0,command=None):
        value={'id':id,'title':title,'minutes':minutes,'mode':mode,'facts':facts,'price':price,'category':'本作原創','url':None}
        if command:value['command']=command
        return value
    catalog['venues']['park']={'name':'河畔公園','url':None,'checked_at':today,'note':'河畔散步、長椅休息、花圃與鳥群。活動會舒緩疲勞和滿足好奇心。','items':[
        row('park-rest','在花園長椅休息',6,'坐一會兒','花木和河風讓人放慢腳步。你實際在公園休息了一會兒。'),
        row('park-birds','觀察花圃與鳥群',8,'觀察','公園的鳥群停在花圃旁，風吹過樹影。這是本作公園的觀察紀錄。'),
        row('park-walk','河畔休息與伸展',8,'休息與伸展','在河畔休息站伸展，身體稍微放鬆。散步可直接在地圖上行走。')]}
    catalog['venues']['market']={'name':'共居市集','url':None,'checked_at':today,'note':'角色把在家做出的作品放到寄售攤位。真實角色或玩家買下才成交；剩餘作品可以收攤取回。','items':[
        row('water','一瓶飲用水',0,'買來帶走','可帶到公園飲用。',6,'buy_supply'),
        row('snack','市集飯糰',0,'買來帶走','一份飯糰可填飽肚子。',8,'buy_supply'),
        row('materials','創作材料包 · 三份材料',0,'買材料','在家工作桌製作自己的作品。',12,'buy_supply'),
        row('market-browse','逛逛市集與攤位',8,'逛一會兒','逛了市集攤位與公開交易看板。只有實際買下的作品才會進入物品袋。')]}
    file.write_text(json.dumps(catalog,ensure_ascii=False,indent=2),encoding='utf-8')
    print('Maps:',len(maps),'venues:',len(catalog['venues']))

if __name__=='__main__':run()
