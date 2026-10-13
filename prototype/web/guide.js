(()=>{const articles=[...document.querySelectorAll('article')],links=[...document.querySelectorAll('nav a')],search=document.getElementById('guide-search'),dialog=document.getElementById('guide-image');search.addEventListener('input',()=>{const term=search.value.trim().toLocaleLowerCase();articles.forEach((a,i)=>{a.hidden=!a.textContent.toLocaleLowerCase().includes(term);links[i].hidden=a.hidden;});document.getElementById('guide-empty').hidden=articles.some(a=>!a.hidden);});for(const b of document.querySelectorAll('.image-open'))b.addEventListener('click',()=>{const image=b.querySelector('img');dialog.querySelector('img').src=image.src;dialog.querySelector('img').alt=image.alt;dialog.showModal();});document.getElementById('guide-image-close').onclick=()=>dialog.close();})();
(()=>{
 const select=document.getElementById('guide-language');if(!select)return;
 const langs=['zh-TW','zh-CN','ja','en'],current=document.documentElement.dataset.language||'zh-TW';
 const target=lang=>location.protocol==='file:'?'afternoon-life-player-guide.'+lang+'.html':'/guide.'+lang+'.html';
 select.value=current;select.onchange=()=>{location.href=target(select.value)+location.hash;};
 const requested=new URLSearchParams(location.search).get('lang');let preferred=requested;
 if(!preferred&&location.pathname==='/guide.html'){try{preferred=localStorage.getItem('lifebox.language');}catch{}}
 if(langs.includes(preferred)&&preferred!==current)location.replace(target(preferred)+location.hash);
})();
