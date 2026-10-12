/* Interface localisation never changes game state, authored profiles or speech history. */
(() => {
 let dictionary={},language='zh-TW',pending=false,ready=false,setting=false;
 const originalNodes=new WeakMap(),originalAttributes=new WeakMap();
 const protectedSelector='script,style,textarea,pre,code,[data-user-content],.from-player,.from-agent,.outfit-description,.group-messages,.social-log';
 const supported=['zh-TW','ja','en'];
 try{const saved=localStorage.getItem('lifebox.language');if(supported.includes(saved))language=saved;}catch{}
 const patterns=[
  [/^(玩家|共居角色) · (.*)$/,(m,a,b)=>`${t(a)} · ${b}`],
  [/^(\d+) 歲 · (.*)$/,(m,n,a)=>language==='en'?`Age ${n} · ${t(a)}`:`${n}歳 · ${t(a)}`],
  [/^按 E 與(.+)互動。$/,(m,name)=>language==='en'?`Press E to interact with ${name}.`:`Eで${name}と交流。`],
  [/^走近(.+)再聊聊。$/,(m,name)=>language==='en'?`Walk up to ${name} to chat.`:`${name}に近づいて話しましょう。`],
  [/^想對(.+)說些什麼？$/,(m,name)=>language==='en'?`What would you like to say to ${name}?`:`${name}に何を話しますか？`],
  [/^走近(.+)$/,(m,name)=>language==='en'?`Walk up to ${name}`:`${name}に近づく`],
  [/^(.+)的家$/,(m,name)=>language==='en'?`${name}'s home`:`${name}の家`],
  [/^衣櫃 · 現在穿著(.+)$/,(m,name)=>language==='en'?`Wardrobe · wearing ${name}`:`衣装棚 · ${name}を着用中`],
  [/^換租借泳裝 · (\d+) 代幣$/,(m,n)=>language==='en'?`Rent swimwear · ${n} coins`:`水着を借りる · ${n}コイン`],
  [/^游泳 (\d+) 分鐘$/,(m,n)=>language==='en'?`Swim for ${n} minutes`:`${n}分泳ぐ`],
  [/^打工 (\d+) 分鐘 · \+(\d+) 代幣$/,(m,n,w)=>language==='en'?`Work ${n} minutes · +${w} coins`:`${n}分働く · +${w}コイン`],
  [/^已領工資 (\d+) · 市集銷售收入 (\d+)$/,(m,w,s)=>language==='en'?`Wages ${w} · market income ${s}`:`受取給与 ${w} · 市場の売上 ${s}`],
  [/^口袋 · (\d+) 代幣$/,(m,n)=>language==='en'?`Pocket · ${n} coins`:`持ち物 · ${n}コイン`],
  [/^(.+) · (\d+) 代幣 · (\d+) 分鐘$/,(m,title,n,time)=>language==='en'?`${t(title)} · ${n} coins · ${time} min`:`${t(title)} · ${n}コイン · ${time}分`],
  [/^(.+)接話 · Grok 4\.3$/,(m,name)=>language==='en'?`${name} replies · Grok 4.3`:`${name}が返答 · Grok 4.3`],
  [/^原存檔 (\d+)$/,(m,n)=>language==='en'?`Archived save ${n}`:`以前のセーブ ${n}`]
  ,[/^沿路走到(.+)。$/,(m,name)=>language==='en'?`Walking to ${t(name)}.`:`${t(name)}へ歩いて向かっています。`]
  ,[/^找到 (\d+) 項 · 顯示 (\d+) 項\s*$/,(m,n,shown)=>language==='en'?`Found ${n} items · showing ${shown}`:`${n}件中${shown}件を表示`]
  ,[/^代幣 (\d+)$/,(m,n)=>language==='en'?`Coins ${n}`:`コイン ${n}`]
  ,[/^聊天 (.*?)；行動 (.*?)。雲端 API (\d+) 次，本機工具 (\d+) 次，估計 US\$(.*?)。上限 (.*?)，走路與生活時間不扣額度。$/,(m,chat,action,calls,tools,cost,limit)=>language==='en'?`Dialogue ${chat}; actions ${action}. Cloud calls ${calls}, local tools ${tools}, estimated US$${cost}. Limit ${limit}. Walking and world time use no API.`:`会話 ${chat}、行動 ${action}。クラウド${calls}回、ローカルツール${tools}回、推定US$${cost}。上限${limit}。歩行と生活時間にAPIは使いません。`]
 ];
 const fragments=[[' · 已替換',' · replaced',' · 置換済み'],[' · 指定名稱／待驗證',' · specified / unverified',' · 指定名・未確認'],[' · 服務回報',' · service reported',' · サービス報告'],[' · 一般 NPC',' · scripted NPC',' · 通常NPC'],[' · 請先走近',' · walk closer first',' · 先に近づいてください'],['視野中 · ','In view · ','見える範囲 · '],['就在身邊 · ','Nearby · ','すぐそば · '],[' 代幣',' coins','コイン'],[' 分鐘',' min','分'],[' · 快取',' · cached',' · キャッシュ']];
 function t(source){
  if(language==='zh-TW'||typeof source!=='string')return source;
  if(dictionary[source])return dictionary[source][language]||source;
  for(const [pattern,replace] of patterns)if(pattern.test(source))return source.replace(pattern,replace);
  let result=source;
  for(const [zh,en,ja] of fragments)result=result.split(zh).join(language==='en'?en:ja);
  for(const [zh,translations] of Object.entries(dictionary))if(zh.length>=3&&result.includes(zh))result=result.split(zh).join(translations[language]);
  return result;
 }
 function skip(element){if(!element)return true;if(element.closest('button')&&!element.closest('pre,code'))return false;return !!element.closest(protectedSelector);}
 function translateNode(node){
  if(skip(node.parentElement)||!node.nodeValue.trim())return;
  const last=originalNodes.get(node),current=node.nodeValue;
  const source=last&&last.rendered===current?last.source:current;
  const whitespace=source.match(/^\s*/)[0],suffix=source.match(/\s*$/)[0];
  const translated=whitespace+t(source.trim())+suffix;
  originalNodes.set(node,{source,rendered:translated});if(current!==translated)node.nodeValue=translated;
 }
 function translateAttributes(element){
  if(skip(element))return;
  let store=originalAttributes.get(element);if(!store){store={};originalAttributes.set(element,store);}
  for(const attr of ['placeholder','aria-label','title','alt']){
   if(!element.hasAttribute(attr))continue;
   const current=element.getAttribute(attr),last=store[attr],source=last&&last.rendered===current?last.source:current,result=t(source);
   store[attr]={source,rendered:result};if(current!==result)element.setAttribute(attr,result);
  }
 }
 function paint(){
  if(!ready)return;
  document.documentElement.lang=language;
  const walker=document.createTreeWalker(document.body,NodeFilter.SHOW_TEXT);
  while(walker.nextNode())translateNode(walker.currentNode);
  for(const el of document.querySelectorAll('[placeholder],[aria-label],[title],[alt]'))translateAttributes(el);
  const title=document.querySelector('title');if(title)title.textContent=t('午後共居 · 像素生活');
 }
 function schedule(){if(pending)return;pending=true;queueMicrotask(()=>{pending=false;paint();});}
 function use(value){if(!supported.includes(value))return;language=value;try{localStorage.setItem('lifebox.language',value);}catch{};schedule();}
 window.LifeI18n={t,sync(s){const note=document.getElementById('demo-note');if(note)note.hidden=!s.usage?.demo;if(!setting)use(s.preferences?.config.language||'zh-TW');}};
 async function init(){
  try{const r=await fetch('/locales.json');if(!r.ok)throw Error();dictionary=await r.json();ready=true;paint();}catch{console.error('Interface translations could not be loaded.');}
  const observer=new MutationObserver(schedule);observer.observe(document.body,{subtree:true,childList:true,characterData:true,attributes:true,attributeFilter:['placeholder','aria-label','title','alt']});
  const modal=document.getElementById('preferences-modal'),select=document.getElementById('preferences-language'),status=document.getElementById('preferences-status');
  document.getElementById('preferences-open').onclick=()=>{game.keys.clear();select.value=language;modal.showModal();schedule();};
  document.getElementById('preferences-close').onclick=()=>modal.close();modal.addEventListener('close',()=>game.keys.clear());
  select.onchange=async()=>{if(setting)return;setting=true;select.disabled=true;const old=language,desired=select.value;try{const r=await fetch('/api/preferences',{method:'POST',headers:{'Content-Type':'application/json','X-Play-Token':token},body:JSON.stringify({language:desired})});const data=await r.json();if(!r.ok)throw Error(data.message||'Unable to save language.');use(data.config.language);if(state)state.preferences=data;status.textContent='語言設定已保存。';}catch(e){use(old);select.value=old;status.textContent=e.message;}finally{setting=false;select.disabled=false;schedule();}};
  if(typeof state!=='undefined'&&state)window.LifeI18n.sync(state);
 }
 if(document.readyState==='loading')document.addEventListener('DOMContentLoaded',init);else init();
})();
