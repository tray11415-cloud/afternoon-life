"""Clothed LPC character previews and SD identity notes; no world writes."""
import copy,hashlib,json,re,threading
from pathlib import Path
from PIL import Image,ImageChops,ImageColor

HAIRS={'short':'短髮','pixie':'精靈短髮','bob':'鮑伯頭','long':'長直髮','curly':'長捲髮','bun':'髮髻','side_bob':'側分短髮','wavy':'波浪長髮'}
BUILDS={'slim':'纖細','average':'勻稱','athletic':'健美','curvy':'豐盈'}
FACES={'soft':'柔和','oval':'橢圓','angular':'俐落'}
START_HAIR=['short','long','bob','curly','pixie','short','bun','wavy','side_bob','bob','pixie']
HAIR_COLORS=['#684536','#283746','#64547a','#aa6745','#30313a','#a75c46','#795238','#292b34','#687147','#574548','#49544f']
TOP_COLORS=['#ae624b','#667f9c','#9275a3','#7a9577','#c0a65d','#648b9f','#ccb994','#b27980','#829167','#6d8d9b','#71889c']
def default_look(actor='player'):
 i=int(actor[-2:])-1 if actor.startswith('member-') else 10
 return {'enabled':False,'hair':START_HAIR[i],'hair_color':HAIR_COLORS[i],'skin_color':'#dfad89','eye_color':'#684536','face':'soft','height':170,'build':'average','top_color':TOP_COLORS[i],'bottom_color':'#525f64'}
def validate_look(value,actor='player'):
 if value is None:return default_look(actor)
 default=default_look(actor)
 if not isinstance(value,dict) or set(value)!=set(default):raise ValueError('外觀設定欄位不符')
 if type(value['enabled']) is not bool or value['hair'] not in HAIRS or value['build'] not in BUILDS or value['face'] not in FACES:raise ValueError('外觀類型不合適')
 if type(value['height']) is not int or not 150<=value['height']<=205:raise ValueError('身高需為150–205公分')
 for key in ('hair_color','skin_color','eye_color','top_color','bottom_color'):
  if not isinstance(value[key],str) or not re.fullmatch(r'#[a-fA-F0-9]{6}',value[key]):raise ValueError('顏色需為六位色碼')
 return copy.deepcopy(value)
def look_prompt(look):
 if not look or not look.get('enabled'):return ''
 p=validate_look(look)
 hair={'short':'short hair','pixie':'pixie haircut','bob':'bob haircut','long':'long straight hair','curly':'long curly hair','bun':'hair bun','side_bob':'side-parted bob','wavy':'long wavy hair'}[p['hair']]
 return f"{color_name(p['hair_color'])} {hair}, {skin_name(p['skin_color'])} skin, {color_name(p['eye_color'])} eyes, {p['face']} face, {p['build']} adult build, height {p['height']} cm"
def nearest_color(value,table):
 rgb=ImageColor.getrgb(value)
 return min(table,key=lambda k:sum((a-b)**2 for a,b in zip(rgb,ImageColor.getrgb(table[k]))))
def color_name(value):
 return nearest_color(value,{'black':'#25252c','dark brown':'#604533','auburn':'#a46042','blond':'#cfb370','silver':'#bac5cf','blue':'#456b9e','green':'#568369','purple':'#78659b','rose':'#b97584','white':'#e4dfd7','charcoal gray':'#525f64'})
def skin_name(value):return nearest_color(value,{'fair ivory':'#f4dcc2','warm beige':'#dfad89','tan':'#b98662','deep brown':'#77553f'})
def tint(im,color):
 target=ImageColor.getrgb(color);data=[]
 for r,g,b,a in (im.get_flattened_data() if hasattr(im,'get_flattened_data') else im.getdata()):
  lum=(r*.299+g*.587+b*.114)/255
  if not a:data.append((r,g,b,a));continue
  if lum<.16:new=tuple(round(c*.34) for c in target)
  elif lum<.38:new=tuple(round(c*.55) for c in target)
  elif lum<.6:new=tuple(round(c*.78) for c in target)
  elif lum<.78:new=target
  elif lum<.94:new=tuple(round(c*.78+255*.22) for c in target)
  else:new=tuple(round(c*.56+255*.44) for c in target)
  data.append((*new,a))
 result=im.copy();result.putdata(data);return result

class LookStudio:
 def __init__(self,session):
  self.session=session;self.root=session.root/'look-art';self.root.mkdir(exist_ok=True);self.static=Path(__file__).parents[1]/'web/assets';self.lock=threading.RLock();self.images={}
 def source(self,name):
  path=self.static/name
  if self.session.components and 'art:'+name in self.session.components.base:
   data=self.session.components.get('art:'+name)
   if data.get('url','').startswith('/component-art/'):path=self.session.components.root/data['file']
  if not path.is_file():raise ValueError('缺少人物預覽圖層')
  stat=path.stat();stamp=(str(path),stat.st_mtime_ns,stat.st_size)
  if stamp in self.images:return self.images[stamp]
  with Image.open(path) as im:
   if im.size!=(576,256):raise ValueError('人物圖層需為576×256')
   im.load();image=im.convert('RGBA')
  value=(image,hashlib.sha256(path.read_bytes()).hexdigest());self.images[stamp]=value;return value
 def render(self,actor,profile,outfit):
  look=validate_look(profile.get('look'),actor)
  if not look['enabled']:return {}
  gender=profile.get('gender','male' if actor=='player' else 'female');shape='swim' if outfit['id'] in {'swim-onepiece','swim-trunks'} else 'cardigan' if 'cardigan' in outfit['id'] else 'buttoned' if 'blazer' in outfit['id'] else 'plain'
  names=[f'look-base-{gender}-{shape}.png',f'look-skin-{gender}-{shape}.png',f'look-top-{gender}-{shape}.png',f'look-bottom-{gender}-{shape}.png',f'look-hair-{look["hair"]}.png']
  with self.lock:
   images=[];hashes=[]
   for name in names:
    im,sha=self.source(name);images.append(im);hashes.append(sha)
   palette=dict(outfit['palette'])
   if outfit['id']=='original':palette={'top':look['top_color'],'bottom':look['bottom_color']}
   key=hashlib.sha256(json.dumps({'actor':actor,'look':look,'gender':gender,'outfit':outfit['render_key'],'palette':palette,'sources':hashes},sort_keys=True).encode()).hexdigest()
   sheet=self.root/(key+'-sprite.png');portrait=self.root/(key+'-portrait.png')
   if not sheet.is_file() or not portrait.is_file():
    base=images[0]
    for mask,color in zip(images[1:4],[look['skin_color'],palette['top'],palette['bottom']]):
     coloured=tint(base,color);base=Image.composite(coloured,base,mask.getchannel('A'))
    base.alpha_composite(tint(images[4],look['hair_color']))
    xscale={'slim':.9,'average':1,'athletic':1.07,'curvy':1.06}[look['build']];yscale=max(.9,min(1.08,look['height']/170))
    result=Image.new('RGBA',(576,256))
    for row in range(4):
     for frame in range(9):
      piece=base.crop((frame*64,row*64,frame*64+64,row*64+64));box=piece.getbbox()
      if box:
       body=piece.crop(box);body=body.resize((max(1,round(body.width*xscale)),max(1,min(60,round(body.height*yscale)))),Image.Resampling.NEAREST)
       result.alpha_composite(body,(frame*64+32-body.width//2,row*64+60-body.height))
    result.save(sheet);result.crop((12,132,52,192)).save(portrait)
   return {'sprite':'/look-art/'+sheet.name,'portrait':'/look-art/'+portrait.name,'frames':9}
 def preview(self,actor,profile):
  p=copy.deepcopy(profile);p['look']=validate_look(p.get('look'),actor)
  outfit=self.session.wardrobe.appearance(actor)
  if not p['look']['enabled']:
   art=self.session.studio.appearance(actor,outfit);art.update(self.session.art_assets.appearance(actor,outfit,'neutral'))
   key=outfit['id'] if (self.static/f'lpc-{actor}-{outfit["id"]}.png').is_file() else 'original'
   return {'sprite':art.get('sprite',f'/assets/lpc-{actor}-{key}.png'),'portrait':art.get('portrait',f'/assets/lpc-{actor}-{key}-portrait.png'),'frames':art.get('frames',9),'preview_only':True,'look':p['look'],'sd_identity':''}
  return {**self.render(actor,p,outfit),'sd_identity':look_prompt(p['look']),'preview_only':True,'look':p['look']}
 def asset(self,name):
  if not re.fullmatch(r'[a-f0-9]{64}-(?:sprite|portrait)\.png',name):return None
  path=self.root/name;return path if path.is_file() else None
