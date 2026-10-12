/* Isolated client behavior tests, with fake DOM/audio; no browser automation. */
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const nodes=new Map(),listeners={},played=[];let timer,held=false;
const element=()=>({value:'',disabled:false,textContent:'',children:[],classList:{toggle(){}},append(x){this.children.push(x)},replaceChildren(){this.children=[]},addEventListener(){},setAttribute(){}});
const doc={hidden:false,getElementById(id){if(!nodes.has(id))nodes.set(id,element());return nodes.get(id)},createElement:element,querySelectorAll(){return[]},addEventListener(){}};
const voices=[{voiceURI:'a',name:'A',lang:'zh-TW',localService:true},{voiceURI:'b',name:'B',lang:'zh-TW',localService:true}];
const config={enabled:true,provider:'browser',auto:true,speed:1,pitch:1,volume:.8,profiles:{'member-02':{browser:'b'}}};
const speech={getVoices:()=>voices,addEventListener:(event,cb)=>listeners[event]=cb,cancel(){},speak(u){played.push({text:u.text,voice:u.voice.name});if(!held)setImmediate(()=>u.onend());}};
const context={document:doc,window:{speechSynthesis:speech},token:'fixture',state:null,game:{keys:{clear(){}}},structuredClone,fetch:async()=>({ok:true,json:async()=>({config,windows:[],models:[],voices:[]})}),setInterval(cb){timer=cb;return 1},clearInterval(){},SpeechSynthesisUtterance:function(text){this.text=text},URL:{revokeObjectURL(){}}};
const stage=path.join(__dirname,'life-upgrade/prototype/web/speech-settings.js'),source=fs.existsSync(stage)?stage:path.join(__dirname,'../prototype/web/speech-settings.js');
vm.createContext(context);vm.runInContext(fs.readFileSync(source,'utf8'),context);
const flush=async()=>{for(let i=0;i<8;i++)await new Promise(setImmediate)};
const event=(id,actor,text)=>({kind:'message_spoken',id,actor,data:{text}});
(async()=>{
 listeners.voiceschanged(); // Voice inventory can arrive before the settings draft.
 timer();await flush();
 context.window.renderSpeech({revision:10,events:[event('old','member-01','舊對話')],social:{groups:[]}});await flush();assert.equal(played.length,0);
 const current={revision:11,events:[event('old','member-01','舊對話'),event('new','member-01','新對話')],social:{groups:[]}};
 context.window.renderSpeech(current);await flush();assert.deepEqual(played,[{text:'新對話',voice:'A'}]);
 context.window.renderSpeech(current);await flush();assert.equal(played.length,1);
 current.revision++;current.social.groups=[{messages:[{id:'group1',actor:'member-02',text:'群聊',tick:12}]}];context.window.renderSpeech(current);await flush();assert.deepEqual(played[1],{text:'群聊',voice:'B'});
 current.events.push(event('player','player','自己的話'));current.revision++;context.window.renderSpeech(current);await flush();assert.equal(played.length,2);
 context.window.resetSpeechHistory();context.window.renderSpeech({revision:999,events:[event('restore','member-01','恢复存檔的歷史')],social:{groups:[]}});await flush();assert.equal(played.length,2);
 held=true;context.window.renderSpeech({revision:1000,events:[event('restore','member-01','恢复存檔的歷史'),event('q1','member-01','第一句'),event('q2','member-02','第二句'),event('q3','member-01','第三句')],social:{groups:[]}});await flush();assert.equal(played.length,3);nodes.get('speech-stop').onclick();await flush();assert.equal(played.length,3);assert.equal(nodes.get('speech-stop').disabled,true);
 console.log('7 speech client behavior checks passed: startup, no historical replay, new line, deduplication, per-character group voice, no player autoread, stop clears queue / restored history baseline.');
})().catch(e=>{console.error(e);process.exitCode=1});

