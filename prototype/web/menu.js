/* Game entry and real preferences. Never resets a world on Continue. */
(() => {
 const el=id=>document.getElementById(id),title=el('start-menu');let active=true,holdPending=true,lastBlocked=true,holding=false;
 const panels=(kind,name)=>{for(const p of document.querySelectorAll(`[data-${kind}-panel]`))p.hidden=p.dataset[kind+'Panel']!==name;for(const b of document.querySelectorAll(`[data-${kind}-tab]`))b.setAttribute('aria-selected',String(b.dataset[kind+'Tab']===name));};
 for(const b of document.querySelectorAll('[data-settings-tab]'))b.onclick=()=>panels('settings',b.dataset.settingsTab);
 function settingsValues(s){
  const p=s.preferences.config;el('settings-zoom').value=p.camera_zoom;el('settings-zoom-value').textContent=Number(p.camera_zoom).toFixed(2)+'×';
  for(const [id,key] of [['settings-names','show_names'],['settings-minimap','show_minimap'],['settings-motion','reduce_motion'],['settings-text','large_text'],['settings-pause','pause_in_settings']])el(id).checked=p[key];
  el('settings-ai-note').textContent=s.usage.demo?'目前為離線示範：作息與範例草稿使用本機規則。':'目前使用已配置的角色模型與原有用量上限。';
 }
 function blocked(){return active||!!(state?.preferences.config.pause_in_settings&&document.querySelector('dialog[open]:not(#start-menu)'));}
 async function hold(){holdPending=true;if(holding||typeof state==='undefined'||!state||busy||polling)return;holdPending=false;holding=true;try{await send('ui_hold',{},true);}finally{holding=false;}}
 function update(s){
  document.body.classList.toggle('large-text',!!s.preferences.config.large_text);
  for(const id of ['title-continue','title-new','title-maker','title-settings','title-language'])el(id).disabled=false;
  el('title-load').disabled=!s.has_save;el('title-language').value=s.preferences.config.language;
  el('title-player-name').textContent=s.player.name;const entity=s.space.entities.find(e=>e.id==='player');el('title-player-art').src=portraitURL('player',entity);
  const background=s.art_backgrounds?.shared?.background||s.components.art['lpc-map-shared.png']||'/assets/lpc-map-shared.png';document.querySelector('.title-art').style.backgroundImage=`linear-gradient(90deg,var(--paper,#f5f1e5) 30%,#f5f1e5cc 55%,#f5f1e522),url("${background}")`;
  el('title-save-note').textContent=s.start_menu.has_progress?'最新進度 · '+s.location_name:'小鎮已準備好，可以開始你的第一個下午。';
  el('title-mode').textContent=s.usage.demo?'離線示範 · 不呼叫模型':'本機世界 · 各自的 AI 視角';
  const next=blocked();if(next!==lastBlocked){lastBlocked=next;holdPending=true;}
  if(holdPending&&!holding&&!busy&&!polling)hold();
 }
 async function enterWorld(){await hold();active=false;if(title.open)title.close();lastBlocked=blocked();if(state)render(state);game.keys.clear();el('world').focus({preventScroll:true});}
 function open(){active=true;game.keys.clear();if(!title.open)title.showModal();hold();if(state)render(state);}
 function child(action){if(title.open)title.close();action();}
 window.LifeMenu={blocked,update,enterWorld,open};
 title.addEventListener('cancel',e=>{e.preventDefault();if(state)enterWorld();});
 el('menu-open').onclick=open;el('title-continue').onclick=enterWorld;
 el('title-new').onclick=()=>child(()=>window.openCharacterMaker('template','player'));
 el('title-maker').onclick=()=>child(()=>window.openCharacterMaker('current','player'));
 el('title-settings').onclick=()=>child(()=>el('preferences-open').click());
 el('title-load').onclick=async()=>{const result=await send('load');if(!result.failed&&!result.error)enterWorld();};
 el('title-language').onchange=async()=>{const select=el('preferences-language');if(typeof select.onchange!=='function')return;el('title-language').disabled=true;try{select.value=el('title-language').value;await select.onchange();}finally{el('title-language').disabled=false;if(state)update(state);}};
 el('settings-zoom').oninput=()=>{el('settings-zoom-value').textContent=Number(el('settings-zoom').value).toFixed(2)+'×';};
 el('preferences-open').addEventListener('click',()=>{if(state)settingsValues(state);});
 el('settings-save').onclick=async()=>{
  const payload={...state.preferences.config,camera_zoom:Number(el('settings-zoom').value),show_names:el('settings-names').checked,show_minimap:el('settings-minimap').checked,reduce_motion:el('settings-motion').checked,large_text:el('settings-text').checked,pause_in_settings:el('settings-pause').checked};
  try{const response=await fetch('/api/preferences',{method:'POST',headers:{'Content-Type':'application/json','X-Play-Token':token},body:JSON.stringify(payload)});const result=await response.json();if(!response.ok)throw Error(result.message||'設定無法保存。');state.preferences=result;el('preferences-status').textContent='遊戲設定已保存。';render(state);}catch(error){el('preferences-status').textContent=error.message;}
 };
 for(const [id,target] of [['settings-speech-link','speech-open'],['settings-ai-link','components-open'],['settings-sd-link','art-open'],['settings-town-link','town-open']])el(id).onclick=()=>{el('preferences-modal').close();el(target).click();};
 el('settings-save-link').onclick=async()=>{const result=await send('save');el('preferences-status').textContent=result.notice||'目前進度已保存。';};
 for(const dialog of document.querySelectorAll('dialog:not(#start-menu)'))dialog.addEventListener('close',()=>{holdPending=true;setTimeout(()=>{if(active&&!document.querySelector('dialog[open]'))title.showModal();hold();if(state)render(state);},0);});
 const observer=new MutationObserver(()=>{const next=blocked();if(next!==lastBlocked){lastBlocked=next;hold();if(state)render(state);}});for(const d of document.querySelectorAll('dialog'))observer.observe(d,{attributes:true,attributeFilter:['open']});
 open();
})();
