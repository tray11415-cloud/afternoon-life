let rosterSignature='';
function portraitURL(id,entity){if(entity?.art?.portrait)return entity.art.portrait;const outfit=LPC_ART.variants[id]?.includes(entity?.outfit?.id)?entity.outfit.id:'original';const name=`lpc-${id}-${outfit}-portrait.png`;return state?.components?.art[name]||'/assets/'+name;}
const $=id=>document.getElementById(id);
let state=null,selected=null,busy=false,polling=false,paused=false,token='',lastEvents='',pendingAction=null,currentCommand=null;
const game=new PixelLife($('world'),(c,p)=>send(c,p,true),pick,interact);
const activity={idle:'休息中',working:'處理自己的事',talking:'交談中',moving:'散步中',meeting:'赴約中',earning:'打工中',crafting:'創作中',visiting:'活動中',gathering:'共同活動中'};
const inviteStatus={pending:'等待回應',accepted:'已接受',declined:'婉拒',active:'一起坐坐',fulfilled:'已赴約',missed:'錯過了',expired:'已過期',cancelled:'已取消'};

function note(text,error=false){$('notice').textContent=text||'';$('notice').classList.toggle('error',error);}
function render(s) {
  state=s;token=s.token||token;window.LifeI18n?.sync(s);
  const entities=new Map(s.space.entities.map(e=>[e.id,e]));
  const person=s.roster.find(p=>p.id===selected);const near=person&&entities.get(selected)?.near;
  $('place').textContent=s.location_name;let t=14*60+s.tick; $('clock').textContent=`DAY ${String(1+Math.floor(t/1440)).padStart(2,'0')} · ${String(Math.floor(t%1440/60)).padStart(2,'0')}:${String(t%60).padStart(2,'0')}`;
  const thinking=busy&&['talk','invite','wait','town_chat'].includes(currentCommand);
  $('life-status').textContent=paused?'時間暫停':thinking?'她正在思考':'生活進行中';
  $('map-note').textContent=near?`按 E 與${person.name}互動。`:selected&&entities.has(selected)?`走近${person.name}再聊聊。`:'走近一個人，故事從這裡開始。';
  $('speaker').textContent=person?`${person.name}${near?'':' · 請先走近'}`:'在庭院逛逛';
  const currentPortrait=portraitURL(selected||'member-01',entities.get(selected||'member-01'));if($('portrait').getAttribute('src')!==currentPortrait)$('portrait').src=currentPortrait; $('portrait').alt=person?`${person.name}的像素立繪`:'角色像素立繪';
  $('message').disabled=!near||busy;$('send').disabled=!near||busy;$('invite').disabled=!near||busy||person?.scripted;$('cg').disabled=!near||busy||person?.scripted;
  $('portrait-caption').textContent=person?`${person.age||25} 歲 · ${person.scripted?'一般 NPC':'成年成員'}`:'成年成員';$('roster-count').textContent=s.roster.length;
  $('message').placeholder=near?`想對${person.name}說些什麼？`:'走近對方之後，說點什麼…';
  $('chat-status').textContent=thinking?(s.usage.demo?'離線示範回應中…':'Grok 4.3 回應中…'):person?.scripted?'一般 NPC · 固定台詞 · 不扣聊天 API':s.usage.demo?'離線示範 · 不扣 API':'聊天使用 Grok 4.3';
  const roster=$('roster');const rosterKey=JSON.stringify([selected,s.roster.map(p=>{const e=entities.get(p.id);return [p.id,p.name,!!e,e?.near,e?.activity,e?.outfit?.id,e?.art?.portrait];})]);if(rosterKey!==rosterSignature){rosterSignature=rosterKey;roster.replaceChildren();
  for(const p of s.roster){const e=entities.get(p.id);const b=document.createElement('button');b.className='person'+(selected===p.id?' selected':'')+(!e?' outside':'');b.setAttribute('aria-label',`走近${p.name}`);b.setAttribute('aria-pressed',selected===p.id?'true':'false');
    const img=document.createElement('img');img.src=portraitURL(p.id,e);img.alt='';
    const info=document.createElement('span');info.className='person-info';const name=document.createElement('strong');name.dataset.userContent='true';name.textContent=p.name;const status=document.createElement('small');status.textContent=e?(e.near?'就在身邊 · ': '視野中 · ')+(activity[e.activity]||'休息中'):'目前不在視野內';info.append(name,status);const dot=document.createElement('span');dot.className='dot';b.append(img,info,dot);b.onclick=()=>pick(p.id);roster.append(b);
  }
  }
  const events=s.events.filter(e=>['message_spoken','city_spoken'].includes(e.kind)&&(e.kind==='city_spoken'&&(e.actor===selected||e.data.target===selected)||e.actor===selected&&e.data.target==='player'||e.actor==='player'&&e.data.target===selected||e.actor===selected&&e.data.target===null));
  const invitations=s.invitations.filter(inv=>inv.sender===selected||inv.recipient===selected);
  const signature=JSON.stringify([selected,events,invitations]);
  if(signature!==lastEvents){lastEvents=signature;const box=$('messages');box.replaceChildren();
    if(!selected||(!events.length&&!invitations.length)){const p=document.createElement('p');p.className='empty';p.textContent=selected?'她有自己的安排。試著問問她今天想做什麼。':'每個人都有自己的日子。靠近她，按 E 聊聊。';box.append(p);}
    for(const e of events.slice(-10)){const p=document.createElement('p');p.className=e.actor==='player'?'from-player':'from-agent';p.dataset.userContent='true';p.textContent=(e.actor==='player'?'你：':(s.roster.find(p=>p.id===e.actor)?.name||'成員')+'：')+e.data.text;window.attachSpeech?.(p,e.id,e.actor,e.data.text);box.append(p);}
    for(const inv of invitations.slice(-2)){const p=document.createElement('p');p.textContent=`一起坐坐：${inviteStatus[inv.status]||inv.status}`;box.append(p);if(inv.status==='pending'&&inv.recipient==='player'){for(const [label,accept] of [['接受',true],['婉拒',false]]){const b=document.createElement('button');b.textContent=label;b.onclick=()=>send('respond',{invitation_id:inv.id,accept});box.append(b);}}}
    box.scrollTop=box.scrollHeight;
  }
  $('usage').textContent=`聊天 ${s.usage.dialogue_model||'grok-4.3'}；行動 ${s.usage.model}。雲端 API ${s.usage.calls} 次，本機工具 ${s.usage.local_tool_calls||0} 次，估計 US$${Number(s.usage.estimated_usd||0).toFixed(5)}。上限 50 次／US$0.05，走路與生活時間不扣額度。`;
  $('memory-info').textContent=s.memory.provider.startsWith('lexical')?'記憶：每人獨立，按話題、重要性、時間和場所想起舊事；原始紀錄保留。尚未接語意模型。':'記憶：每人獨立，使用本機語意向量與事件檢索。';
  $('load').disabled=!s.has_save||busy;$('save').disabled=busy;$('wait').disabled=busy;$('reset').disabled=busy;
  if(s.components)for(const [key,value] of Object.entries(s.components.theme))document.documentElement.style.setProperty('--'+(key==='accent'?'green':key),value);
  renderFacilities(s);renderEconomy(s);renderWardrobe(s);window.renderSocial?.(s);window.renderSpeech?.(s);window.renderLife?.(s);game.paused=paused||busy;game.update(s,selected);
  if(s.error)note(s.error.message,true);else if(s.notice)note(s.notice);
  const outfitKey=entities.get(selected)?.outfit?.render_key;
  if(!$('cg-modal').hidden&&window.shownCGOutfit!==outfitKey)$('cg-modal').hidden=true;
  const ready=[...s.cg.jobs].reverse().find(j=>j.status==='ready'&&j.scene.scene===s.space.scene&&j.scene.character===selected&&j.scene.outfit===outfitKey);
  if(ready&&ready.job_id!==window.lastCG){window.lastCG=ready.job_id;window.shownCGOutfit=outfitKey;$('cg-image').src=ready.url||`/cg/${ready.asset_id}.png`;$('cg-modal').hidden=false;}
}
async function send(command,params={},quiet=false) {
  if(busy||!state)return;
  // A heartbeat must not swallow a click, a message or a key press.
  if(polling){if(command!=='pulse'&&(!pendingAction||['step','walk'].includes(pendingAction.command)))pendingAction={command,params,quiet};return;}
  if(['load','reset','create_cast','restore_cast'].includes(command))window.resetSpeechHistory?.();
  const isPulse=command==='pulse';if(isPulse)polling=true;else{busy=true;currentCommand=command;render(state);if(!quiet)note('');}
  try {
    const response=await fetch('/api/action',{method:'POST',headers:{'Content-Type':'application/json','X-Play-Token':token},body:JSON.stringify({command,params})});
    const data=await response.json();if(!response.ok)throw new Error(data.message||'行動暫時無法執行。');
    state=data;return data;
  }catch(e){note(e.message,true);return {failed:true,notice:e.message};}finally{busy=false;polling=false;currentCommand=null;if(state)render(state);if(pendingAction){const next=pendingAction;pendingAction=null;send(next.command,next.params,next.quiet);}}
}
function pick(id){
  if(!state||busy)return;selected=id;render(state);const e=state.space.entities.find(p=>p.id===id);
  if(!e){note('她目前不在視野內。可以到她家附近看看。');return;}
  if(e.near){$('message').focus();return;}send('approach',{target:id},true);$('world').focus();
}
function interact(){
  if(!state||busy)return;
  if(state.facility?.near){facilityOpen=true;selected=null;render(state);return;}const p=state.space.entities.find(e=>e.id==='player');
  const nearby=state.space.entities.filter(e=>e.id!=='player'&&e.near).sort((a,b)=>(Math.abs(a.x-p.x)+Math.abs(a.y-p.y))-(Math.abs(b.x-p.x)+Math.abs(b.y-p.y)));
  if(nearby.length){selected=nearby.some(e=>e.id===selected)?selected:nearby[0].id;render(state);$('message').focus();return;}
  const object=state.space.objects.find(o=>Math.abs(o.x-p.x)+Math.abs(o.y-p.y)<=2);
  if(object)send('interact',{object:object.id});else note('附近沒有可互動的人或物。再走近一點。');
}
$('talk-form').addEventListener('submit',e=>{e.preventDefault();const text=$('message').value.trim();if(!text||!selected||busy)return;$('message').value='';send('talk',{target:selected,text}).then(()=>{$('message').focus();});});
$('invite').onclick=()=>send('invite',{target:selected});$('wait').onclick=()=>send('wait',{minutes:2});$('save').onclick=()=>send('save');$('load').onclick=()=>send('load');$('reset').onclick=()=>{selected=null;send('reset');};
$('close-dialogue').onclick=()=>{selected=null;game.keys.clear();render(state);$('world').focus();};$('interact').onclick=interact;
$('pause').onclick=()=>{paused=!paused;$('pause').textContent=paused?'▶ 繼續':'Ⅱ 暫停';render(state);};
$('cg').onclick=()=>send('cg',{target:selected});$('cg-close').onclick=()=>{$('cg-modal').hidden=true;};
document.querySelectorAll('[data-dir]').forEach(button=>{button.onclick=()=>send('step',{direction:button.dataset.dir},true);});
document.addEventListener('visibilitychange',()=>{game.keys.clear();});
async function start(){
  try{await game.load();const response=await fetch('/api/state');if(!response.ok)throw new Error('世界尚未啟動。');render(await response.json());$('world').focus();}
  catch(e){note('遊戲載入失敗：'+e.message,true);}
}
setInterval(()=>{if(state&&!busy&&!polling&&!paused&&!document.hidden)send('pulse',{focus:selected&&state.space.entities.some(e=>e.id===selected&&e.near)?selected:null},true);},250);
start();

let facilityOpen=false,tripTarget=null,catalogSignature='',catalogLimit=30,lastFacility=null;
function sourceLink(url,label){const a=document.createElement('a');a.textContent=label;if(url&&url.startsWith('https://')){a.href=url;a.target='_blank';a.rel='noopener noreferrer';}return a;}
function renderFacilities(s){
  const nav=$('places');if(!nav.children.length)for(const place of s.places||[]){const b=document.createElement('button');b.textContent=place.name;b.title='沿路步行前往';b.dataset.place=place.id;b.onclick=()=>{tripTarget=place.id;facilityOpen=false;selected=null;catalogLimit=30;send('visit',{location:place.id},true);$('world').focus();};nav.append(b);}
  for(const b of nav.children)b.classList.toggle('active',s.space.scene===b.dataset.place);
  const f=s.facility;if(tripTarget&&f?.id===tripTarget&&f.near){facilityOpen=true;tripTarget=null;}
  if(f&&lastFacility!==f.id){lastFacility=f.id;$('catalog-search').value='';catalogLimit=30;catalogSignature='';}
  if(!f)facilityOpen=false;
  $('facility-panel').hidden=!(facilityOpen&&f);$('conversation').hidden=facilityOpen&&!!f;
  if(!f||!facilityOpen)return;
  $('facility-name').textContent=f.name;$('wallet').textContent=`代幣 ${f.wallet}`;
  const n=$('facility-note');n.replaceChildren(document.createTextNode(`${f.note} · ${new Date(f.checked_at).toLocaleDateString('zh-TW')} ${f.id==='boutique'?'服裝詞彙已匯入':['park','market'].includes(f.id)?'本作原創':f.stale?'快取待更新':'已同步'} `));if(f.url)n.append(sourceLink(f.url,'官方完整目錄 ↗'));
  $('rest').disabled=busy;
  const q=$('catalog-search').value.trim().toLowerCase();const rows=f.items.filter(i=>(i.title+' '+i.category).toLowerCase().includes(q));
  const signature=JSON.stringify([f.id,f.near,f.now_showing,!!f.job,!!s.economy?.busy,busy,s.town?.pool.in_water,s.town?.pool.swimwear,q,catalogLimit,f.wallet,s.wardrobe?.owned.map(i=>i.id)]);
  if(signature!==catalogSignature){catalogSignature=signature;const box=$('catalog');box.replaceChildren();
    for(const item of rows.slice(0,catalogLimit)){const card=document.createElement('article');card.className='catalog-item';const h=document.createElement('strong');h.dataset.userContent='true';h.textContent=item.title;const small=document.createElement('small');small.textContent=`${item.category} · ${item.minutes} 分鐘${item.price?' · '+item.price+' 代幣':''}${item.start?' · '+item.start+'～'+item.end:''}`;card.append(h,small);
      if(item.coverage){const c=document.createElement('small');c.textContent=item.coverage;card.append(c);}
      const actions=document.createElement('div');actions.className='item-actions';const b=document.createElement('button');b.textContent=f.id==='cinema'?(item.id===f.now_showing?'本場 · 讀劇情':'下一輪候選'):item.mode;b.disabled=busy||(item.command==='pool_swim'?(!s.town?.pool.in_water||!s.town?.pool.swimwear):!f.near)||!!f.job||!!s.economy?.busy||(f.id==='cinema'&&item.id!==f.now_showing);b.onclick=()=>send(item.command||'use',item.command==='pool_swim'?{}:{item:item.id});actions.append(b);
      if(['cafe','restaurant'].includes(f.id)){const carry=document.createElement('button');carry.textContent='買來帶走';carry.disabled=b.disabled;carry.onclick=()=>send('buy_supply',{item:item.id});actions.append(carry);}
      if(item.url)actions.append(sourceLink(item.url,f.id==='library'?'完整原文 ↗':'來源 ↗'));
      if(item.embed){const v=document.createElement('button');v.textContent='播放免費電影';v.onclick=()=>{const u=new URL(item.embed);if(u.origin!=='https://video.blender.org'||!u.pathname.startsWith('/videos/embed/'))return;u.searchParams.set('p2p','0');$('movie-name').textContent=item.title;$('movie-frame').src=u.href;$('movie-modal').hidden=false;};actions.append(v);}
        if(item.color){const swatch=document.createElement('span');swatch.className='clothing-swatch';swatch.style.backgroundColor=item.color;h.prepend(swatch);}
        if(item.command==='buy_clothes'&&s.wardrobe?.owned.some(i=>i.id===item.id)){b.textContent='已入衣櫃';b.disabled=true;}
        card.append(actions);box.append(card);
    }
    const more=$('catalog-more');more.replaceChildren(document.createTextNode(`找到 ${rows.length} 項 · 顯示 ${Math.min(rows.length,catalogLimit)} 項 `));if(rows.length>catalogLimit){const b=document.createElement('button');b.textContent='再看 30 項';b.onclick=()=>{catalogLimit+=30;renderFacilities(state);};more.append(b);}
  }
  $('facility-progress').textContent=f.job?`${f.job.title} · ${f.job.scope} · 還有 ${Math.max(0,f.job.ends_at-s.tick)} 分鐘`:f.near?'選一個活動或品項；結果會留下自己的記憶。':'走近服務桌再選；活動會留下自己的記憶。';
  const log=$('outing-log');log.replaceChildren();for(const e of f.recent.slice(-2)){const p=document.createElement('p');p.textContent=`✓ ${e.data.title}：${e.data.scope}　`+e.data.knowledge.slice(0,150);log.append(p);}
}
$('facility-close').onclick=()=>{facilityOpen=false;catalogSignature='';render(state);$('world').focus();};
$('catalog-search').oninput=()=>{catalogLimit=30;renderFacilities(state);};
$('rest').onclick=()=>send('rest');
function closeMovie(){$('movie-modal').hidden=true;$('movie-frame').removeAttribute('src');}
$('movie-close').onclick=closeMovie;
document.addEventListener('keydown',e=>{if(e.key==='Escape'){closeMovie();facilityOpen=false;selected=null;game.keys.clear();if(state)render(state);$('world').focus();}});

let economySignature='';
function actionButton(label,command,params,disabled=false){const b=document.createElement('button');b.textContent=label;b.disabled=disabled;b.onclick=()=>send(command,params);return b;}
function renderEconomy(s){
  const p=s.economy;if(!p)return;
  $('pocket-title').textContent=`口袋與日常 · ${p.wallet} 代幣`;
  const desires=[];for(const [key,label] of [['hunger','想吃點東西'],['thirst','想喝水'],['fatigue','想找個地方休息'],['curiosity','想找點新鮮事']])if(p.needs[key]>=45)desires.push(label);
  $('needs-note').textContent=desires.length?desires.join('，')+'。':'目前狀態還不錯。';
  $('income-note').textContent=`已領工資 ${p.income.wages} · 市集銷售收入 ${p.income.sales}`;
  $('job-progress').textContent=p.job?`${p.job.kind==='shift'?'打工':'創作'}：${p.job.title} · 還有 ${Math.max(0,p.job.ends_at-s.tick)} 分鐘${p.job.kind==='shift'?` · 完成領 ${p.job.wage} 代幣`:''}`:'';
  const signature=JSON.stringify([p.wallet,p.inventory,p.shift,p.can_craft,p.market,p.job,!!p.busy,busy,s.space.scene]);
  if(signature===economySignature)return;economySignature=signature;
  const disabled=busy||p.busy;const actions=$('life-actions');actions.replaceChildren();
  if(p.shift.available)actions.append(actionButton(`打工 ${p.shift.minutes} 分鐘 · +${p.shift.wage} 代幣`,'shift',{},disabled||p.shift.today>=p.shift.limit));
  if(p.can_craft){const material=p.inventory.find(i=>i.id==='materials')?.quantity||0;actions.append(actionButton(`創作${p.recipe.title} · 一份材料`,'craft',{},disabled||material<1));}
  actions.append(actionButton('過十分鐘 · 生活繼續','rest',{},busy));
  const inventory=$('inventory');inventory.replaceChildren();
  if(!p.inventory.length){const empty=document.createElement('p');empty.textContent='口袋裡還沒有物品。';inventory.append(empty);}
  for(const item of p.inventory){const row=document.createElement('div');row.className='inventory-row';const name=document.createElement('span');name.textContent=`${item.title} × ${item.quantity}`;row.append(name);
    if(item.consumable)row.append(actionButton('使用一份','consume',{item:item.id},disabled));
    if(item.sellable&&p.market?.near&&!p.market.listings.some(l=>l.seller==='player'&&l.item===item.id))row.append(actionButton(`寄售 · ${item.price} / 份`,'offer',{item:item.id,quantity:Math.min(2,item.quantity),price:item.price},disabled));inventory.append(row);}
  const market=$('market-trades');market.hidden=!p.market;market.replaceChildren();if(!p.market)return;
  const h=document.createElement('h3');h.textContent='她們的市集';market.append(h);const note=document.createElement('p');note.textContent='作品寄售中；賣家可離開攤位，成交後收到代幣。';market.append(note);
  if(!p.market.listings.length){const empty=document.createElement('p');empty.textContent='目前還沒有作品上架。她們需要先回家創作，或者你也可以帶作品來。';market.append(empty);}
  for(const listing of p.market.listings){const row=document.createElement('div');row.className='market-row';const text=document.createElement('span');text.textContent=`${listing.seller_name} · ${listing.title} · ${listing.price} 代幣 / 份 · 剩 ${listing.quantity} 份`;row.append(text);
    row.append(listing.seller==='player'?actionButton('收攤取回','withdraw',{listing:listing.id},disabled||!p.market.near):actionButton('買一份','buy',{listing:listing.id},disabled||!p.market.near||p.wallet<listing.price));market.append(row);}
}


let wardrobeSignature='';
function renderWardrobe(s){
  const w=s.wardrobe;if(!w)return;const wearing=w.owned.find(i=>i.id===w.wearing);
  $('wardrobe-title').textContent=`衣櫃 · 現在穿著${wearing?.title||'日常服裝'}`;
  $('wardrobe-note').textContent=(w.can_change?'在房間裡，可以換裝。':'買好衣服後回房間換裝。')+'人物行走圖顯示當下穿著；SD 素材可在生圖設定生成、預覽並套用。';
  const signature=JSON.stringify([w,busy]);if(signature===wardrobeSignature)return;wardrobeSignature=signature;
  const box=$('wardrobe-items');box.replaceChildren();
  for(const item of w.owned){const row=document.createElement('div');row.className='wardrobe-row';const heading=document.createElement('div');const color=document.createElement('span');color.className='clothing-swatch';color.style.backgroundColor=item.palette.top;const title=document.createElement('strong');title.dataset.userContent='true';title.textContent=item.title;heading.append(color,title,actionButton(item.id===w.wearing?'穿著中':'換上這套','wear',{item:item.id},busy||w.busy||!w.can_change||item.id===w.wearing));row.append(heading);
    const details=document.createElement('details');const summary=document.createElement('summary');summary.textContent='服裝描述 · 日後出圖使用';const text=document.createElement('p');text.className='outfit-description';text.textContent=item.prompt;details.append(summary,text);if(item.source_url)details.append(sourceLink(item.source_url,'Civitai 服裝參考 ↗'));row.append(details);box.append(row);}
}

