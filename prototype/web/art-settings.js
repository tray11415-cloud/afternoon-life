/* Local character art studio. Polling only changes job cards, never form drafts. */
(() => {
 const el=id=>document.getElementById(id);let studio=null,actor='member-01',timer=null,working=false;
 const names=()=>Object.fromEntries([...(state?.roster||[]).filter(p=>!p.scripted).map(p=>[p.id,p.name]),['player',state?.player?.name||'玩家']]);
 const categories={checkpoint:'底模',lora:'LoRA',vae:'VAE',controlnet:'ControlNet',embedding:'Embedding',text_encoder:'文字編碼器',diffusion:'Diffusion / UNet',upscaler:'放大模型',background:'去背模型',ipadapter:'IP-Adapter',extension:'擴充節點',workflow:'既有工作流',other:'其他資源',vision:'視覺編碼器'};
 function option(select,value,label,disabled=false){const o=document.createElement('option');o.value=value;o.textContent=label;o.disabled=disabled;select.append(o);}
 function report(text,error=false){el('art-status').textContent=text;el('art-status').classList.toggle('error',error);}
 async function call(operation,params={}){
  const res=await fetch('/api/art',operation?{method:'POST',headers:{'Content-Type':'application/json','X-Play-Token':token},body:JSON.stringify({operation,params})}:{headers:{'X-Play-Token':token}});
  const data=await res.json();if(!res.ok)throw Error(data.message||'生圖設定暫時無法讀取，請重新整理遊戲。');return data;
 }
 async function run(fn){if(working)return;working=true;el('art-modal').setAttribute('aria-busy','true');try{await fn();}catch(e){report(e.message,true);}finally{working=false;el('art-modal').removeAttribute('aria-busy');}}
 function defaultProfile(){const index=Number(actor.slice(-2))-1;const hair=['brown short hair','long blue black hair','purple wavy hair','brown braided hair','blonde bob hair','auburn ponytail','dark brown shoulder length hair','rose brown long hair','dark green black hair','black straight hair'];return {identity:hair[index]||'short dark hair',trigger:'',lora:'',weight:.8,clothes_lora:'',clothes_weight:.6,seed:4100+(Number.isFinite(index)&&index>=0?index:10),auto:true,expression:'neutral'};}
 function resourcesFor(category){return studio.resources.filter(r=>r.category===category&&r.installations.includes(el('art-installation').value));}
 function choices(id,category,value,blank='不使用 / 由底模內建'){
  const select=el(id);select.replaceChildren();option(select,'',blank);
  for(const r of resourcesFor(category).filter(r=>r.selectable).sort((a,b)=>a.name.localeCompare(b.name)))option(select,r.id,`${r.name} · ${r.base||r.format}`);
  if(value&&![...select.options].some(o=>o.value===value))option(select,value,'先前選定的資源（目前未找到）',true);select.value=value||'';
 }
 function profileForm(){const p=studio.config.profiles[actor]||defaultProfile();el('art-identity').value=p.identity;el('art-trigger').value=p.trigger;
  choices('art-character-checkpoint','checkpoint',p.checkpoint,'沿用全局底模');choices('art-style-lora','lora',p.style_lora,'不使用畫風 LoRA');el('art-style-weight').value=p.style_weight??.8;el('art-style-trigger').value=p.style_trigger||'';
  choices('art-lora','lora',p.lora,'選擇角色 LoRA（尚未綁定）');choices('art-clothes-lora','lora',p.clothes_lora,'不疊加服裝 LoRA；使用實際穿著 prompt');
  for(const k of ['weight','clothes_weight','seed'])el('art-'+k.replace('_','-')).value=p[k];el('art-character-auto').checked=p.auto;el('art-expression').value=p.expression;
  updateLora();el('art-character-description').textContent=`${names()[actor]} · 成年角色 · 身份、Seed 與素材獨立保存。生成衣服取目前實際穿著。`;
 }
 function updateLora(){const r=studio.resources.find(r=>r.id===el('art-lora').value);el('art-lora-info').textContent=r?`檔案：${r.path}\n底模架構：${r.base}\n訓練標籤參考：${r.tags.join(', ')||'無內嵌資料'}\n標籤只供參考，不會自動加入 prompt；請填寫正確角色觸發詞。`:'目前未綁定角色 LoRA。系統不會猜測哪個本機模型屬於這個角色。';}
 function paint(data){studio=data;const c=data.config;
  const f=el('art-installation');f.replaceChildren();for(const folder of data.folders)option(f,folder.id,`${folder.label} — ${folder.path}`);f.value=c.installation;
  el('art-backend').textContent=data.folders.find(x=>x.id===f.value)?.backend==='comfyui'?'ComfyUI · 固定節點工作流':'reForge / Forge / A1111 · WebUI API';el('art-url').value=c.url;
  choices('art-checkpoint','checkpoint',c.checkpoint,'請選擇已安裝底模');choices('art-vae','vae',c.vae);
  const sam=el('art-sampler');sam.replaceChildren();let samplers=data.service.samplers||[];if(!samplers.includes(c.sampler))samplers=[c.sampler,...samplers];for(const n of samplers)option(sam,n,n);sam.value=c.sampler;
  el('art-scheduler').value=c.scheduler;el('art-auto').checked=c.auto;el('art-background').checked=c.remove_background;el('art-tolerance').value=c.background_tolerance;el('art-palette').value=c.palette;el('art-pixel-guide').value=c.pixel_guide;
  choices('art-control-model','controlnet',c.control_model,'選擇本機姿勢 ControlNet');el('art-control-weight').value=c.control_weight;
  el('art-palette-reference').checked=c.palette_reference;
  el('art-background-method').value=c.background_method;el('art-background-device').value=c.background_device;el('art-background-resolution').value=c.background_resolution;
  const bg=el('art-background-model');bg.replaceChildren();option(bg,'','選擇本機 RMBG-2.0');for(const r of data.resources.filter(r=>r.category==='background'&&r.name==='model.safetensors'&&/RMBG-2.0/i.test(r.path)))option(bg,r.id,r.path);bg.value=c.background_model;
  el('art-rmbg-runtime').textContent=(data.background_runtimes||[]).map(r=>`${r.label}：${r.path}`).join('\n')||'沒有找到既有 SD Python；RMBG 不會自動安裝環境。';
  const select=el('art-character');select.replaceChildren();for(const [id,name] of Object.entries(names()))option(select,id,name);select.value=actor;profileForm();
  for(const kind of ['onepiece','trunks']){const p=c.outfit_loras?.['swim-'+kind]||{};choices('art-swim-'+kind,'lora',p.lora,'選擇本機泳装 LoRA（尚未綁定）');el('art-swim-'+kind+'-trigger').value=p.trigger||'';el('art-swim-'+kind+'-weight').value=p.weight||.8;}
  for(const kind of ['portrait','pixel','cg']){const t=c.templates[kind];for(const k of ['prompt','negative','width','height','steps','cfg','denoise'])el(`art-${kind}-${k}`).value=t[k];}
  for(const box of document.querySelectorAll('[data-art-expression]'))box.checked=c.expressions.includes(box.dataset.artExpression);
  const kinds=el('art-resource-kind');if(!kinds.options.length){option(kinds,'','所有類型');for(const [id,label] of Object.entries(categories))option(kinds,id,label);}
  paintResources();paintJobs();connectionStatus();paintNative();
 }
 function connectionStatus(){el('art-connection').textContent=studio.service.message;el('art-connection').classList.toggle('connected',!!studio.service.ready);
  const models=studio.resources.filter(r=>r.selectable&&r.category==='checkpoint').length;const loras=studio.resources.filter(r=>r.category==='lora'&&r.selectable).length;
  el('art-summary').textContent=`${studio.folders.length} 個 SD 安裝 · ${models} 個底模 · ${loras} 個可選 LoRA · 共 ${studio.resources.length} 筆本機資源。H 類 LoRA 只列出，不提供生成功能。`;
 }
 function collect(){const c=studio.config;const profiles=structuredClone(c.profiles);profiles[actor]={...profiles[actor],checkpoint:el('art-character-checkpoint').value,style_lora:el('art-style-lora').value,style_weight:Number(el('art-style-weight').value),style_trigger:el('art-style-trigger').value,identity:el('art-identity').value,trigger:el('art-trigger').value,lora:el('art-lora').value,weight:Number(el('art-weight').value),clothes_lora:el('art-clothes-lora').value,clothes_weight:Number(el('art-clothes-weight').value),seed:Number(el('art-seed').value),auto:el('art-character-auto').checked,expression:el('art-expression').value};
  const templates={};for(const kind of ['portrait','pixel','cg']){templates[kind]={};for(const k of ['prompt','negative','width','height','steps','cfg','denoise'])templates[kind][k]=['prompt','negative'].includes(k)?el(`art-${kind}-${k}`).value:Number(el(`art-${kind}-${k}`).value);}
  const outfit_loras={};for(const kind of ['onepiece','trunks']){const id=el('art-swim-'+kind).value;if(id)outfit_loras['swim-'+kind]={lora:id,weight:Number(el('art-swim-'+kind+'-weight').value),trigger:el('art-swim-'+kind+'-trigger').value};}
  return {outfit_loras,installation:el('art-installation').value,backend:studio.folders.find(f=>f.id===el('art-installation').value).backend,url:el('art-url').value,checkpoint:el('art-checkpoint').value,vae:el('art-vae').value,sampler:el('art-sampler').value,scheduler:el('art-scheduler').value,auto:el('art-auto').checked,pixel_guide:el('art-pixel-guide').value,control_model:el('art-control-model').value,control_weight:Number(el('art-control-weight').value),palette:Number(el('art-palette').value),palette_reference:el('art-palette-reference').checked,remove_background:el('art-background').checked,background_tolerance:Number(el('art-tolerance').value),background_method:el('art-background-method').value,background_model:el('art-background-model').value,background_device:el('art-background-device').value,background_resolution:Number(el('art-background-resolution').value),expressions:[...document.querySelectorAll('[data-art-expression]:checked')].map(b=>b.dataset.artExpression),templates,profiles};
 }
 async function save(){const data=await call('configure',collect());paint(data);report('設定已保存。LoRA、底模、模板與 Seed 會一起記錄，換裝素材各自保留。');}
 function paintResources(){const query=el('art-resource-search').value.toLowerCase(),kind=el('art-resource-kind').value;const matches=studio.resources.filter(r=>r.installations.includes(el('art-installation').value)&&(!kind||r.category===kind)&&(`${r.name} ${r.path} ${r.base}`.toLowerCase().includes(query)));
  el('art-resource-count').textContent=`找到 ${matches.length} 筆。完整清單可下載；此處每筆顯示實際路徑。`;const body=el('art-resource-list');body.replaceChildren();
  for(const r of matches){const row=document.createElement('tr');for(const text of [r.name,categories[r.category]||r.category,r.base||'—',r.bytes?`${(r.bytes/1024/1024).toFixed(1)} MB`:'—',r.note||(r.selectable?'本機檔案已找到；API 可用性以連線結果為準':'僅列出'),r.path]){const cell=document.createElement('td');cell.textContent=text;row.append(cell);}body.append(row);}
 }
 function paintJobs(){const list=el('art-jobs');list.replaceChildren();const status={queued:'等待 GPU',running:'生成中',ready:'完成',failed:'失敗',cancelled:'已取消',interrupted:'已中斷'};
  if(!studio.jobs.length){const p=document.createElement('p');p.textContent='還沒有角色生成任務。選好 LoRA 後，可先只生成立繪確認角色身份。';list.append(p);return;}
  for(const j of [...studio.jobs].reverse()){
   const card=document.createElement('section');card.className='art-job';const title=document.createElement('h4');title.textContent=`${names()[j.actor]||j.actor} · ${j.kind==='cg'?'一般 CG':j.kind==='both'?'立繪＋像素':j.kind==='pixel'?'像素行走':'立繪差分'} · ${status[j.status]||j.status} ${j.done}/${j.total}`;card.append(title);
   const p=document.createElement('p');p.textContent=`${j.outfit.title} · ${j.message}`;card.append(p);const progress=document.createElement('progress');progress.max=j.total;progress.value=j.done;card.append(progress);
   if(['queued','running'].includes(j.status)){const b=document.createElement('button');b.textContent='取消此任務';b.onclick=()=>run(async()=>{studio=await call('cancel',{id:j.id});paintJobs();});card.append(b);}
   if(j.status==='ready'){
    const images=document.createElement('div');images.className='art-previews';
    for(const [expression,file] of Object.entries(j.files.portraits||{})){const figure=document.createElement('figure');const image=document.createElement('img');image.src='/character-art/'+file;image.alt=`${names()[j.actor]} ${studio.expression_labels[expression]}立繪`;image.loading='lazy';figure.append(image);const caption=document.createElement('figcaption');caption.textContent=studio.expression_labels[expression];figure.append(caption);
     const a=document.createElement('a');a.href=image.src;a.download=file;a.textContent='原圖';figure.append(a);images.append(figure);}
    if(j.files.sprite){const figure=document.createElement('figure'),image=document.createElement('img');image.src='/character-art/'+j.files.sprite;image.alt='四方向三幀行走圖';image.className='art-sprite-preview';figure.append(image);const caption=document.createElement('figcaption');caption.textContent='四方向 × 待機／左步／右步（12 張 SD 圖）';figure.append(caption);images.append(figure);}card.append(images);
    if(j.files.cg){const figure=document.createElement('figure'),image=document.createElement('img');image.src='/character-art/'+j.files.cg;image.alt=`${names()[j.actor]}在${j.scene?.place_name||'當下場景'}的一般 CG`;figure.append(image);images.append(figure);list.append(card);continue;}
    const toolbar=document.createElement('div');toolbar.className='art-toolbar';const select=document.createElement('select');select.setAttribute('aria-label',`${names()[j.actor]}套用表情差分`);for(const expression of Object.keys(j.files.portraits||{neutral:''}))option(select,expression,studio.expression_labels[expression]);
    select.value=Object.hasOwn(j.files.portraits||{},studio.config.profiles[j.actor]?.expression)?studio.config.profiles[j.actor].expression:'neutral';
    const b=document.createElement('button');b.textContent='套用這套素材';b.onclick=()=>run(async()=>{studio=await call('activate',{id:j.id,expression:select.value});report('已套用。只在這位角色穿著同一套衣服時使用；換裝時保留其他素材。');});toolbar.append(select,b);card.append(toolbar);
   }list.append(card);
  }
 }
 function download(name,value){const blob=new Blob([JSON.stringify(value,null,2)],{type:'application/json'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download=name;a.click();URL.revokeObjectURL(url);}
 let nativeDraft=null;
 const nativeVariables={prompt:'正向 Prompt',negative:'負向 Prompt',seed:'Seed',checkpoint:'底模',lora:'角色 LoRA',lora_weight:'角色 LoRA 權重',clothes_lora:'服裝 LoRA（可選）',clothes_weight:'服裝 LoRA 權重',style_lora:'畫風 LoRA（可選）',style_weight:'畫風 LoRA 權重',reference:'身份參考圖',control:'姿勢骨架圖（像素）',denoise:'重繪幅度',width:'寬度（可選）',height:'高度（可選）'};
 for(let i=2;i<=8;i++){nativeVariables['style_lora_'+i]='畫風 LoRA '+i;nativeVariables['style_weight_'+i]='畫風 LoRA '+i+' 權重';}
 function nativeUrl(){const u=new URL(el('art-native-url').value.trim());if(u.protocol!=='http:'||!['127.0.0.1','localhost'].includes(u.hostname)||!u.port||Number(u.port)<1024||u.username||u.password||u.pathname!=='/'||u.search||u.hash)throw Error('完整 SD 只接受本機 HTTP 位址，例如 http://127.0.0.1:7861');return u.origin;}
 function nativeLink(){try{el('art-native-link').href=nativeUrl()+'/';el('art-native-link').removeAttribute('aria-disabled');}catch{el('art-native-link').removeAttribute('href');el('art-native-link').setAttribute('aria-disabled','true');}}
 function paintNative(){const install=el('art-native-installation'),previous=install.value;install.replaceChildren();for(const f of studio.folders)option(install,f.id,`${f.label} — ${f.path}`);install.value=studio.folders.some(f=>f.id===previous)?previous:studio.config.installation;
  if(!el('art-native-url').value)el('art-native-url').value=studio.config.url;nativeLink();
  const templates=studio.native_templates||[],compatible=templates.filter(t=>t.installation===studio.config.installation&&t.backend===studio.config.backend);
  for(const kind of ['portrait','pixel','cg']){const select=el('art-native-'+kind);select.replaceChildren();option(select,'','使用遊戲內建模板');for(const t of compatible)option(select,t.id,t.title);select.value=studio.config.native_selected?.[kind]||'';}
  const lib=el('art-native-library'),selected=lib.value;lib.replaceChildren();option(lib,'','選擇已保存模板');for(const t of templates)option(lib,t.id,`${t.title} · ${t.backend}`);lib.value=templates.some(t=>t.id===selected)?selected:'';
  const resources=el('art-native-resource');resources.replaceChildren();option(resources,'','選擇目前 SD 安裝中的既有工作流');for(const r of studio.resources.filter(r=>r.category==='workflow'&&r.installations.includes(studio.config.installation)))option(resources,r.id,r.name);
  const comfy=studio.config.backend==='comfyui';for(const id of ['history-load','capture','history'])el('art-native-'+id).disabled=!comfy;
  el('art-native-location').textContent=`遊戲生成目前使用 ${studio.config.backend} · ${studio.config.url}。原生視窗可另開其他安裝；保存遊戲模板以前，請在「SD 連線」選擇相同安裝並測試連線。`;
 }
 function nativeFields(value,path='',fields=[]){if(fields.length>=1000)return fields;if(Array.isArray(value)){value.forEach((v,i)=>nativeFields(v,path+'/'+i,fields));}else if(value&&typeof value==='object'){for(const [k,v] of Object.entries(value))nativeFields(v,path+'/'+k.replaceAll('~','~0').replaceAll('/','~1'),fields);}else fields.push({path,value});return fields;}
 function draftForm(draft){nativeDraft=draft;el('art-native-title').value=draft.title;el('art-native-document').value=JSON.stringify(draft.payload,null,2);el('art-native-bindings').value=JSON.stringify(draft.bindings||{},null,2);
  const wrap=el('art-native-bind-fields');wrap.replaceChildren();const fields=nativeFields(draft.payload);
  if(draft.backend==='comfyui')for(const [variable,label] of Object.entries(nativeVariables)){const row=document.createElement('label');row.textContent=label;const select=document.createElement('select');select.setAttribute('aria-label','綁定 '+label);option(select,'','保留原生值／不綁定');for(const f of fields){const n=f.path.split('/')[1],type=draft.payload[n]?.class_type||'';if(/^\/[\w.-]+\/inputs\/[^/]+$/.test(f.path))option(select,f.path,`${n} ${type} · ${f.path.split('/').at(-1)}`);}select.value=Array.isArray(draft.bindings?.[variable])?draft.bindings[variable][0]:draft.bindings?.[variable]||'';
   select.onchange=()=>{try{const bindings=JSON.parse(el('art-native-bindings').value);if(select.value)bindings[variable]=select.value;else delete bindings[variable];el('art-native-bindings').value=JSON.stringify(bindings,null,2);}catch(e){report('綁定 JSON 尚未完成，請先修正格式。',true);}};row.append(select);wrap.append(row);}
  const outputs=el('art-native-output');outputs.replaceChildren();option(outputs,'','選擇輸出節點');if(draft.backend==='comfyui')for(const [id,node] of Object.entries(draft.payload))if(node&&node.class_type)option(outputs,id,`${id} · ${node.class_type}`);outputs.value=draft.output||'';
 }
 el('art-native-installation').onchange=()=>{const f=studio.folders.find(f=>f.id===el('art-native-installation').value);el('art-native-url').value=f.id===studio.config.installation?studio.config.url:f.backend==='comfyui'?'http://127.0.0.1:8188':'http://127.0.0.1:7861';nativeLink();};
 el('art-native-url').oninput=nativeLink;
 el('art-native-open').onclick=()=>{try{el('art-native-frame').src=nativeUrl()+'/';el('art-native-frame').hidden=false;el('art-native-hide').hidden=false;report('已開啟原生 SD；若尚未啟動，先按「啟動完整 SD」。');}catch(e){report(e.message,true);}};
 el('art-native-hide').onclick=()=>{el('art-native-frame').hidden=true;el('art-native-frame').removeAttribute('src');el('art-native-hide').hidden=true;};
 el('art-native-start').onclick=()=>run(async()=>{const data=await call('start_native',{installation:el('art-native-installation').value,url:nativeUrl()});studio=data;report(data.native_message||data.service.message);});
 el('art-native-prepare').onclick=()=>run(async()=>{const data=await call('native_prepare',{document:el('art-native-document').value,title:el('art-native-title').value});draftForm(data.native_draft);report('已解析。確認遊戲變數綁定後，保存為固定模板。');});
 el('art-native-import').onchange=()=>run(async()=>{const file=el('art-native-import').files[0];if(!file)return;if(file.size>2*1024*1024)throw Error('匯入檔案請小於 2 MB；較大 PNG 可改貼 PNG Info 文字。');const params={title:file.name.replace(/\.[^.]+$/,'').slice(0,100)};if(/\.png$/i.test(file.name)){const bytes=new Uint8Array(await file.arrayBuffer());let text='';for(let i=0;i<bytes.length;i+=8192)text+=String.fromCharCode(...bytes.subarray(i,i+8192));params.png=btoa(text);}else params.document=await file.text();const data=await call('native_prepare',params);draftForm(data.native_draft);el('art-native-import').value='';report('已讀入原生模板，尚未保存或執行。');});
 el('art-native-save').onclick=()=>run(async()=>{if(!nativeDraft)throw Error('先解析模板或匯入原生檔案。');const data=await call('native_save',{title:el('art-native-title').value,backend:nativeDraft.backend,payload:JSON.parse(el('art-native-document').value),bindings:JSON.parse(el('art-native-bindings').value),output:el('art-native-output').value});studio=data;paintNative();el('art-native-library').value=data.native_saved;report('固定模板已保存。上方選定生成用途後按「保存三種用途的模板選擇」。');});
 el('art-native-use').onclick=()=>run(async()=>{const selections=Object.fromEntries(['portrait','pixel','cg'].map(k=>[k,el('art-native-'+k).value]));studio=await call('native_select',{selections});paintNative();report('三種生成用途已保存，下次角色生圖使用所選完整模板。');});
 el('art-native-load-resource').onclick=()=>run(async()=>{const data=await call('native_resource',{id:el('art-native-resource').value});draftForm(data.native_draft);report('已讀取工作流；若為畫布 JSON，請先在原生 ComfyUI 匯出 API 格式。');});
 el('art-native-history-load').onclick=()=>run(async()=>{const data=await call('native_history');const select=el('art-native-history');select.replaceChildren();option(select,'','選擇已完成的生成');for(const h of [...data.native_history].reverse())option(select,h.id,`${h.id.slice(0,8)} · ${h.nodes} 節點／${h.images} 圖片`);report(`讀到 ${data.native_history.length} 筆已完成紀錄，不會再次生圖。`);});
 el('art-native-capture').onclick=()=>run(async()=>{const data=await call('native_history',{id:el('art-native-history').value});draftForm(data.native_draft);report('已擷取實際執行的完整節點圖；請確認身份、參考圖與輸出綁定。');});
 el('art-native-edit').onclick=()=>run(async()=>{const data=await call('native_read',{id:el('art-native-library').value});draftForm(data.native_draft);report('已讀取模板；重新保存會保留舊版模板和既有素材。');});
 el('art-native-export').onclick=()=>run(async()=>{const data=await call('native_read',{id:el('art-native-library').value});download('native-sd-template.json',data.native_draft);report('已匯出完整原生模板與遊戲變數綁定。');});
 el('art-native-delete').onclick=()=>run(async()=>{studio=await call('native_delete',{id:el('art-native-library').value});paintNative();report('已刪除未使用模板；既有角色素材保留。');});
 const sampleSprite=new Image();if(el('art-walk-proof'))sampleSprite.src='/assets/sd-v14-sprite.png';let sampleFrame=0;
 setInterval(()=>{const canvas=el('art-walk-proof');if(!canvas||!sampleSprite.complete||!sampleSprite.naturalWidth||!el('art-modal').open||canvas.closest('[data-art-panel]').hidden)return;const ctx=canvas.getContext('2d');ctx.clearRect(0,0,512,128);ctx.imageSmoothingEnabled=false;const frame=[0,1,0,2][sampleFrame++%4];for(let row=0;row<4;row++)ctx.drawImage(sampleSprite,frame*64,row*64,64,64,row*128,0,128,128);},260);
 el('art-open').onclick=()=>run(async()=>{if(!state)return;game.keys.clear();el('art-modal').showModal();report('讀取本機 SD 設定…');if(window.characterArtIntent)actor=window.characterArtIntent;paint(await call());if(window.characterArtIntent){window.characterArtIntent=null;document.querySelector('[data-art-tab="character"]').click();}report('設定只保存在本機；生成不呼叫 xAI，也不使用雲端生圖。');timer=setInterval(async()=>{if(working||el('art-modal').open===false)return;try{const data=await call();const signature=JSON.stringify(data.jobs);if(signature!==JSON.stringify(studio.jobs)){studio.jobs=data.jobs;paintJobs();}}catch{}},2500);});
 el('art-close').onclick=()=>el('art-modal').close();el('art-modal').addEventListener('close',()=>{clearInterval(timer);timer=null;game.keys.clear();});
 el('art-save').onclick=()=>run(save);el('art-probe').onclick=()=>run(async()=>{await save();report('測試本機 SD API…');paint(await call('probe'));report(studio.service.message,!studio.service.ready);});
 el('art-start').onclick=()=>run(async()=>{await save();paint(await call('start'));report(studio.service.message);});
 el('art-scan').onclick=()=>run(async()=>{report('掃描已安裝模型與資源…');paint(await call('scan'));report('已更新本機資源清單。');});
 el('art-folder-add').onclick=()=>run(async()=>{const folder=el('art-folder-path').value.trim();if(!folder)throw Error('請貼上 SD 安裝資料夾路徑。');paint(await call('scan',{folder}));report('已找到安裝資料夾並更新清單。');});
 el('art-folder-open').onclick=()=>run(async()=>{await call('open_folder',{id:el('art-installation').value});report('已在檔案總管開啟所選 SD 資料夾。');});
 el('art-installation').onchange=()=>{const folder=studio.folders.find(f=>f.id===el('art-installation').value);el('art-url').value=folder.backend==='comfyui'?'http://127.0.0.1:8188':'http://127.0.0.1:7861';el('art-backend').textContent=folder.backend==='comfyui'?'ComfyUI · 固定節點工作流':'WebUI API';choices('art-checkpoint','checkpoint','');choices('art-vae','vae','');choices('art-lora','lora','');choices('art-clothes-lora','lora','');choices('art-character-checkpoint','checkpoint','','沿用全局底模');choices('art-style-lora','lora','','不使用畫風 LoRA');el('art-sampler').replaceChildren();option(el('art-sampler'),folder.backend==='comfyui'?'euler':'Euler',folder.backend==='comfyui'?'euler':'Euler');paintResources();updateLora();report('已切換資料夾。請重新選擇底模，保存後測試連線。');};
 el('art-character').onchange=()=>{studio.config.profiles=collect().profiles;actor=el('art-character').value;profileForm();report('已切換角色，其他角色的編輯暫存保留；完成後按保存設定。');};
 el('art-lora').onchange=updateLora;el('art-resource-search').oninput=paintResources;el('art-resource-kind').onchange=paintResources;
 for(const kind of ['portrait','pixel','both'])el('art-generate-'+kind).onclick=()=>run(async()=>{await save();if(!studio.service.ready)paint(await call('probe'));if(!studio.service.ready)throw Error(studio.service.message);studio=await call('generate',{actor,kind});paintJobs();report('已排入本機生成佇列。生活世界仍可正常走動，請在生成紀錄查看進度。');document.querySelector('[data-art-tab="jobs"]').click();});
 el('art-generate-all').onclick=()=>run(async()=>{await save();if(!studio.service.ready)paint(await call('probe'));studio=await call('generate_bound');paintJobs();report('已排入所有綁定角色 LoRA 的角色；未綁定者保留 LPC 圖。');document.querySelector('[data-art-tab="jobs"]').click();});
 el('art-export').onclick=()=>{download('character-sd-settings.json',collect());report('已匯出設定模板；不包含模型權重、私有記憶或金鑰。');};
 el('art-export-resources').onclick=()=>download('local-sd-resources.json',{folders:studio.folders,resources:studio.resources});
 el('art-import').onchange=()=>run(async()=>{const file=el('art-import').files[0];if(!file)return;if(file.size>65536)throw Error('設定檔需小於 64 KB');paint(await call('configure',JSON.parse(await file.text())));report('已匯入並保存設定；模型必須存在於這台電腦。');el('art-import').value='';});
 for(const tab of document.querySelectorAll('[data-art-tab]'))tab.onclick=()=>{for(const t of document.querySelectorAll('[data-art-tab]'))t.setAttribute('aria-selected',String(t===tab));for(const panel of document.querySelectorAll('[data-art-panel]'))panel.hidden=panel.dataset.artPanel!==tab.dataset.artTab;};
})();
