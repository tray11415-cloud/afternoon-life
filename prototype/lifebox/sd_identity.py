"""Appearance-neutral OpenPose guides; no LPC hair or clothing enters diffusion."""
import io

VERSION=2

def pose_image(direction,frame,width=512,height=512):
 from PIL import Image,ImageDraw
 if direction not in {'up','down','left','right'} or frame not in range(3):raise ValueError('無效方向或步伐')
 image=Image.new('RGB',(width,height),'black');draw=ImageDraw.Draw(image)
 points=[(256,84),(256,135),(211,143),(199,224),(198,289),(301,143),(313,224),(314,289),(228,295),(219,373),(216,468),(284,295),(293,373),(296,468),(243,78),(269,78),(232,83),(280,83)]
 if direction=='up':points=[None if i in (0,14,15,16,17) else p for i,p in enumerate(points)]
 if direction in ('left','right'):
  sign=-1 if direction=='left' else 1;points=[(256+(x-256)*.28,y) for x,y in points];points[0]=(256+sign*16,84)
  for i in ((15,17) if direction=='left' else (14,16)):points[i]=None
 if frame:
  step=1 if frame==1 else -1
  for i in (3,4,9,10):
   if points[i]:x,y=points[i];points[i]=(x-(40 if i==10 else 22 if i==9 else 18)*step,y-(30 if i==10 else 18 if i==9 else 12)*step)
  for i in (6,7,12,13):
   if points[i]:x,y=points[i];points[i]=(x+(40 if i==13 else 22 if i==12 else 18)*step,y+(8 if i in (12,13) else 12)*step)
 points=[(p[0]*width/512,p[1]*height/512) if p else None for p in points]
 colors=[(255,0,0),(255,85,0),(255,170,0),(255,255,0),(170,255,0),(85,255,0),(0,255,0),(0,255,85),(0,255,170),(0,255,255),(0,170,255),(0,85,255),(0,0,255),(85,0,255),(170,0,255),(255,0,255),(255,0,170),(255,0,85)]
 limbs=[(1,2),(1,5),(2,3),(3,4),(5,6),(6,7),(1,8),(8,9),(9,10),(1,11),(11,12),(12,13),(1,0),(0,14),(14,16),(0,15),(15,17)]
 for n,(a,b) in enumerate(limbs):
  if points[a] and points[b]:draw.line((points[a],points[b]),fill=colors[n],width=max(2,round(width*7/512)))
 radius=max(2,round(width*5/512))
 for i,p in enumerate(points):
  if p:draw.ellipse((p[0]-radius,p[1]-radius,p[0]+radius,p[1]+radius),fill=colors[i])
 output=io.BytesIO();image.save(output,format='PNG');return output.getvalue()

def identity_canvas(raw,width,height):
 from PIL import Image
 image=Image.open(io.BytesIO(raw)).convert('RGBA');image.thumbnail((round(width*.85),round(height*.94)),Image.Resampling.LANCZOS)
 result=Image.new('RGB',(width,height),'white');result.paste(image,((width-image.width)//2,height-image.height),image)
 output=io.BytesIO();result.save(output,format='PNG');return output.getvalue()

def align_clothes_palette(frame,reference):
 """Conservative main garment color alignment; leaves white, black and face alone.

 Multi-color/low-saturation garments are left unchanged. This postprocess is
 optional and never claims semantic segmentation or exact outfit recovery.
 """
 import colorsys,statistics
 def dominant(image):
  bounds=image.getbbox()
  if not bounds:return None
  body=image.crop(bounds);body.thumbnail((96,128));w,h=body.size;values=[]
  for y in range(round(h*.25),round(h*.80)):
   for x in range(w):
    r,g,b,a=body.getpixel((x,y))
    if a<200:continue
    hue,s,v=colorsys.rgb_to_hsv(r/255,g/255,b/255)
    if s>.30 and .12<v<.82:values.append((hue,s,v))
  if len(values)<24:return None
  bins={}
  for h,s,v in values:bins[round(h*36)%36]=bins.get(round(h*36)%36,0)+1
  center=max(bins,key=bins.get)/36
  cluster=[v for v in values if min(abs(v[0]-center),1-abs(v[0]-center))<.055]
  if len(cluster)<len(values)*.65:return None
  return tuple(statistics.median(v[i] for v in cluster) for i in range(3))
 src=dominant(reference);dst=dominant(frame)
 if not src or not dst:return frame
 result=frame.copy();bounds=frame.getbbox();x0,y0,x1,y1=bounds;dh=((src[0]-dst[0]+.5)%1)-.5;ds=max(-.25,min(.25,src[1]-dst[1]));dv=max(-.25,min(.25,src[2]-dst[2]))
 pixels=result.load()
 for y in range(y0+round((y1-y0)*.23),y0+round((y1-y0)*.88)):
  for x in range(x0,x1):
   r,g,b,a=pixels[x,y];h,s,v=colorsys.rgb_to_hsv(r/255,g/255,b/255)
   if a>=200 and s>.30 and .10<v<.88 and min(abs(h-dst[0]),1-abs(h-dst[0]))<.075:
    rr,gg,bb=colorsys.hsv_to_rgb((h+dh)%1,max(0,min(1,s+ds)),max(0,min(1,v+dv)));pixels[x,y]=(round(rr*255),round(gg*255),round(bb*255),a)
 return result
