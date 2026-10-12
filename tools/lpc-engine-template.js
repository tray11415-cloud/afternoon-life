/* LPC native-resolution renderer. Server remains authoritative for all actions,
   collision, ownership, NPCs and saves. Art credits are bundled with the game. */
const LPC_ART=/*ART_MANIFEST*/;
window.PixelLife=class PixelLife {
  constructor(canvas,onAction,onPick,onInteract){
    this.canvas=canvas;this.ctx=canvas.getContext('2d');this.ctx.imageSmoothingEnabled=false;
    this.onAction=onAction;this.onPick=onPick;this.onInteract=onInteract;
    this.images=new Map();this.loading=new Map();this.entities=new Map();this.keys=new Set();
    this.zoom=1;this.tileSize=LPC_ART.tile_size;this.camera={x:0,y:0};this.selected=null;this.paused=false;
    this.lastInput=0;this.ready=false;this.lastFrame=0;this.installInputs();
    this.loop=this.loop.bind(this);requestAnimationFrame(this.loop);
  }
  image(url){
    if(this.images.has(url))return Promise.resolve(this.images.get(url));
    if(this.loading.has(url))return this.loading.get(url);
    const resolved=this.assetOverrides?.[url.split('?')[0]]||url;const img=new Image();const promise=new Promise((resolve,reject)=>{img.onload=()=>{if((this.assetOverrides?.[url.split('?')[0]]||url)===resolved)this.images.set(url,img);resolve(img);};img.onerror=()=>reject(new Error('美術素材讀取失敗'));});
    this.loading.set(url,promise);img.src=resolved;return promise;
  }
  async load(){
    const r=await fetch('/assets/maps.json');if(!r.ok)throw new Error('地圖讀取失敗');this.spec=await r.json();
    const urls=new Set();
    for(const art of Object.values(LPC_ART.scenes)){urls.add(art.background);for(const prop of art.decor)urls.add(prop.image);}
    for(const [id,variants] of Object.entries(LPC_ART.variants))for(const outfit of variants)urls.add(`/assets/lpc-${id}-${outfit}.png`);
    await Promise.all([...urls].map(url=>this.image(url)));this.ready=true;
  }
  spriteURL(e){
    if(e.art?.sprite&&this.images.has(e.art.sprite))return e.art.sprite;
    const variants=LPC_ART.variants[e.id]||[];const outfit=variants.includes(e.outfit?.id)?e.outfit.id:'original';
    return `/assets/lpc-${e.id}-${outfit}.png`;
  }
  installInputs(){
    const dirs={ArrowUp:'up',ArrowDown:'down',ArrowLeft:'left',ArrowRight:'right',w:'up',s:'down',a:'left',d:'right',W:'up',S:'down',A:'left',D:'right'};
    window.addEventListener('keydown',e=>{
      if(e.target.closest('dialog'))return;
      if(['INPUT','TEXTAREA','BUTTON','SUMMARY','SELECT'].includes(e.target.tagName)||e.isComposing)return;
      if(dirs[e.key]){e.preventDefault();this.keys.add(dirs[e.key]);if(!e.repeat&&!this.paused){this.lastInput=performance.now();this.onAction('step',{direction:dirs[e.key]});}}
      if((e.key==='e'||e.key==='E'||e.key===' ')&&!e.repeat){e.preventDefault();this.onInteract();}
    });
    window.addEventListener('keyup',e=>{if(dirs[e.key])this.keys.delete(dirs[e.key]);});window.addEventListener('blur',()=>this.keys.clear());
    this.canvas.addEventListener('pointerdown',e=>{
      this.canvas.focus({preventScroll:true});if(!this.map||this.paused)return;
      const r=this.canvas.getBoundingClientRect();const x=(e.clientX-r.left)*this.canvas.width/r.width,y=(e.clientY-r.top)*this.canvas.height/r.height;
      const wx=x/this.zoom+this.camera.x,wy=y/this.zoom+this.camera.y,T=this.tileSize;
      const target=[...this.entities.values()].find(p=>p.id!=='player'&&Math.abs(wx-(p.drawX*T+T/2))<18&&Math.abs(wy-(p.drawY*T+T/2-16))<28);
      if(target){this.onPick(target.id);return;}
      const object=this.map.objects.find(o=>Math.abs(wx-(o.x*T+T/2))<T*.6&&Math.abs(wy-(o.y*T+T/2))<T*.65);
      if(object){const p=this.entities.get('player');if(Math.abs(p.x-object.x)+Math.abs(p.y-object.y)<=2)this.onAction('interact',{object:object.id});else this.onAction('walk',{x:object.x,y:object.y+1});return;}
      this.onAction('walk',{x:Math.floor(wx/T),y:Math.floor(wy/T)});
    });
  }
  update(state,selected){
    if(!this.ready||!state.space)return;
    for(const art of Object.values(state.art_backgrounds||{}))if(!this.images.has(art.background))this.image(art.background).catch(()=>{});
    const c=state.components;if(c){const mapping=Object.fromEntries(Object.entries(c.art).map(([name,url])=>['/assets/'+name,url]));const previous=this.assetOverrides||{};this.assetOverrides=mapping;for(const url of new Set([...Object.keys(mapping),...Object.keys(previous)]))if(mapping[url]!==previous[url]){this.images.delete(url);this.loading.delete(url);this.image(url).catch(()=>{});}this.assetOverrides=mapping;this.spec.maps[state.space.scene]=c.map;this.componentVisual=c.visual;for(const url of [c.visual.background,...c.visual.decor.map(d=>d.image),...(c.visual.tiles||[]).map(t=>t.image)])if(!this.images.has(url))this.image(url).catch(()=>{});}
    const changed=this.scene!==state.space.scene;this.scene=state.space.scene;this.map=this.spec.maps[this.scene];this.selected=selected;this.state=state;
    const present=new Set();
    for(const item of state.space.entities){
      if(item.art?.sprite&&!this.images.has(item.art.sprite))this.image(item.art.sprite).catch(()=>{});
      present.add(item.id);const prev=this.entities.get(item.id),sceneChanged=!prev||prev.scene!==item.scene;
      const moving=prev&&(prev.x!==item.x||prev.y!==item.y);
      this.entities.set(item.id,{...item,drawX:sceneChanged?item.x:prev.drawX,drawY:sceneChanged?item.y:prev.drawY,animationUntil:moving?performance.now()+360:prev?.animationUntil||0});
    }
    for(const id of this.entities.keys())if(!present.has(id))this.entities.delete(id);
    const p=this.entities.get('player');if(!p)return;
    if(changed){this.camera.x=p.x*this.tileSize+16-this.canvas.width/2;this.camera.y=p.y*this.tileSize+16-this.canvas.height/2;}
    this.canvas.dataset.playerX=String(p.x);this.canvas.dataset.playerY=String(p.y);this.canvas.dataset.scene=this.scene;this.canvas.dataset.artVersion='LPC-0.10';
  }
  label(text,x,y,kind='normal',translate=true){
    if(translate)text=window.LifeI18n?.t(text)||text;
    if(translate)text=window.LifeI18n?.t(text)||text;
    const ctx=this.ctx;ctx.font='12px "Microsoft JhengHei",sans-serif';ctx.textAlign='center';ctx.textBaseline='middle';
    const w=ctx.measureText(text).width+14;
    ctx.fillStyle=kind==='selected'?'#fff1caee':kind==='home'?'#33473fba':'#263a32b0';
    ctx.beginPath();ctx.roundRect(Math.round(x-w/2),Math.round(y-9),Math.ceil(w),18,4);ctx.fill();
    ctx.fillStyle=kind==='selected'?'#51463b':'#f8f5e5';ctx.fillText(text,Math.round(x),Math.round(y));
  }
  drawEntity(e,now){
    const ctx=this.ctx,T=this.tileSize,px=Math.round(e.drawX*T+T/2),py=Math.round(e.drawY*T+28);
    const row={up:0,left:1,down:2,right:3}[e.direction]??2;
    const active=e.animationUntil>now||Math.abs(e.drawX-e.x)+Math.abs(e.drawY-e.y)>.05;
    const sd=!!e.art?.sprite&&this.images.has(e.art.sprite),frames=sd?(e.art.frames||3):9;
    const frame=active?1+Math.floor(now/140)%(frames-1):0,sprite=this.images.get(this.spriteURL(e));
    ctx.fillStyle='#253b3745';ctx.beginPath();ctx.ellipse(px,py-3,11,4,0,0,Math.PI*2);ctx.fill();
    if(e.id===this.selected){ctx.strokeStyle='#edcd87';ctx.lineWidth=1.5;ctx.beginPath();ctx.ellipse(px,py-3,13,5,0,0,Math.PI*2);ctx.stroke();}
    if(sprite)ctx.drawImage(sprite,frame*64,row*64,64,64,px-32,py-60,64,64);
    if(e.activity==='working'||e.activity==='earning'){ctx.fillStyle='#f2d698';ctx.beginPath();ctx.arc(px+15,py-45,3,0,Math.PI*2);ctx.fill();}
  }
  draw(now,dt){
    const ctx=this.ctx,w=this.canvas.width,h=this.canvas.height,T=this.tileSize;
    if(!this.ready||!this.map){ctx.fillStyle='#98a792';ctx.fillRect(0,0,w,h);ctx.fillStyle='#f8f3e3';ctx.font='16px sans-serif';ctx.textAlign='center';ctx.fillText(window.LifeI18n?.t('正在整理街景…')||'正在整理街景…',w/2,h/2);return;}
    const player=this.entities.get('player');if(!player)return;
    for(const e of this.entities.values()){const k=Math.min(1,dt*.025);e.drawX+=(e.x-e.drawX)*k;e.drawY+=(e.y-e.drawY)*k;if(Math.abs(e.drawX-e.x)<.015)e.drawX=e.x;if(Math.abs(e.drawY-e.y)<.015)e.drawY=e.y;}
    const viewW=w/this.zoom,viewH=h/this.zoom,mapW=this.map.width*T,mapH=this.map.height*T;
    const cx=mapW<viewW?(mapW-viewW)/2:Math.max(0,Math.min(mapW-viewW,player.drawX*T+16-viewW/2));
    const cy=mapH<viewH?(mapH-viewH)/2:Math.max(0,Math.min(mapH-viewH,player.drawY*T+16-viewH/2));
    this.camera.x+=(cx-this.camera.x)*Math.min(1,dt*.02);this.camera.y+=(cy-this.camera.y)*Math.min(1,dt*.02);
    ctx.fillStyle='#35433e';ctx.fillRect(0,0,w,h);
    const original=this.componentVisual||LPC_ART.scenes[this.scene],replacement=this.state.art_backgrounds?.[this.scene],ready=replacement&&this.images.has(replacement.background);const art=ready?{background:replacement.background,decor:replacement.hide_decor?[]:original.decor}:original,bg=this.images.get(art.background);
    ctx.save();ctx.scale(this.zoom,this.zoom);ctx.translate(-Math.round(this.camera.x),-Math.round(this.camera.y));if(bg)ctx.drawImage(bg,0,0);for(const tile of art.tiles||[]){const im=this.images.get(tile.image);if(im)ctx.drawImage(im,...tile.source,tile.x,tile.y,tile.width,tile.height);}
    // Structures and actors share depth sorting: people pass behind trees,
    // counters and building roofs rather than walking over a painted picture.
    const layers=art.decor.map(p=>({depth:p.depth,prop:p}));
    for(const e of this.entities.values())layers.push({depth:e.drawY*T+28,entity:e});
    layers.sort((a,b)=>a.depth-b.depth);
    for(const layer of layers){if(layer.entity)this.drawEntity(layer.entity,now);else{const p=layer.prop;const im=this.images.get(p.image);if(im)ctx.drawImage(im,p.x,p.y);}}
    if(this.scene==='shared'&&this.state.space.watered_today){ctx.fillStyle='#a9d9e0';ctx.beginPath();ctx.arc(14*T+24,15*T+10,3,0,Math.PI*2);ctx.fill();}
    ctx.restore();
    const screen=(x,y)=>[(x*T+16-this.camera.x)*this.zoom,(y*T-this.camera.y)*this.zoom];
    // Discrete world time supplies a gentle evening tint, leaving detail legible.
    const hour=(14+Math.floor(this.state.tick/60))%24;
    if(['shared','district','zoo','park','market'].includes(this.scene)&&(hour>=18||hour<7)){ctx.fillStyle='rgba(37,52,73,.13)';ctx.fillRect(0,0,w,h);}
    for(const l of this.map.labels){const[x,y]=screen(l.x,l.y);if(x>0&&x<w&&y>12&&y<h-12)this.label(l.text,x,y-12,'home');}
    for(const e of this.entities.values()){
      const[x,y]=screen(e.drawX,e.drawY);if(x<0||x>w||y<30||y>h+60)continue;
      const name=e.id==='player'?'你':this.state.roster.find(p=>p.id===e.id)?.name||'';
      this.label(name+(e.near?' · E':''),x,y-37,e.id===this.selected?'selected':'normal',e.id==='player');
    }
    if(this.scene==='market'&&this.state.economy?.market){for(let i=0;i<10;i++){
      const seller=`member-${String(i+1).padStart(2,'0')}`,stock=this.state.economy.market.listings.filter(l=>l.seller===seller).reduce((sum,l)=>sum+l.quantity,0);
      if(stock){const[x,y]=screen(6+7*(i%5),5+8*Math.floor(i/5));this.label(`寄售 ${stock} 份`,x,y+43);}
    }}
    if(['shared','district','park','market'].includes(this.scene)){
      const mw=120,mh=Math.round(mw*mapH/mapW),mx=15,my=h-mh-15;ctx.fillStyle='#f7f2dfdd';ctx.fillRect(mx-3,my-3,mw+6,mh+6);
      ctx.save();ctx.beginPath();ctx.rect(mx,my,mw,mh);ctx.clip();if(bg)ctx.drawImage(bg,mx,my,mw,mh);
      for(const p of art.decor)if(this.images.has(p.image))ctx.drawImage(this.images.get(p.image),mx+p.x*mw/mapW,my+p.y*mh/mapH,this.images.get(p.image).width*mw/mapW,this.images.get(p.image).height*mh/mapH);
      ctx.strokeStyle='#f9e7b7';ctx.lineWidth=1;ctx.strokeRect(mx+this.camera.x*mw/mapW,my+this.camera.y*mh/mapH,viewW*mw/mapW,viewH*mh/mapH);
      for(const e of this.entities.values()){ctx.fillStyle=e.id==='player'?'#fff4be':'#b86d57';ctx.fillRect(mx+(e.x*T+16)*mw/mapW-1,my+(e.y*T+16)*mh/mapH-1,3,3);}ctx.restore();
    }
  }
  loop(now){
    const dt=Math.min(60,now-this.lastFrame||16);this.lastFrame=now;
    if(this.keys.size&&!this.paused&&now-this.lastInput>160){this.lastInput=now;this.onAction('step',{direction:[...this.keys].at(-1)});}
    this.draw(now,dt);requestAnimationFrame(this.loop);
  }
};
