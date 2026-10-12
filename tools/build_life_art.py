from pathlib import Path
import json,urllib.request,importlib.util,csv,re
from PIL import Image,ImageDraw
import argparse
parser=argparse.ArgumentParser();parser.add_argument('--project',type=Path,default=Path(__file__).resolve().parents[1]);args=parser.parse_args()
stage=args.project.resolve();assets=stage/'prototype/web/assets';source=stage/'art-sources';male=source/'characters/spritesheets';male.mkdir(parents=True,exist_ok=True)
files=['body/bodies/male/walk.png','head/heads/human/male/walk.png','legs/pants/male/walk.png','feet/shoes/revised/male/walk.png','torso/clothes/longsleeve/longsleeve2/male/walk.png','torso/clothes/longsleeve/longsleeve2_cardigan/male/walk.png','torso/clothes/longsleeve/longsleeve2_buttoned/male/walk.png']
for name in files:
 p=male/name;p.parent.mkdir(parents=True,exist_ok=True)
 if not p.is_file():
  url='https://raw.githubusercontent.com/LiberatedPixelCup/Universal-LPC-Spritesheet-Character-Generator/master/spritesheets/'+name
  with urllib.request.urlopen(url,timeout=25) as r:raw=r.read(2*1024*1024)
  assert raw.startswith(b'\x89PNG');p.write_bytes(raw)
spec=importlib.util.spec_from_file_location('lpc_build',str(stage/'tools/build_lpc_art.py'));mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);c=mod.Composer(source,assets)
def layer(name,color=None):
 path=male/name if '/male/' in name else source/'characters/spritesheets'/name
 im=Image.open(path).convert('RGBA');return c.recolor(im,color) if color else im
def make(ident,male_body,hair,haircolor,top,bottom,outfit='original',swim=False):
 sex='male' if male_body else 'female';im=Image.new('RGBA',(576,256))
 im.alpha_composite(layer('body/bodies/'+sex+'/walk.png'));im.alpha_composite(layer('head/heads/human/'+sex+'/walk.png'))
 pants=layer('legs/pants/'+('male' if male_body else 'thin')+'/walk.png',bottom)
 if swim:
  # Athletic shorts/one-piece are a native placeholder; actual LoRA renders replace it.
  if male_body:
   for row in range(4):
    for frame in range(9):
     piece=pants.crop((frame*64,row*64,frame*64+64,row*64+45));im.alpha_composite(piece,(frame*64,row*64))
  else:
   for row in range(4):
    for frame in range(9):
     d=ImageDraw.Draw(im);x=frame*64;y=row*64;d.rectangle((x+26,y+34,x+37,y+41),fill=top)
 else:im.alpha_composite(pants);im.alpha_composite(layer('feet/shoes/revised/'+('male' if male_body else 'thin')+'/walk.png','#4a4547'))
 shirt='longsleeve2_cardigan' if 'cardigan' in outfit else 'longsleeve2_buttoned' if 'blazer' in outfit else 'longsleeve2'
 im.alpha_composite(layer('torso/clothes/longsleeve/'+shirt+'/'+sex+'/walk.png',top))
 im.alpha_composite(layer('hair/'+hair+'/adult/walk.png',haircolor));im.save(assets/f'lpc-{ident}-{outfit}.png',optimize=True)
 im.crop((12,132,52,192)).save(assets/f'lpc-{ident}-{outfit}-portrait.png',optimize=True)
p=stage/'prototype/web/engine.js';text=p.read_text(encoding='utf-8');start=re.search(r'const LPC_ART\s*=\s*',text).end();end=text.index(';',start);manifest=json.loads(text[start:end].strip())
clothes=json.loads((stage/'prototype/data/clothing.json').read_text(encoding='utf-8'))['items']
for item in [{'id':'original','palette':{'top':'#71889c','bottom':'#525f64'}}]+clothes:
 make('player',True,'pixie','#49544f',item['palette']['top'],item['palette']['bottom'],item['id'])
import sys;sys.path.insert(0,str(stage/'prototype'));from lifebox.neighborhood import NPCS
hairstyles=['bob','bangsshort','long_straight','pixie','bob_side_part','bangsshort'];colors=['#6b5140','#343139','#514350','#735449','#685540','#363a40']
for i,(ident,npc) in enumerate(NPCS.items()):make(ident,npc['gender']=='male',hairstyles[i],colors[i],'#648b9f','#525f64');manifest['variants'][ident]=['original']
for i,ident in enumerate([f'member-{j:02d}' for j in range(1,11)]+['player']):
 outfit='swim-trunks' if ident=='player' else 'swim-onepiece';hair=mod.HAIR[i]
 if hair=='ponytail':hair='bangsshort'
 make(ident,ident=='player',hair,mod.HAIR_COLORS[i],'#416383','#26466d',outfit,True);manifest['variants'][ident]=list(dict.fromkeys(manifest['variants'][ident]+[outfit]))
m=json.loads((assets/'maps.json').read_text(encoding='utf-8'))['maps']['pool'];im=Image.new('RGBA',(m['width']*32,m['height']*32));floor=c.tile(mod.INTERIOR,32,128);water=c.tile(mod.BASE+'/tiles/water.png',32,160)
for y in range(m['height']):
 for x in range(m['width']):im.alpha_composite(water if 9<=x<=22 and 4<=y<=12 else floor,(x*32,y*32))
d=ImageDraw.Draw(im)
for y in (4,7,10,13):d.line((9*32,y*32,23*32,y*32),fill='#edf4e9',width=3)
d.rectangle((9*32-5,4*32-5,23*32+5,13*32+5),outline='#dde7df',width=5)
for x in (3,5,7):
 d.rounded_rectangle((x*32,15*32,x*32+28,16*32+8),radius=3,fill='#567c91',outline='#304a5b',width=2);d.ellipse((x*32+19,15*32+19,x*32+22,15*32+22),fill='#e5d6ad')
for y in (2,16):
 for x in (11,15,19):d.rounded_rectangle((x*32,y*32,x*32+50,y*32+19),radius=4,fill='#ede0b8',outline='#796d59',width=2)
d.rectangle((0,0,im.width-1,im.height-1),outline='#66796f',width=24);im.save(assets/'lpc-map-pool.png',optimize=True)
manifest['scenes']['pool']={'background':'/assets/lpc-map-pool.png','decor':[]};district=manifest['scenes']['district'];board={'image':'/assets/lpc-prop-board.png','x':3*32,'y':18*32-29,'depth':18*32+1};district['decor']=[d for d in district['decor'] if d!=board]+[board]

for scene,v in manifest['scenes'].items():
 for i,d in enumerate(v['decor']):d.setdefault('id',scene+'-decor-'+str(i))
(stage/'prototype/data/art-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False),encoding='utf-8')
text=text[:start]+json.dumps(manifest,ensure_ascii=False)+text[end:];p.write_text(text,encoding='utf-8')
credits=assets/'LPC-CREDITS.txt';rows=[r for r in csv.DictReader((source/'characters/CREDITS.csv').open(encoding='utf-8')) if r['filename'] in files]
assert len(rows)==len(files)
marker='\n=== v0.16 Male player and scripted adult NPC layers ==='
credits.write_text(credits.read_text(encoding='utf-8').split(marker)[0],encoding='utf-8')
with credits.open('a',encoding='utf-8') as f:
 f.write('\n=== v0.16 Male player and scripted adult NPC layers ===\nSource: https://github.com/LiberatedPixelCup/Universal-LPC-Spritesheet-Character-Generator\nMale layers use the offered OGA-BY 3.0 option. Existing female/hair/background layer credits remain above. Pool composition and character layer edits: CC BY-SA 4.0.\n')
 for r in rows:f.write(json.dumps(r,ensure_ascii=False)+'\n')
print(json.dumps({'scenes':len(manifest['scenes']),'identities':len(manifest['variants']),'male_layers':len(files),'pool_pixels':im.size},ensure_ascii=False))

import html
p=stage/'prototype/web/index.html';page=p.read_text(encoding='utf-8');page=re.sub(r'(<details class="art-credits">.*?<pre>).*?(</pre>)',lambda m:m[1]+html.escape(credits.read_text(encoding='utf-8'))+m[2],page,count=1,flags=re.S);p.write_text(page,encoding='utf-8')
