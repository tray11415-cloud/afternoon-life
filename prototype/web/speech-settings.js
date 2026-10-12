/* Speech is optional, per speaker, and never invokes the dialogue model. */
(() => {
 const el=id=>document.getElementById(id);let data=null,config=null,draft=null,actor='member-01',browserVoices=[],serial=0,audio=null,url=null,finish=null,seen=null,lastRevision=0,queue=[],draining=false;
 const option=(s,value,label)=>{const o=document.createElement('option');o.value=value;o.textContent=label;s.append(o);};
 const status=(text,error=false)=>{el('speech-status').textContent=text;el('speech-status').classList.toggle('error',error);el('speech-now').textContent=text;el('speech-modal-stop').disabled=el('speech-stop').disabled;el('social-speech-stop').disabled=el('speech-stop').disabled;el('social-speech-status').textContent=text;};
 async function api(operation,params={}){const res=await fetch('/api/speech',{method:'POST',headers:{'X-Play-Token':token,'Content-Type':'application/json'},body:JSON.stringify({operation,params})});const d=await res.json();if(!res.ok)throw Error(d.message||'語音暫時無法使用');return d;}
 async function load(){const r=await fetch('/api/speech',{headers:{'X-Play-Token':token}});if(!r.ok)throw Error('無法讀取語音設定');data=await r.json();config=data.config;updateButtons();}
 function stop(clearQueue=true){serial++;if(clearQueue)queue=[];window.speechSynthesis?.cancel();if(audio){audio.pause();audio.src='';audio=null;}if(url){URL.revokeObjectURL(url);url=null;}if(finish){finish();finish=null;}el('speech-stop').disabled=true;status('已停止播放');}
 function updateButtons(){for(const b of document.querySelectorAll('.speech-line'))b.disabled=!config?.enabled;el('speech-open').textContent=config?.enabled?'語音設定 · 已啟用':'語音設定';}
 function profile(){return draft?.profiles?.[actor]||{windows:'',browser:'',local:''};}
 function storeVoice(){if(!draft)return;const p=profile();p.windows=el('speech-windows').value;p.browser=el('speech-browser').value;p.local=el('speech-local-id').value.trim();draft.profiles[actor]=p;}
 function collect(){storeVoice();Object.assign(draft,{enabled:el('speech-enabled').checked,auto:el('speech-auto').checked,language:el('speech-language').value,language_mode:el('speech-language-mode').value,provider:el('speech-provider').value,endpoint:el('speech-endpoint').value.trim(),model:el('speech-model-id').value.trim(),speed:Number(el('speech-speed').value),pitch:Number(el('speech-pitch').value),volume:Number(el('speech-volume').value)});}
 function voices(){browserVoices=(window.speechSynthesis?.getVoices()||[]).filter(v=>v.localService);const s=el('speech-browser');const old=s.value||profile()?.browser||'';s.replaceChildren();option(s,'','自動選本機聲線（依朗讀語言）');for(const v of browserVoices)option(s,v.voiceURI,`${v.name} · ${v.lang}`);if(old&&!browserVoices.some(v=>v.voiceURI===old))option(s,old,`${old}（此瀏覽器未提供）`);s.value=old;el('speech-browser-count').textContent=`此瀏覽器提供 ${browserVoices.length} 個本機聲線；不使用遠端聲線。`;}
 window.speechSynthesis?.addEventListener('voiceschanged',voices);
 function showVoice(){const p=profile(),s=el('speech-windows');s.replaceChildren();option(s,'','自動選本機聲線（依朗讀語言）');for(const v of data.windows)option(s,v.id,`${v.name} · ${v.lang}`);if(p.windows&&!data.windows.some(v=>v.id===p.windows))option(s,p.windows,`${p.windows}（未安裝）`);s.value=p.windows;voices();el('speech-browser').value=p.browser;el('speech-local-id').value=p.local;el('speech-local-voice').value=p.local;}
 function catalogs(){const s=el('speech-model');s.replaceChildren();const ids=[...new Set([draft.model,...data.models])];for(const id of ids)option(s,id,`${id}${data.models.includes(id)?' · 服務回報':' · 指定名稱／待驗證'}`);s.value=draft.model;const v=el('speech-local-voice');v.replaceChildren();option(v,'','選擇服務聲線或手動填入');for(const row of data.voices)option(v,row.id,row.name);el('speech-service').textContent=data.service;}
 function provider(){el('speech-language-mode-field').hidden=el('speech-provider').value!=='local';const p=el('speech-provider').value;el('speech-windows-field').hidden=p!=='windows';el('speech-browser-field').hidden=p!=='browser';el('speech-local-fields').hidden=!['local','kokoro'].includes(p);el('speech-pitch-field').hidden=p!=='browser';}
 function paint(){const language=el('speech-language');language.replaceChildren();for(const [id,label] of Object.entries(data.languages||{auto:'跟隨聲線','zh-TW':'繁體中文','zh-CN':'普通話','en-US':'英語（美國）','en-GB':'英語（英國）','ja-JP':'日語','ko-KR':'韓語'}))option(language,id,label);language.value=draft.language||'auto';el('speech-language-mode').value=draft.language_mode||'voice';for(const k of ['enabled','auto'])el('speech-'+k).checked=draft[k];el('speech-provider').value=draft.provider;for(const k of ['endpoint','speed','pitch','volume'])el('speech-'+k).value=draft[k];el('speech-model-id').value=draft.model;catalogs();showVoice();provider();el('speech-resource-count').textContent=`Windows 可用聲線 ${data.windows.length} 個${data.windows_error?' · '+data.windows_error:''}。語音快取 ${data.cache_files} 份。`;}
 async function save(){collect();data=await api('configure',draft);config=data.config;draft=structuredClone(config);stop();updateButtons();status('語音設定已保存；不扣聊天 API。');}
 async function play(actorId,text,event,preview=false,automatic=false){
  if(!config)await load();if(!preview&&!config.enabled){status('先在語音設定中啟用 TTS。',true);return;}
  stop(!automatic);const mine=serial;el('speech-stop').disabled=false;status('語音準備中…');
  try{
   const p=config.profiles[actorId]||{};
   if(config.provider==='browser'){
    browserVoices=(window.speechSynthesis?.getVoices()||[]).filter(v=>v.localService);
    const voice=p.browser?browserVoices.find(v=>v.voiceURI===p.browser):browserVoices.find(v=>v.lang===(config.language==='auto'?'zh-TW':config.language))||browserVoices.find(v=>v.lang.startsWith(config.language==='auto'?'zh':(config.language||'zh-TW').split('-')[0]));
    if(voice&&config.language&&config.language!=='auto'&&voice.lang.split('-')[0]!==config.language.split('-')[0])throw Error('聲線語言不符，請在語音設定重新選擇聲線');if(!voice)throw Error('此瀏覽器沒有所選本機聲線；請改用 Windows 語音。');
    await new Promise((resolve,reject)=>{const u=new SpeechSynthesisUtterance(text);u.voice=voice;u.lang=voice.lang;u.rate=config.speed;u.pitch=config.pitch;u.volume=config.volume;finish=resolve;u.onend=resolve;u.onerror=e=>reject(Error('瀏覽器朗讀未完成：'+e.error));status('播放中 · '+voice.name);window.speechSynthesis.speak(u);});
   }else{
    const result=await api(preview?'preview':'speak',preview?{actor:actorId}:{event});if(mine!==serial)return;
    const res=await fetch(result.audio,{headers:{'X-Play-Token':token}});if(!res.ok)throw Error('音訊暫時無法讀取');const blob=await res.blob();if(mine!==serial)return;
    url=URL.createObjectURL(blob);audio=new Audio(url);audio.volume=config.volume;
    await new Promise((resolve,reject)=>{finish=resolve;audio.onended=resolve;audio.onerror=()=>reject(Error('音訊無法播放'));status(`播放中 · ${result.voice}${result.cached?' · 快取':''}`);audio.play().catch(()=>reject(Error('瀏覽器需要你再按一次播放，才能發聲。')));});
   }
   if(mine===serial){if(url){URL.revokeObjectURL(url);url=null;}audio=null;finish=null;el('speech-stop').disabled=true;status('播放完成');}
  }catch(e){if(mine===serial){stop();status(e.message,true);}}
 }
 window.attachSpeech=(node,eventId,actorId,text)=>{if(!eventId)return;const b=document.createElement('button');b.type='button';b.className='speech-line';b.textContent='▶ 朗讀';b.setAttribute('aria-label',`朗讀${text.slice(0,24)}`);b.disabled=!config?.enabled;b.onclick=()=>play(actorId,text,eventId);node.append(b);};
 window.resetSpeechHistory=()=>{stop();seen=null;lastRevision=0;};
 window.renderSpeech=s=>{
  const lines=[...s.events.filter(e=>['message_spoken','city_spoken'].includes(e.kind)).map(e=>({id:e.id,actor:e.actor,text:e.data.text})),...(s.social?.groups||[]).flatMap(g=>g.messages)];
  const key=m=>`${m.id}:${m.actor}:${m.text}`;
  if(!seen||s.revision<lastRevision){if(seen)stop();seen=new Set(lines.map(key));lastRevision=s.revision;return;}lastRevision=s.revision;
  const added=lines.filter(m=>m.id&&!seen.has(key(m)));for(const m of lines)seen.add(key(m));if(seen.size>10000)seen=new Set(lines.map(key));
  updateButtons();if(config?.enabled&&config.auto&&!document.hidden){queue.push(...added.filter(m=>m.actor!=='player'));queue=queue.slice(-8);drain();}
 };
 async function drain(){if(draining)return;draining=true;try{while(queue.length&&config.enabled&&config.auto){const m=queue.shift();await play(m.actor,m.text,m.id,false,true);}}finally{draining=false;}}
 el('speech-open').onclick=async()=>{if(!state)return;game.keys.clear();el('speech-modal').showModal();try{await load();draft=structuredClone(config);const s=el('speech-person');s.replaceChildren();for(const p of [{id:'player',name:'你'},...state.roster])option(s,p.id,p.name);s.value=actor;paint();status('先選類型與聲線，保存後可朗讀對話；試聽使用固定句子。');}catch(e){status(e.message,true);}};
 el('speech-close').onclick=()=>el('speech-modal').close();el('speech-modal').addEventListener('close',()=>game.keys.clear());
 el('speech-language').onchange=()=>{storeVoice();const lang=el('speech-language').value;draft.language=lang;if(lang!=='auto')for(const p of Object.values(draft.profiles)){const w=data.windows.find(v=>v.id===p.windows),b=browserVoices.find(v=>v.voiceURI===p.browser);if(w&&w.lang.split('-')[0]!==lang.split('-')[0])p.windows='';if(b&&b.lang.split('-')[0]!==lang.split('-')[0])p.browser='';}showVoice();status('朗讀語言已選擇；保存後生效，不會翻譯台詞。');};
 el('speech-provider').onchange=()=>{storeVoice();if(el('speech-provider').value==='kokoro'){el('speech-model-id').value='kokoro';}provider();};
 el('speech-person').onchange=()=>{storeVoice();actor=el('speech-person').value;showVoice();};
 el('speech-model').onchange=()=>el('speech-model-id').value=el('speech-model').value;
 el('speech-local-voice').onchange=()=>el('speech-local-id').value=el('speech-local-voice').value;
 el('speech-save').onclick=()=>save().catch(e=>status(e.message,true));
 el('speech-preview').onclick=async()=>{try{await save();await play(actor,data.preview,null,true);}catch(e){status(e.message,true);}};
 el('speech-stop').onclick=()=>stop();
 el('speech-modal-stop').onclick=()=>stop();
 el('social-speech-stop').onclick=()=>stop();
 el('speech-probe').onclick=async()=>{try{await save();data=await api('probe');catalogs();status(data.service);}catch(e){status(e.message,true);}};
 el('speech-refresh').onclick=async()=>{try{collect();data=await api('voices');paint();status('本機聲線已重新讀取。');}catch(e){status(e.message,true);}};
 document.addEventListener('visibilitychange',()=>{if(document.hidden)stop();});
 const timer=setInterval(()=>{if(token){clearInterval(timer);load().catch(e=>status(e.message,true));}},300);
})();
