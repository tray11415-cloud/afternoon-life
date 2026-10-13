/* Player-operated API and SD setup. Never stores a key in the browser. */
(() => {
 const el=id=>document.getElementById(id);let current=null,working=false;
 const note=(text,error=false)=>{el('connections-status').textContent=text;el('connections-status').classList.toggle('error',error);};
 const option=(select,value,label)=>{const o=document.createElement('option');o.value=value;o.textContent=label;select.append(o);};
 async function api(body){const r=await fetch('/api/connections',body?{method:'POST',headers:{'Content-Type':'application/json','X-Play-Token':token},body:JSON.stringify(body)}:{headers:{'X-Play-Token':token}});const data=await r.json();if(!r.ok)throw Error(data.message||'連線設定無法完成。');return data;}
 async function run(action){if(working)return;working=true;for(const b of el('connections-modal').querySelectorAll('button'))b.disabled=true;try{await action();}catch(error){note(error.message,true);}finally{working=false;for(const b of el('connections-modal').querySelectorAll('button'))b.disabled=false;}}
 function models(){const f=current.sd.folders.find(f=>f.id===el('connections-installation').value);const s=el('connections-checkpoint');s.replaceChildren();option(s,'','先掛載，稍後選擇底模');for(const r of current.sd.resources.filter(r=>r.installations.includes(f?.id)))option(s,r.id,r.name);s.value=f?.id===current.sd.config.installation?current.sd.config.checkpoint:'';}
 function paint(data){current=data;const a=data.ai;el('connections-enabled').checked=a.enabled;el('connections-endpoint').value=a.endpoint;el('connections-remember').disabled=!a.can_remember;el('connections-remember').checked=a.can_remember;
  el('connections-key-state').textContent=a.saved_key?'這台電腦已加密保存金鑰；留空會保留原金鑰。':a.has_key?'已有可用的本機金鑰；留空會保留。':'尚未填入 API 金鑰。';
  for(const [id,value] of [['connections-action-model',a.model],['connections-chat-model',a.dialogue_model]]){const s=el(id);s.replaceChildren();for(const m of a.models)option(s,m,m);s.value=value;}
  const f=el('connections-installation');f.replaceChildren();option(f,'','選擇已偵測的 SD 安裝');for(const folder of data.sd.folders)option(f,folder.id,`${folder.label} — ${folder.path}`);f.value=data.sd.config.installation;
  el('connections-sd-url').value=data.sd.config.url;models();el('connections-mounted').textContent=data.sd.folders.find(f=>f.id===data.sd.config.installation)?.path||'尚未掛載 SD 安裝。';
 }
 el('settings-connections-link').onclick=()=>{el('preferences-modal').close();el('connections-modal').showModal();game.keys.clear();run(async()=>{paint(await api());note('填入後按保存；連線測試與啟動 SD 需另按按鈕。');});};
 const forgetDraft=()=>{el('connections-key').value='';el('connections-key').type='password';el('connections-show-key').checked=false;};
 el('connections-close').onclick=()=>el('connections-modal').close();el('connections-modal').addEventListener('close',forgetDraft);
 el('connections-show-key').onchange=()=>{el('connections-key').type=el('connections-show-key').checked?'text':'password';};
 el('connections-save-ai').onclick=()=>run(async()=>{const data=await api({operation:'save_ai',enabled:el('connections-enabled').checked,key:el('connections-key').value,remember:el('connections-remember').checked,model:el('connections-action-model').value,dialogue_model:el('connections-chat-model').value});const sessionOnly=!!el('connections-key').value&&!el('connections-remember').checked;forgetDraft();paint(data);note(data.message+(sessionOnly?' 新金鑰僅在本次執行使用。':''));const r=await fetch('/api/state');state=await r.json();render(state);});
 el('connections-test-ai').onclick=()=>run(async()=>{note('測試已保存的 API 連線…');const data=await api({operation:'test_ai'});note(data.message);});
 el('connections-browse').onclick=()=>run(async()=>{note('請在資料夾選擇視窗中選擇 SD 安裝。');const data=await api({operation:'browse_sd'});if(data.path){el('connections-path').value=data.path;el('connections-checkpoint').value='';note('已選擇資料夾，請核對服務網址後按掛載。');}else note('已取消選擇資料夾。');});
 el('connections-installation').onchange=()=>{el('connections-path').value='';const f=current.sd.folders.find(f=>f.id===el('connections-installation').value);if(f)el('connections-sd-url').value=f.id===current.sd.config.installation?current.sd.config.url:f.backend==='comfyui'?'http://127.0.0.1:8188':'http://127.0.0.1:7860';models();};
 el('connections-path').oninput=()=>{if(el('connections-path').value.trim())el('connections-checkpoint').value='';};
 el('connections-scan').onclick=()=>run(async()=>{paint(await api({operation:'scan_sd'}));note('已重新讀取本機 SD 安裝清單。');});
 el('connections-mount').onclick=()=>run(async()=>{const data=await api({operation:'mount_sd',path:el('connections-path').value,installation:el('connections-installation').value,url:el('connections-sd-url').value,checkpoint:el('connections-checkpoint').value});paint(data);el('connections-path').value='';note(data.message);});
 el('connections-test-sd').onclick=()=>run(async()=>{note('測試已保存的本機 SD 服務…');const data=await api({operation:'test_sd'});note(data.message,!data.sd.service.ready);});
 el('connections-advanced').onclick=()=>{el('connections-modal').close();el('art-open').click();};
})();
