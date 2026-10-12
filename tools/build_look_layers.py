from pathlib import Path
from PIL import Image,ImageChops,ImageDraw
import csv,json,argparse
ap=argparse.ArgumentParser();ap.add_argument('--project',type=Path,default=Path.cwd());ap.add_argument('--source',type=Path,required=True);args=ap.parse_args();root=args.project;source=args.source;assets=root/'prototype/web/assets';assets.mkdir(parents=True,exist_ok=True);used=set()
def layer(name):
 used.add(name)
 with Image.open(source/name) as im:
  im.load();assert im.size==(576,256),(name,im.size);return im.convert('RGBA')
def mask(alpha):
 im=Image.new('RGBA',(576,256),'white');im.putalpha(alpha);return im
for gender in ('male','female'):
 body=layer(f'body/bodies/{gender}/walk.png');body.alpha_composite(layer(f'head/heads/human/{gender}/walk.png'))
 pants=layer(f'legs/pants/{"male" if gender=="male" else "thin"}/walk.png');shoes=layer(f'feet/shoes/revised/{"male" if gender=="male" else "thin"}/walk.png')
 for shape,shirt in [('plain','longsleeve2'),('cardigan','longsleeve2_cardigan'),('buttoned','longsleeve2_buttoned'),('swim','longsleeve2')]:
  top=layer(f'torso/clothes/longsleeve/{shirt}/{gender}/walk.png');bottom=pants.copy()
  if shape=='swim':
   # Match the existing SFW native pool placeholder. The SD workflow supplies
   # detailed swimwear. Covered pelvis regions are retained in every direction.
   top=Image.new('RGBA',(576,256))
   if gender=='male':
    for row in range(4):
     for frame in range(9):
      for y in range(45,64):
       for x in range(64):bottom.putpixel((frame*64+x,row*64+y),(0,0,0,0))
   else:
    draw=ImageDraw.Draw(top)
    for row in range(4):
     for frame in range(9):draw.rectangle((frame*64+26,row*64+34,frame*64+37,row*64+41),fill='#7f7f7f')
  garments=Image.new('RGBA',(576,256));garments.alpha_composite(bottom);garments.alpha_composite(shoes);garments.alpha_composite(top)
  base=body.copy();base.alpha_composite(garments)
  skin=ImageChops.multiply(body.getchannel('A'),ImageChops.invert(garments.getchannel('A')))
  bottom_mask=ImageChops.multiply(bottom.getchannel('A'),ImageChops.invert(top.getchannel('A')))
  prefix=f'{gender}-{shape}.png'
  base.save(assets/f'look-base-{prefix}',optimize=True);mask(skin).save(assets/f'look-skin-{prefix}',optimize=True);mask(top.getchannel('A')).save(assets/f'look-top-{prefix}',optimize=True);mask(bottom_mask).save(assets/f'look-bottom-{prefix}',optimize=True)
styles={'short':'bangsshort','pixie':'pixie','bob':'bob','long':'long_straight','curly':'curly_long','bun':'bangs_bun','side_bob':'bob_side_part','wavy':'long'}
for key,name in styles.items():layer('hair/'+name+'/adult/walk.png').save(assets/f'look-hair-{key}.png',optimize=True)
rows=[r for r in csv.DictReader((source.parent/'CREDITS.csv').open(encoding='utf-8')) if r['filename'] in used]
assert set(r['filename'] for r in rows)==used
credits=assets/'LPC-CREDITS.txt';marker='\n=== v0.20 Clothed character customisation layers ==='
text=credits.read_text(encoding='utf-8').split(marker)[0]+marker+'\nSource: https://github.com/LiberatedPixelCup/Universal-LPC-Spritesheet-Character-Generator\nLayer composites, masks and adaptive previews: CC BY-SA 4.0. Original authors and offered upstream licences follow. Raw nude body layers are not packaged.\n'
text+='\n'.join(json.dumps(r,ensure_ascii=False) for r in rows)+'\n';credits.write_text(text,encoding='utf-8')
print(json.dumps({'clothed_layers':32,'hair_layers':8,'source_files':len(used)}))
