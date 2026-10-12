/* Supported pixel appearance, independent profile drafts and portable cards. */
(() => {
 const el=id=>document.getElementById(id);let direction=2,preview=null,sprite=null,previewSerial=0,timer=null,lastFrame=0,actor='player';
 const fields={'hair':'look-hair','hair_color':'look-hair-color','skin_color':'look-skin-color','eye_color':'look-eye-color','face':'look-face','height':'look-height','build':'look-build','top_color':'look-top-color','bottom_color':'look-bottom-color'};
 const note=(id,text)=>{el(id).textContent=text;};
 function readLook(previous){const p={...(previous||{})};p.enabled=el('look-enabled').checked;for(const [key,id] of Object.entries(fields))p[key]=key==='height'?Number(el(id).value):el(id).value;return p;}
 async function api(body){const response=await fetch('/api/characters',{method:'POST',headers:{'Content-Type':'application/json','X-Play-Token':token},body:JSON.stringify(body)});const result=await response.json();if(!response.ok)throw Error(result.message||'人物草稿無法處理。');return result;}
 async function refreshPreview(){
  const version=++previewSerial,draft=window.CharacterBridge.read();note('maker-preview-status','正在更新像素預覽…');
  try{const result=await api({operation:'preview_look',actor:draft.actor,profile:draft.profile});if(version!==previewSerial)return;const image=new Image();image.onload=()=>{if(version===previewSerial){sprite=image;preview=result;note('maker-preview-status',result.look.enabled?'草稿預覽，尚未套用。':'原始素材；啟用自訂外觀後可調整。');}};image.onerror=()=>note('maker-preview-status','人物圖片載入失敗。');image.src=result.sprite;}catch(error){if(version===previewSerial)note('maker-preview-status',error.message);}
 }
 function schedule(){clearTimeout(timer);timer=setTimeout(refreshPreview,320);el('maker-name').textContent=el('creation-name').value;el('look-height-value').textContent=el('look-height').value+' cm';}
 function show(profile,id,mode){
  actor=id;const p=profile.look;el('look-enabled').checked=!!p?.enabled;if(p)for(const [key,field] of Object.entries(fields))el(field).value=p[key];
  el('maker-name').textContent=profile.name;el('maker-mode-note').textContent=mode==='current'?'目前人物 · 草稿預覽':'新遊戲模板 · 草稿預覽';el('look-height-value').textContent=el('look-height').value+' cm';
  el('maker-ai-source').textContent=state.usage.demo?'離線模式：產生本機範例草稿，不使用模型。':'手動呼叫目前行動模型一次；只傳這位人物草稿與描述，沿用現有用量上限。';el('maker-persona').value='';schedule();
 }
 window.CharacterMaker={readLook,show};
 for(const button of document.querySelectorAll('[data-maker-tab]'))button.onclick=()=>{for(const b of document.querySelectorAll('[data-maker-tab]'))b.setAttribute('aria-selected',String(b===button));for(const panel of document.querySelectorAll('[data-maker-panel]'))panel.hidden=panel.dataset.makerPanel!==button.dataset.makerTab;};
 for(const id of ['look-enabled',...Object.values(fields)])el(id).addEventListener('input',()=>{if(id!=='look-enabled')el('look-enabled').checked=true;window.CharacterBridge.invalidate();schedule();});
 for(const id of ['creation-name','creation-age','creation-gender','creation-appearance'])el(id).addEventListener('input',()=>{if(id==='creation-gender')el('look-enabled').checked=true;schedule();});
 for(const button of document.querySelectorAll('[data-preview-direction]'))button.onclick=()=>{direction=Number(button.dataset.previewDirection);};
 const personalities={
  direct:{'zh-TW':'說話爽快直接，重視實際行動，願意清楚表達自己的界線。','zh-CN':'说话爽快直接，重视实际行动，愿意清楚表达自己的界线。',en:'Direct and practical. States personal boundaries clearly and values follow-through.',ja:'率直で実用的。自分の境界線をはっきり伝え、行動を大切にする。'},
  quiet:{'zh-TW':'慢熟細膩，先觀察再開口；熟悉之後會分享自己在意的小事。','zh-CN':'慢熟细腻，先观察再开口；熟悉之后会分享自己在意的小事。',en:'Reserved and observant at first; shares meaningful little details once comfortable.',ja:'最初は控えめで観察を大切にする。打ち解けると、小さな大切なことを話す。'},
  warm:{'zh-TW':'溫和可靠，會關心他人，也會為自己的工作和休息保留時間。','zh-CN':'温和可靠，会关心他人，也会为自己的工作和休息保留时间。',en:'Warm and dependable. Cares for others while keeping time for work and rest.',ja:'穏やかで頼れる。人を気遣いながら、自分の仕事と休息も大切にする。'},
  curious:{'zh-TW':'好奇活潑，喜歡探索新事物，有自己的計畫，偶爾會先行動再說。','zh-CN':'好奇活泼，喜欢探索新事物，有自己的计划，偶尔会先行动再说。',en:'Curious and lively. Enjoys exploring, keeps personal plans, and sometimes acts before explaining.',ja:'好奇心が強く活発。探索が好きで自分の計画を持ち、ときには話す前に動く。'}
 };
 el('maker-persona').onchange=()=>{const row=personalities[el('maker-persona').value];if(row){el('creation-voice').value=row[window.LifeI18n.language]||row['zh-TW'];el('creation-voice').dispatchEvent(new Event('input'));}};
 el('maker-draft').onclick=async()=>{
  const button=el('maker-draft'),draft=window.CharacterBridge.read(),brief=el('maker-brief').value.trim();if(!brief){note('maker-draft-status','先描述你想要的人物方向。');return;}button.disabled=true;note('maker-draft-status',state.usage.demo?'正在準備本機範例…':'AI 正在草擬這一位人物…');
  try{const result=await api({operation:'draft',actor:draft.actor,profile:draft.profile,brief});const now=window.CharacterBridge.read();if(now.actor!==draft.actor||now.mode!==draft.mode){note('maker-draft-status','人物已切換，這份草稿未放入其他人物。');return;}if(JSON.stringify(now.profile)!==JSON.stringify(draft.profile)){note('maker-draft-status','已有新的編輯，AI 草稿沒有覆蓋目前內容。');return;}window.CharacterBridge.accept(result.profile);state.usage=result.usage;note('maker-draft-status',result.source==='model'?'AI 草稿已放入編輯器，尚未套用。':'本機範例已放入編輯器，沒有呼叫模型。');}catch(error){note('maker-draft-status',error.message);}finally{button.disabled=false;}
 };
 el('maker-export').onclick=()=>{const p=window.CharacterBridge.read();const blob=new Blob([JSON.stringify({format:'lifebox.character.v1',profile:p.profile},null,2)],{type:'application/json'});const url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='character-'+p.actor+'.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1500);note('maker-draft-status','人物卡已匯出；不包含世界記憶或模型權重。');};
 el('maker-import').onchange=async()=>{const file=el('maker-import').files[0];if(!file)return;try{if(file.size>65536)throw Error('人物卡需小於64KB。');const value=JSON.parse(await file.text());if(value.format!=='lifebox.character.v1'||Object.keys(value).sort().join(',')!=='format,profile')throw Error('人物卡格式不符。');const draft=window.CharacterBridge.read(),result=await api({operation:'preview_look',actor:draft.actor,profile:value.profile}),now=window.CharacterBridge.read();if(now.actor!==draft.actor||now.mode!==draft.mode)throw Error('人物已切換，這份草稿未放入其他人物。');window.CharacterBridge.accept({...draft.profile,...value.profile,look:result.look});note('maker-draft-status','人物卡已放入編輯器，尚未套用。');}catch(error){note('maker-draft-status',error.message);}finally{el('maker-import').value='';}};
 function draw(now){
  if(!el('creation-modal').open){requestAnimationFrame(draw);return;}
  const canvas=el('maker-canvas'),ctx=canvas.getContext('2d');ctx.clearRect(0,0,canvas.width,canvas.height);ctx.imageSmoothingEnabled=false;
  ctx.fillStyle='#7e96764a';ctx.beginPath();ctx.ellipse(160,315,55,13,0,0,Math.PI*2);ctx.fill();
  if(sprite&&preview){const frames=preview.frames||9,frame=el('maker-animate').checked?Math.floor(now/180)%frames:0;ctx.drawImage(sprite,frame*64,direction*64,64,64,32,80,256,256);}
  requestAnimationFrame(draw);
 }
 requestAnimationFrame(draw);
})();
