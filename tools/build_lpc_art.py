"""Compose licensed native-resolution LPC art over the existing collision maps.

No LLM/SD calls, no changes to maps.json, no save reads or writes. All downloads
are build inputs only; originals and their credits stay in art-sources/.
"""
from pathlib import Path
import argparse, csv, hashlib, json, shutil
from PIL import Image, ImageDraw, ImageEnhance, ImageColor

T=32
BASE='base/LPC Base Assets'
INTERIOR='interior/LPC_house_interior/interior.png'
MANSION='buildings/lpc-victorian-buildings/victorian-mansion.png'
DOORS='buildings/lpc-victorian-buildings/victorian-windows-doors.png'
GARDEN='decoration/lpc-victorian-decoration/victorian-garden.png'
MARKET='decoration/lpc-victorian-decoration/victorian-market.png'
STREETS='decoration/lpc-victorian-decoration/victorian-streets.png'
NAMES=['曉晴','雨澄','以寧','若涵','季夏','庭羽','知秋','映彤','芷禾','書瑤']
HAIR=['bangsshort','long_straight','bob','curly_long','pixie','ponytail','bangs_bun','long','bob_side_part','bob','pixie']
HAIR_COLORS=['#684536','#283746','#64547a','#aa6745','#30313a','#a75c46','#795238','#292b34','#687147','#574548','#49544f']
TOP_COLORS=['#ae624b','#667f9c','#9275a3','#7a9577','#c0a65d','#648b9f','#ccb994','#b27980','#829167','#6d8d9b','#71889c']

def digest(path): return hashlib.sha256(path.read_bytes()).hexdigest()
def rgba(c): return ImageColor.getrgb(c)

class Composer:
    def __init__(self,source,target):
        self.source=source;self.target=target;self.loaded={};self.props={};self.used=set();self.scenes={}
    def img(self,f):
        self.used.add(f)
        if f not in self.loaded:self.loaded[f]=Image.open(self.source/f).convert('RGBA')
        return self.loaded[f]
    def crop(self,f,box):return self.img(f).crop(box)
    def tile(self,f,x,y):return self.crop(f,(x,y,x+32,y+32))
    def prop(self,name,f,box):
        if name not in self.props:self.props[name]=self.crop(f,box)
        return name
    def add(self,decor,name,x,y,depth=None):
        im=self.props[name]
        decor.append({'image':f'/assets/lpc-prop-{name}.png','x':round(x),'y':round(y),'depth':round(depth if depth is not None else y+im.height)})
    def centered(self,decor,name,x,y):
        im=self.props[name];self.add(decor,name,x*T+16-im.width/2,(y+1)*T-im.height,(y+1)*T)
    def nine(self,im,w,h):
        out=Image.new('RGBA',(w,h))
        # Repeat middle slices without enlarging pixels.
        for y in range(0,h,32):
            for x in range(0,w,32):
                sx=0 if x==0 else 64 if x+32>=w else 32
                sy=0 if y==0 else 64 if y+32>=h else 32
                out.alpha_composite(im.crop((sx,sy,sx+32,sy+32)),(x,y))
        return out
    def setup_props(self):
        self.prop('books',INTERIOR,(32,192,64,256))
        self.prop('cabinet',INTERIOR,(0,192,32,256))
        # Service counters occupy a single collision row. Tall atlas furniture
        # would incorrectly hide people standing in the walkable row behind it.
        counter=Image.new('RGBA',(128,48))
        for xx in range(0,128,32):counter.alpha_composite(self.tile(BASE+'/tiles/cabinets.png',0,96),(xx,16))
        top=self.crop(BASE+'/tiles/cabinets.png',(64,256,128,272))
        counter.alpha_composite(top,(0,0));counter.alpha_composite(top,(64,0))
        counter.alpha_composite(self.crop(INTERIOR,(224,96,256,112)),(52,0));self.props['desk']=counter
        self.prop('table',MARKET,(160,544,256,608))
        self.prop('chair',BASE+'/tiles/victoria.png',(160,0,192,64))
        self.prop('seat',BASE+'/tiles/victoria.png',(160,0,192,32))
        self.prop('bed',BASE+'/tiles/victoria.png',(64,0,128,96))
        self.prop('plant',GARDEN,(128,320,160,384))
        self.prop('flowers',GARDEN,(64,416,128,448))
        self.prop('flowers-small',GARDEN,(160,320,192,384))
        self.prop('bench',MARKET,(192,416,256,480))
        self.prop('gazebo',GARDEN,(320,0,416,144))
        self.prop('fountain',GARDEN,(288,1568,384,1632))
        self.prop('board',STREETS,(224,832,256,896))
        self.prop('mirror',INTERIOR,(224,224,256,256))
        self.prop('kitchen',INTERIOR,(64,96,160,160))
        self.prop('lamp',STREETS,(96,544,128,672))
        self.prop('statue',GARDEN,(0,272,32,384))
        tree=Image.new('RGBA',(96,128));tree.alpha_composite(self.crop(BASE+'/tiles/trunk.png',(0,0,96,96)),(0,32));tree.alpha_composite(self.crop(BASE+'/tiles/treetop.png',(0,0,96,96)),(0,0));self.props['tree']=tree
        for i in range(4):
            stall=Image.new('RGBA',(128,128));sd=ImageDraw.Draw(stall)
            for xx in [18,107]:
                sd.rectangle((xx,40,xx+4,122),fill='#65523c');sd.line((xx+1,42,xx+1,120),fill='#b59662')
            # Complete fabric canopy from the atlas, with native weave/shading.
            tent=self.crop(MARKET,(384,704,480,800))
            tent=self.recolor(tent,['#72969e','#b87673','#839469','#c5a36a'][i],preserve_dark=True)
            for xx in [16,48,80]:stall.alpha_composite(self.tile(BASE+'/tiles/cabinets.png',32,256),(xx,91))
            stall.alpha_composite(self.crop(INTERIOR,(192,192,256,224)),(36,76));stall.alpha_composite(tent,(16,0));self.props[f'stall-{i}']=stall
        for i,color in enumerate(['#5e737d','#a77761','#768763','#93697e','#637b83','#a39268']):
            for wide in [4,5]:
                wall=self.nine(self.crop(MANSION,(0,(i%4)*256,96,(i%4)*256+96)),wide*T,96)
                wall=self.recolor(wall,color,preserve_dark=True)
                house=Image.new('RGBA',(wide*T,128));house.alpha_composite(wall,(0,32))
                roof=Image.new('RGBA',(wide*T,64))
                for yy in range(2):
                    for xx in range(wide):
                        sx=0 if xx==0 else 64 if xx==wide-1 else 32
                        roof.alpha_composite(self.crop(BASE+'/tiles/house.png',(sx,96+yy*32,sx+32,128+yy*32)),(xx*T,yy*T))
                house.alpha_composite(self.recolor(roof,color,preserve_dark=True),(0,0))
                door=self.crop(DOORS,(16,544,48,608));house.alpha_composite(door,(64,64))
                window=self.crop(BASE+'/tiles/house.png',(256,0,288,64));house.alpha_composite(window,(16,64));house.alpha_composite(window,((wide-1)*T-16,64))
                # Decorative dormer is an actual LPC architectural crop.
                dormer=self.crop(MANSION,(352,(i%4)*256,416,(i%4)*256+64));house.alpha_composite(dormer,(wide*T//2-32,0))
                self.props[f'house-{wide}-{i}']=house
        for color in ['cream','sage','navy','rose','lavender','black']:
            self.props[f'rack-{color}']=self.clothes_rack(color)
        # Small framed landscapes are cropped from the licensed garden scene.
        for i in range(4):
            picture=Image.new('RGBA',(64,64));d=ImageDraw.Draw(picture);d.rectangle((0,0,63,63),fill='#564235');d.rectangle((3,3,60,60),fill='#cbb58a');d.rectangle((6,6,57,57),fill=['#aec4be','#d3bd99','#9cafa1','#bca1ac'][i])
            patch=self.crop(GARDEN,(224+96*(i%2),576,320+96*(i%2),672)).resize((46,46),Image.Resampling.NEAREST)
            picture.alpha_composite(patch,(9,9));self.props[f'art-{i}']=picture
        screen=Image.new('RGBA',(320,96));d=ImageDraw.Draw(screen)
        for inset,c in [(0,'#342e35'),(3,'#6c6061'),(7,'#231f29'),(10,'#adc0b8')]:d.rectangle((inset,inset,319-inset,95-inset),fill=c)
        for y in range(12,84):
            d.line((12,y,307,y),fill=(int(139+y*.3),int(163+y*.25),int(165+y*.16)))
        for x,y in [(80,45),(170,35),(235,47)]:
            patch=self.props['tree'].resize((48,64),Image.Resampling.NEAREST);screen.alpha_composite(patch,(x,y))
        d.rectangle((11,83,308,84),fill='#d9d9c5');self.props['screen']=screen
        # Atlas cells often include padding. Trim it so the visible base, rather
        # than the atlas margin, sits on the server's object/collision cell.
        self.props={name:im.crop(im.getbbox()) if im.getbbox() else im for name,im in self.props.items()}

    def clothes_rack(self,color):
        colors={'cream':'#d9c7a2','sage':'#78977b','navy':'#526781','rose':'#b17d86','lavender':'#9d8aac','black':'#43484f'}
        im=Image.new('RGBA',(96,80));d=ImageDraw.Draw(im)
        # Timber/metal rack, detailed garment sprites rather than solid blocks.
        d.line((5,76,5,8,90,8,90,76),fill='#4e4640',width=3);d.line((6,9,89,9),fill='#c4b195',width=1)
        source=self.img('characters/spritesheets/torso/clothes/longsleeve/longsleeve2_cardigan/female/walk.png').crop((16,128+24,48,128+48))
        source=self.recolor(source,colors[color])
        for x in [9,34,59]:
            d.line((x+14,13,x+14,20,x+4,25,x+25,25,x+14,20),fill='#aa8f69',width=1)
            im.alpha_composite(source,(x,22));d.line((x+4,55,x+26,55),fill='#91816d')
        d.rectangle((0,75,95,79),fill='#806c55');d.line((1,75,94,75),fill='#c6b493')
        return im

    def recolor(self,im,color,preserve_dark=False):
        im=im.copy();target=rgba(color);data=[]
        for r,g,b,a in im.get_flattened_data():
            if not a:data.append((r,g,b,a));continue
            lum=(r*.299+g*.587+b*.114)/255
            if preserve_dark and lum<.15:data.append((r,g,b,a));continue
            # Hue changes keep the artist's six-level light/shadow structure.
            if lum<.16:new=tuple(round(c*.34) for c in target)
            elif lum<.38:new=tuple(round(c*.55) for c in target)
            elif lum<.6:new=tuple(round(c*.78) for c in target)
            elif lum<.78:new=target
            elif lum<.94:new=tuple(round(c*.78+255*.22) for c in target)
            else:new=tuple(round(c*.56+255*.44) for c in target)
            data.append((*new,a))
        im.putdata(data);return im

    def floor(self,m,key):
        out=Image.new('RGBA',(m['width']*T,m['height']*T));d=ImageDraw.Draw(out)
        outdoor=key in ['shared','district','zoo','park','market']
        grass=self.tile(BASE+'/tiles/grass.png',32,160);stone=self.tile(INTERIOR,32,128)
        plank=ImageEnhance.Color(self.tile(BASE+'/tiles/inside.png',0,128)).enhance(.65);plank=ImageEnhance.Brightness(plank).enhance(1.2);checker=self.tile(INTERIOR,0,128)
        if key=='gallery':plank=checker
        if key=='cinema':plank=self.recolor(plank,'#6a5b68',True)
        if key=='boutique':plank=ImageEnhance.Color(plank).enhance(.55)
        for y,row in enumerate(m['ground']):
            for x,g in enumerate(row):
                tile=(stone if g in [25,43] else grass) if outdoor else plank
                out.alpha_composite(tile,(x*T,y*T))
        if not outdoor:
            wall=self.crop(BASE+'/tiles/inside.png',(0,0,96,96));palette={'library':'#67785f','cafe':'#91a69a','gallery':'#c8c0aa','cinema':'#615b70','restaurant':'#b28c74','boutique':'#b0aaa0'}
            wall=self.recolor(wall,palette.get(key,'#91a4a0'),True)
            for x in range(m['width']):
                # A single-cell back wall: rows 1 and 2 are walkable in the
                # authoritative maps, so art must never disguise them as wall.
                out.alpha_composite(wall.crop((32,32,64,64)),(x*T,0))
                trim=wall.crop((32,64,64,72));out.alpha_composite(trim,(x*T,24))
            # Side skirting stays inside existing one-cell collision borders.
            for y in range(1,m['height']):
                out.alpha_composite(wall.crop((0,32,32,64)),(0,y*T));out.alpha_composite(wall.crop((64,32,96,64)),((m['width']-1)*T,y*T))
            for x in range(m['width']):out.alpha_composite(wall.crop((32,64,64,96)),(x*T,(m['height']-1)*T))
            for p in m['portals']:
                out.alpha_composite(plank,(p['x']*T,p['y']*T));out.alpha_composite(plank,(p['x']*T,(m['height']-1)*T))
            # Woven rug with a thin patterned border; no extra obstacles.
            if key.startswith('room-'):rx,ry,rw,rh=7,8,6,3
            else:rx,ry,rw,rh=11,12,6,4
            tint=['#baa789','#a8b3a4','#b6a5a5','#9dabb0'][int(key[-2:])%4 if key.startswith('room-') else 0]
            d.rectangle((rx*T,ry*T,(rx+rw)*T-1,(ry+rh)*T-1),fill=tint)
            for inset,c in [(2,'#685d55'),(4,'#d7c6a2'),(7,'#77685e'),(9,tint)]:d.rectangle((rx*T+inset,ry*T+inset,(rx+rw)*T-inset-1,(ry+rh)*T-inset-1),outline=c,width=1)
            for yy in range(ry*T+13,(ry+rh)*T-12,4):
                for xx in range(rx*T+13,(rx+rw)*T-12,6):d.point((xx+(yy%8)//4,yy),fill='#d0c2ad')
        else:
            # Native-texture verges on unreachable border tiles.
            for x,y in m['blocked']:
                if (x in [0,m['width']-1] or y in [0,m['height']-1]) and key!='shared':
                    d.line((x*T,y*T+28,x*T+31,y*T+28),fill='#56794b',width=2)
        return out

    def map(self,key,m):
        out=self.floor(m,key);decor=[];assigned=set()
        if key in ['shared','district']:
            for i,p in enumerate(p for p in m['portals'] if p['to'].startswith('room-') or p['to'] in ['library','cafe','zoo','gallery','cinema','restaurant']):
                wide=4 if key=='shared' else 5;x=p['x']-2;y=p['y']-3
                self.add(decor,f'house-{wide}-{i%6}',x*T,y*T,(p['y']+1)*T)
                for yy in range(y,y+4):
                    for xx in range(x,x+wide):assigned.add((xx,yy))
                if key=='district':
                    # Exterior lanterns flank each front door.
                    self.add(decor,'lamp',(x-1)*T,(y+1)*T,(y+4)*T)
            for x,y in m['blocked']:
                if (x,y) in assigned:continue
                if key=='shared' and (x,y) not in [(16,12),(17,12),(18,12),(21,14),(14,15),(22,16)]:self.centered(decor,'tree',x,y)
            if key=='shared':
                self.centered(decor,'bench',17,12);self.centered(decor,'fountain',21,14);self.centered(decor,'flowers-small',14,15);self.centered(decor,'flowers-small',22,16)
            else:
                for x,y in [(4,4),(4,21),(36,16),(17,3),(28,18)]:
                    # Small movable planters are visual trim, not new collision.
                    self.centered(decor,'plant',x,y)
        elif key.startswith('room-'):
            self.centered(decor,'desk',6,5);self.centered(decor,'bed',14,5);self.centered(decor,'plant',15,9)
            self.centered(decor,'cabinet',3,3)
            self.centered(decor,'chair',6,6)
        for p in m.get('props',[]):
            kind=p['kind'];x=p['x'];y=p['y']
            if kind=='books':
                # One tall case per two blocked cells, preserving all aisles.
                if y%2==1:self.centered(decor,'books',x,y)
            elif kind in ['desk','counter']:
                if kind=='counter' and key in ['cafe','restaurant']:
                    piece=self.tile(INTERIOR,96 if x%3!=0 else 128,96)
                    name='counter-'+str(x%3)
                    if name not in self.props:self.props[name]=piece
                    self.add(decor,name,x*T,y*T,(y+1)*T)
                else:self.centered(decor,'desk',x,y)
            elif kind=='clothesrack':
                color=['cream','sage','navy','rose','lavender','black'][sum(1 for q in m['props'][:m['props'].index(p)] if q['kind']=='clothesrack')]
                self.centered(decor,'rack-'+color,x,y)
            elif kind=='table':self.centered(decor,'table',x,y)
            elif kind=='art':self.centered(decor,f'art-{x%4}',x,y)
            elif kind=='sculpture':self.centered(decor,'statue',x,y)
            elif kind=='screen':self.centered(decor,'screen',x,y)
            elif kind=='marketboard':self.centered(decor,'board',x,y)
            elif kind=='flowerbed':self.centered(decor,'flowers',x,y)
            elif kind=='stall':self.centered(decor,f'stall-{p["index"]%4}',x,y)
            elif kind=='pond':
                # Exactly the original impassable pond footprint: 9 x 12 cells.
                water=self.tile(BASE+'/tiles/water.png',32,160)
                for yy in range(4,16):
                    for xx in range(27,36):out.alpha_composite(water,(xx*T,yy*T))
                dd=ImageDraw.Draw(out);dd.rectangle((27*T,4*T,36*T-1,16*T-1),outline='#a19c76',width=5)
            elif kind=='habitat':
                # Clear zoo pen outlines and textured natural terrain.
                dd=ImageDraw.Draw(out);dd.rounded_rectangle(((x-2)*T,(y-1)*T,(x+3)*T,(y+2)*T),radius=12,outline='#9b8359',width=4)
                self.centered(decor,'tree',x+1,y-1)
                # Preserve the established animal icon until a matching licensed
                # animal sheet is sourced; texture and pen art are now LPC.
                name='animal-'+{'熊貓':'panda','長頸鹿':'giraffe','企鵝':'penguin','象':'elephant'}.get(p['animal'],'elephant');self.props[name]=self.animal(p['animal']);self.centered(decor,name,x,y)
            elif kind in ['bench','tree','gazebo','seat','mirror']:self.centered(decor,kind,x,y)
        # Soft golden pools around street lamps are cached, never model calls.
        for p in m['portals']:
            if p['to'].startswith('room-') or key.startswith('room-') or key=='district':
                d=ImageDraw.Draw(out);d.line((p['x']*T+6,(p['y']+1)*T-2,p['x']*T+25,(p['y']+1)*T-2),fill='#dfcea2',width=2)
        out.save(self.target/f'lpc-map-{key}.png',optimize=True)
        self.scenes[key]={'background':f'/assets/lpc-map-{key}.png','decor':decor}

    def animal(self,name):
        # Existing native pixel icons re-authored with outlines and shading.
        im=Image.new('RGBA',(64,64));d=ImageDraw.Draw(im)
        if name=='熊貓':
            for box in [(15,13,25,24),(38,13,48,24),(16,42,29,61),(36,42,48,61)]:d.ellipse(box,fill='#303c3c')
            d.ellipse((13,19,50,54),fill='#303c3c');d.ellipse((18,22,46,51),fill='#e6e4cf');d.ellipse((19,17,46,40),fill='#efeedb')
            for x in [22,35]:d.ellipse((x,25,x+8,32),fill='#3b4543');d.point((x+4,27),fill='#fffbea')
            d.ellipse((29,32,34,36),fill='#354342')
        elif name=='長頸鹿':
            d.rectangle((13,32,44,48),fill='#d1ac61');d.rectangle((35,9,44,43),fill='#d1ac61');d.ellipse((32,3,53,17),fill='#dbb66d');d.rectangle((16,45,21,61),fill='#ab8548');d.rectangle((38,45,43,61),fill='#ab8548')
            for x,y in [(20,34),(29,40),(35,23),(39,11)]:d.ellipse((x,y,x+4,y+5),fill='#9c7244')
            d.point((48,8),fill='#363b36')
        elif name=='企鵝':
            d.ellipse((20,8,45,58),fill='#303f48');d.ellipse((25,24,40,55),fill='#e5e4d4');d.polygon([(39,18),(52,22),(39,27)],fill='#dcad61');d.ellipse((20,54,31,60),fill='#cf9e57');d.ellipse((35,54,47,60),fill='#cf9e57');d.point((38,16),fill='#ece6cf')
        else:
            d.ellipse((7,19,48,50),fill='#8b9996');d.ellipse((34,14,59,43),fill='#a6ada5');d.ellipse((28,14,46,40),fill='#859591');d.rectangle((10,43,18,59),fill='#758885');d.rectangle((38,41,46,59),fill='#758885');d.line((54,34,53,54,47,58),fill='#a6ada5',width=8);d.point((51,23),fill='#394644')
        return im

    def characters(self,clothes):
        prefix='characters/spritesheets/'
        used_layers=set()
        def layer(f,color=None):
            used_layers.add(f);im=self.img(prefix+f)
            return self.recolor(im,color) if color else im
        variants={}
        for i in range(11):
            ident=f'member-{i+1:02d}' if i<10 else 'player';variants[ident]=[]
            initial={'id':'original','palette':{'top':TOP_COLORS[i],'bottom':'#525f64'},'shape':'dress' if i in [3,8] else 'original'}
            for item in [initial]+clothes:
                im=Image.new('RGBA',(576,256))
                hairstyle=HAIR[i]
                if hairstyle=='ponytail':im.alpha_composite(layer('hair/ponytail/adult/bg/walk.png',HAIR_COLORS[i]))
                for f in ['body/bodies/female/walk.png','head/heads/human/female/walk.png']:im.alpha_composite(layer(f))
                bottom='legs/skirts/plain/thin/walk.png' if item['shape']=='dress' else 'legs/pants/thin/walk.png'
                im.alpha_composite(layer(bottom,item['palette']['bottom']));im.alpha_composite(layer('feet/shoes/revised/thin/walk.png','#4a4547'))
                shirt='longsleeve2_cardigan' if item['shape']=='cardigan' or i in [1,6,8] and item['id']=='original' else 'longsleeve2_buttoned' if item['shape']=='blazer' else 'longsleeve2'
                im.alpha_composite(layer(f'torso/clothes/longsleeve/{shirt}/female/walk.png',item['palette']['top']))
                hairpath=f'hair/{hairstyle}/adult/'+('fg/' if hairstyle=='ponytail' else '')+'walk.png'
                im.alpha_composite(layer(hairpath,HAIR_COLORS[i]))
                d=ImageDraw.Draw(im)
                # Existing identity accessories follow their owners, all frames.
                for row in range(4):
                    for frame in range(9):
                        xx=frame*64;yy=row*64
                        if i in [1,9] and row==2:
                            d.rectangle((xx+25,yy+23,xx+30,yy+26),outline='#3c4146');d.rectangle((xx+33,yy+23,xx+38,yy+26),outline='#3c4146');d.line((xx+30,yy+24,xx+33,yy+24),fill='#3c4146')
                        if i==8:d.ellipse((xx+36,yy+17,xx+40,yy+21),fill='#e3ca86');d.point((xx+38,yy+19),fill='#b5945f')
                file=f'lpc-{ident}-{item["id"]}.png';im.save(self.target/file,optimize=True)
                # Keep portraits tied to the actual public outfit, not ownership.
                portrait=im.crop((12,128+4,52,192));portrait.save(self.target/f'lpc-{ident}-{item["id"]}-portrait.png',optimize=True)
                variants[ident].append(item['id'])
        self.used_layers=used_layers;self.variants=variants

    def credits(self):
        files=[BASE+'/CREDITS.TXT','interior/LPC_house_interior/credits.txt','buildings/lpc-victorian-buildings/CREDITS-victorian.txt','decoration/lpc-victorian-decoration/CREDITS-decorations-victorian.txt']
        sections=['LPC art used in 午後共居 v0.10\n\nWorld artwork: original tiles from the four sources below, composed/cropped/recolored by this project. Map compositions are distributed under CC BY-SA 4.0.\nCharacter layers: selected OGA-BY 3.0 / CC0 alternatives where offered; CC BY-SA 4.0 for layers without OGA-BY. Composite edits are distributed under CC BY-SA 4.0. No authors endorse this game.\nChanges: native 32px tile composition, recoloring, atlas cropping, eleven character identities and outfit previews. Zoo animal icons, rugs and engine are project-authored.\nhttps://creativecommons.org/licenses/by-sa/4.0/\nhttps://static.opengameart.org/OGA-BY-3.0.txt\n']
        for f in files:sections.append('\n=== '+f+' ===\n'+(self.source/f).read_text(encoding='utf8',errors='replace'))
        rows=[r for r in csv.DictReader((self.source/'characters/CREDITS.csv').open(encoding='utf8')) if r['filename'] in self.used_layers]
        assert len(rows)==len(self.used_layers), 'A character layer is missing attribution'
        sections.append('\n=== Selected character layers ===\nhttps://github.com/LiberatedPixelCup/Universal-LPC-Spritesheet-Character-Generator\n')
        for row in rows:sections.append('\n'.join(f'{k}: {v}' for k,v in row.items())+'\n')
        text='\n'.join(sections);(self.target/'LPC-CREDITS.txt').write_text(text,encoding='utf8')
        return text

def main():
    p=argparse.ArgumentParser();p.add_argument('--source',type=Path,required=True);p.add_argument('--project',type=Path,required=True);p.add_argument('--target',type=Path,required=True);args=p.parse_args()
    assets=args.target/'prototype/web/assets';assets.mkdir(parents=True,exist_ok=True)
    maps=args.project/'prototype/web/assets/maps.json';before=digest(maps);spec=json.loads(maps.read_text('utf8'));clothes=json.loads((args.project/'prototype/data/clothing.json').read_text('utf8'))['items']
    c=Composer(args.source,assets);c.setup_props()
    for k,m in spec['maps'].items():c.map(k,m)
    c.characters(clothes)
    for key,im in c.props.items():im.save(assets/f'lpc-prop-{key}.png',optimize=True)
    credits=c.credits();manifest={'tile_size':32,'frame_size':64,'walk_frames':9,'scenes':c.scenes,'variants':c.variants}
    (args.target/'art-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False),encoding='utf8')
    template=args.target/'tools/lpc-engine-template.js'
    if template.exists():
        source=template.read_text('utf8');assert '/*ART_MANIFEST*/' in source
        (args.target/'prototype/web/engine.js').write_text(source.replace('/*ART_MANIFEST*/',json.dumps(manifest,ensure_ascii=False)),encoding='utf8')
    assert before==digest(maps),'Collision maps must not change during the art build'
    report={'version':'0.10','map_count':len(c.scenes),'character_count':len(c.variants),'outfit_variants':sum(map(len,c.variants.values())),'native_tile_size':32,'sprite_frame_size':64,'walk_frames':9,'collision_maps_sha256':before,'source_files':{f:digest(args.source/f) for f in sorted(c.used)},'api_calls':0}
    (args.target/'art-build-report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
    print(json.dumps({k:v for k,v in report.items() if k!='source_files'},ensure_ascii=True))
    # Reproducible originals and exact notices, separated from the web route.
    source_dest=args.target/'art-sources';source_dest.mkdir(exist_ok=True)
    for f in sorted(c.used):
        dest=source_dest/f;dest.parent.mkdir(parents=True,exist_ok=True)
        if (args.source/f).resolve()!=dest.resolve():shutil.copyfile(args.source/f,dest)
    for f in [BASE+'/CREDITS.TXT','interior/LPC_house_interior/credits.txt','buildings/lpc-victorian-buildings/CREDITS-victorian.txt','decoration/lpc-victorian-decoration/CREDITS-decorations-victorian.txt','characters/CREDITS.csv','sources.json']:
        dest=source_dest/f;dest.parent.mkdir(parents=True,exist_ok=True)
        if (args.source/f).resolve()!=dest.resolve():shutil.copyfile(args.source/f,dest)

if __name__=='__main__':main()
