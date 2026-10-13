/* SD-first character art workflow; explicit generation and display application. */
(() => {
 const el=id=>document.getElementById(id),sdTabs=['sd-art','sd-portrait','sd-cg'];let data=null,tabName='sd-art',version=0,working=false,actor=null,bindingBefore=null,loadingForm=false;
 const context=()=>window.CharacterBridge.read(),active=()=>sdTabs.includes(tabName),status=text=>el('atelier-status').textContent=text;
 async function request(params){const r=await fetch('/api/art',{method:'POST',headers:{'Content-Type':'application/json','X-Play-Token':token},body:JSON.stringify({operation:'atelier',params})}),d=await r.json();if(!r.ok)throw Error(d.message||'美術操作無法完成。');return d;}
 function option(select,value,text){const o=document.createElement('option');o.value=value;o.textContent=text;select.append(o);}
 function preview(url,kind,frames=3){
  const image=el('atelier-image'),canvas=el('maker-canvas');image.hidden=!url||kind==='pixel';canvas.hidden=kind!=='pixel';el('atelier-empty').hidden=!!url;el('maker-preview-status').textContent=url?'SD 素材預覽；按套用才更新遊戲。':'尚未生成或套用 SD 素材。';el('maker-canvas').closest('.maker-preview').classList.toggle('sd-sprite',kind==='pixel');
  if(url&&kind==='pixel')window.CharacterMaker.generated(url,frames);else if(url)image.src=url;else image.removeAttribute('src');
 }
 function configureView(){
  bindingBefore=data.atelier.bindings[actor];const c=data.config,p=c.profiles[actor],outfit=data.atelier.outfits[actor],folder=data.folders.find(f=>f.id===c.installation),model=data.resources.find(r=>r.id===c.checkpoint);
  el('atelier-connection').textContent=(folder?.label||'未選 SD 安裝')+' · '+(model?.name||'未選底模')+' · '+(data.service.ready?'SD 已連線':'SD 尚未連線');
  el('atelier-outfit').textContent='當下穿著：'+outfit.title;
  const select=el('atelier-lora');select.replaceChildren();option(select,'','選擇角色 LoRA（尚未綁定）');for(const r of data.resources.filter(r=>r.selectable&&r.category==='lora'&&r.installations.includes(c.installation)))option(select,r.id,r.name);select.value=p.lora;
  for(const field of ['weight','seed','trigger','identity'])el('atelier-'+field).value=p[field];
  el('atelier-expressions').textContent='表情差分：'+c.expressions.map(e=>data.expression_labels[e]).join('、');
  const scene=el('atelier-scene'),old=scene.value;scene.replaceChildren();for(const [id,name] of Object.entries(data.atelier.public_scenes))option(scene,id,name);scene.value=Object.hasOwn(data.atelier.public_scenes,old)?old:Object.hasOwn(data.atelier.public_scenes,data.atelier.default_scene)?data.atelier.default_scene:'shared';
  updateControls();const installed=c.active[actor+':'+outfit.render_key];if(tabName==='sd-cg'){const cg=data.atelier.cg;preview(cg?.actor===actor?cg.url:null,'cg');}else if(tabName==='sd-art'&&installed?.sprite){preview('/character-art/'+installed.sprite,'pixel',installed.frames||3);}else if(installed?.portraits){const file=installed.portraits[installed.expression||'neutral'];preview(file?'/character-art/'+file:null,'portrait');}else preview(null,'portrait');
 }
 function updateControls(){const template=context().mode!=='current';const p=data?.config.profiles[actor];const dirty=!p||['lora','weight','seed','trigger','identity'].some(k=>String(el('atelier-'+k).value)!==String(p[k]));for(const id of ['atelier-pixel','atelier-both','atelier-portrait','atelier-cg'])el(id).disabled=working||template||dirty;el('atelier-restore').disabled=working||template;if(template)status('新遊戲模板請先建立人物，再生成該人物目前穿著的 SD 美術。');}
 function jobs(){
  if(!data)return;const box=el('atelier-jobs');box.replaceChildren();const kinds=tabName==='sd-cg'?['cg']:tabName==='sd-portrait'?['portrait','both']:['pixel','both'];const rows=data.jobs.filter(j=>j.actor===actor&&kinds.includes(j.kind));
  if(!rows.length){const p=document.createElement('p');p.textContent='這位人物還沒有此用途的 SD 任務。';box.append(p);return;}
  const labels={queued:'等待 GPU',running:'生成中',ready:'完成',failed:'失敗',cancelled:'已取消',interrupted:'已中斷'};
  for(const j of [...rows].reverse()){
   const card=document.createElement('section');card.className='atelier-job';const h=document.createElement('h4');h.textContent=(j.kind==='cg'?'CG':j.kind==='both'?'立繪＋像素':j.kind==='pixel'?'像素行走':'立繪差分')+' · '+labels[j.status];const note=document.createElement('p');note.textContent=j.outfit.title+' · '+j.message;card.append(h,note);const bar=document.createElement('progress');bar.max=j.total;bar.value=j.done;card.append(bar);
   if(['queued','running'].includes(j.status)){const b=document.createElement('button');b.textContent='取消此任務';b.onclick=()=>run(async()=>{const r=await fetch('/api/art',{method:'POST',headers:{'Content-Type':'application/json','X-Play-Token':token},body:JSON.stringify({operation:'cancel',params:{id:j.id}})});if(!r.ok)throw Error('取消失敗');await load(false);});card.append(b);}
   if(j.status==='ready'){
    const thumbs=document.createElement('div');thumbs.className='atelier-thumbs';
    function thumb(file,label,kind){const b=document.createElement('button'),im=document.createElement('img');im.src='/character-art/'+file;im.alt=label;im.loading='lazy';b.append(im,document.createTextNode(label));if(kind==='cg')b.className='cg';b.onclick=()=>preview(im.src,kind,j.frames||3);thumbs.append(b);}
    for(const [e,file] of Object.entries(j.files.portraits||{}))thumb(file,data.expression_labels[e],'portrait');if(j.files.sprite)thumb(j.files.sprite,'四方向行走表','pixel');if(j.files.cg)thumb(j.files.cg,'CG 預覽','cg');card.append(thumbs);
    const toolbar=document.createElement('div');toolbar.className='studio-actions';const expression=document.createElement('select');expression.setAttribute('aria-label','套用表情差分');for(const e of Object.keys(j.files.portraits||{neutral:''}))option(expression,e,data.expression_labels[e]);
    const b=document.createElement('button');b.disabled=working||context().mode!=='current';b.textContent=j.kind==='cg'?'套用為目前 CG':'套用這套 SD 素材';const owner=j.actor;b.onclick=()=>run(async()=>{const result=await request({command:'apply',actor:owner,id:j.id,expression:expression.value});if(context().actor===owner){data=result;jobs();if(j.files.cg)preview('/character-art/'+j.files.cg,'cg');else if(j.files.portraits?.[expression.value])preview('/character-art/'+j.files.portraits[expression.value],'portrait');else if(j.files.sprite)preview('/character-art/'+j.files.sprite,'pixel');status(j.kind==='cg'?'CG 已套用，可在 CG 插圖中查看。':'SD 素材已套用；原生與匯入美術保留作為備援。');}await send('ui_hold',{},true);});
    if(j.files.portraits)toolbar.append(expression);toolbar.append(b);card.append(toolbar);
   }box.append(card);
  }
 }
 async function load(forms=true){if(forms)loadingForm=true;const turn=++version,who=context().actor;try{const d=await request({command:'state'});if(turn!==version||context().actor!==who)return;data=d;actor=who;if(forms)configureView();jobs();}catch(e){if(turn===version)status(e.message);}finally{if(forms&&turn===version)loadingForm=false;}}
 async function run(action){if(working)return;working=true;updateControls();try{await action();}catch(e){status(e.message);}finally{working=false;updateControls();}}
 async function generate(kind){const who=context().actor;await run(async()=>{data=await request({command:'generate',actor:who,kind,scene:kind==='cg'?el('atelier-scene').value:null,description:kind==='cg'?el('atelier-description').value:''});jobs();status('已排入本機 SD 生成，完成後請預覽並套用。');});}
 el('atelier-binding').onclick=()=>run(async()=>{if(!data)return;const who=context().actor,p={...data.config.profiles[who]};for(const field of ['lora','trigger','identity'])p[field]=el('atelier-'+field).value;p.weight=Number(el('atelier-weight').value);p.seed=Number(el('atelier-seed').value);data=await request({command:'binding',actor:who,profile:p,before:bindingBefore});configureView();jobs();status('這位人物的 SD 配方已保存。');});
 el('atelier-refresh').onclick=()=>load();for(const [id,kind] of [['atelier-pixel','pixel'],['atelier-both','both'],['atelier-portrait','portrait'],['atelier-cg','cg']])el(id).onclick=()=>generate(kind);
 el('atelier-restore').onclick=()=>run(async()=>{data=await request({command:'restore',actor:context().actor});configureView();jobs();await send('ui_hold',{},true);status('已恢復備援美術，SD 生成檔仍保留。');});
 el('atelier-settings').onclick=()=>{window.CharacterBridge.read();window.characterArtIntent=context().actor;el('creation-modal').close();el('art-modal').addEventListener('close',()=>window.resumeCharacterMaker(),{once:true});el('art-open').click();};
 el('atelier-gallery').onclick=async()=>{await send('ui_hold',{},true);el('creation-modal').close();el('illustration-modal').addEventListener('close',()=>window.resumeCharacterMaker(),{once:true});el('illustration-open').click();};
 function tab(name){tabName=name;if(active())el('atelier-profile-nav').open=false;el('atelier-common').hidden=!active();el('atelier-results').hidden=!active();el('look-enabled').closest('label').hidden=active();el('creation-live').hidden=active()||context().mode!=='current';el('creation-save').hidden=active()||context().mode!=='template';if(active()){preview(null,'portrait');if(data){jobs();updateControls();if(name==='sd-cg'&&data.atelier.cg?.actor===actor)preview(data.atelier.cg.url,'cg');}}else{el('atelier-image').hidden=true;el('atelier-empty').hidden=true;el('maker-canvas').hidden=false;el('maker-canvas').closest('.maker-preview').classList.remove('sd-sprite');window.CharacterMaker.refresh();}}
 for(const field of ['lora','weight','seed','trigger','identity'])el('atelier-'+field).addEventListener('input',()=>{updateControls();status('SD 配方改動請先保存，再生成。');});
 window.SDAtelier={active,show(){actor=context().actor;tab(tabName);load();},tab};
 setInterval(()=>{if(el('creation-modal').open&&active()&&!working&&!loadingForm&&data)load(false);},2500);
})();
