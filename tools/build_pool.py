from pathlib import Path
import json,copy
import argparse
parser=argparse.ArgumentParser();parser.add_argument('--project',type=Path,default=Path(__file__).resolve().parents[1]);args=parser.parse_args();root=args.project.resolve()/'prototype';path=root/'web/assets/maps.json';doc=json.loads(path.read_text(encoding='utf-8'));maps=doc['maps']
if 'pool' not in maps:
 base=copy.deepcopy(maps['cafe']);w,h=base['width'],base['height']
 base.update(name='晴水游泳池',objects=[{'id':'pool-lobby','x':5,'y':13,'description':'接待台與休息區；下水前需到更衣櫃換泳裝。','effect':'none'},{'id':'pool-locker','x':5,'y':15,'description':'更衣櫃：換上泳裝後才可進入水域；離開泳池會換回原服裝。','effect':'none'},{'id':'pool-water','x':9,'y':13,'description':'泳池水域；下水前必須穿泳衣。','effect':'none'}],labels=[{'x':15,'y':4,'text':'泳池水域'},{'x':5,'y':16,'text':'更衣區'}])
 base['blocked']=[[x,y] for y in range(h) for x in range(w) if x==0 or x==w-1 or y==0 or y==h-1]
 entry=maps['cafe']['portals'][0];base['portals']=[{'x':entry['x'],'y':entry['y'],'to':'district','spawn':[3,18]}]
 base['blocked']=[p for p in base['blocked'] if p!=[entry['x'],entry['y']]]
 maps['pool']=base;district=maps['district'];district['portals'].append({'x':3,'y':18,'to':'pool','spawn':[entry['x'],entry['y']-1]});district['blocked']=[p for p in district['blocked'] if p!=[3,18]];district['labels'].append({'x':3,'y':17,'text':'游泳池'})
 # Remove copied cafe object/tile barriers; the pool has its own physical plan.
 path.write_text(json.dumps(doc,ensure_ascii=False),encoding='utf-8')
vpath=root/'data/venues.json';v=json.loads(vpath.read_text(encoding='utf-8'));v['venues']['pool']={'name':'晴水游泳池','url':'','note':'本作原創泳池。更衣櫃換泳裝，下水後可游泳十五分鐘；泳裝 LoRA 在生圖設定綁定。','checked_at':'2026-10-12T00:00:00+00:00','items':[{'id':'pool-swim','title':'游泳十五分鐘','category':'運動','url':'','price':0,'minutes':15,'mode':'游泳','facts':'穿著泳裝在公共泳池游泳。','command':'pool_swim'}]};vpath.write_text(json.dumps(v,ensure_ascii=False),encoding='utf-8')
print({'pool_size':[maps['pool']['width'],maps['pool']['height']],'maps':len(maps),'district_size':[maps['district']['width'],maps['district']['height']]})
