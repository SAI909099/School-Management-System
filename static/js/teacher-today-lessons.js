(function(){
  const API_BASE=(window.API_BASE||'/api/').replace(/\/+$/,'');
  const access=localStorage.getItem('access');
  if(!access){ return; } // teacher page already guards; fail quietly
  const HEADERS={'Content-Type':'application/json','Authorization':'Bearer '+access};

  const target=document.getElementById('today-lessons');
  if(!target) return;

  const WEEKDAY_MAP={1:'Dushanba',2:'Seshanba',3:'Chorshanba',4:'Payshanba',5:'Juma',6:'Shanba'};
  const now=new Date();
  const todayW=(d=> (d===0?7:d))(now.getDay()); // Mon..Sat = 1..6  (Sun->7)
  const pad=n=>String(n).padStart(2,'0');
  const hm=()=> pad(now.getHours())+':'+pad(now.getMinutes());

  function el(t,a={},...kids){const e=document.createElement(t);for(const[k,v]of Object.entries(a)){if(k==='class')e.className=v;else if(v!=null)e.setAttribute(k,v);}kids.forEach(x=>e.append(x instanceof Node?x:document.createTextNode(x)));return e;}

  async function api(path){
    const url=path.startsWith('http')?path:API_BASE+(path.startsWith('/')?path:'/'+path);
    const r=await fetch(url,{headers:HEADERS});
    if(!r.ok) throw new Error(await r.text().catch(()=>`HTTP ${r.status}`));
    return r.json();
  }

  function statusFor(entry){
    const cur=hm();
    const st=(entry.start_time||'').slice(0,5);
    const et=(entry.end_time||'').slice(0,5);
    if(!st||!et) return '';
    if (cur>=st && cur<=et) return ' — davom etmoqda ⏱️';
    if (cur<st) return ' — yaqinlashmoqda ⏰';
    return '';
  }

  async function init(){
    target.innerHTML = 'Yuklanmoqda...';
    try{
      const all=await api('/schedule/teacher/me/');
      const today=all.filter(x=>x.weekday===todayW)
                     .sort((a,b)=>String(a.start_time).localeCompare(String(b.start_time)));
      if(!today.length){
        target.innerHTML = `<div class="empty">Bugun (${WEEKDAY_MAP[todayW]}) dars yo‘q.</div>`;
        return;
      }
      const list=el('div',{class:'list'});
      today.forEach(e=>{
        const st=(e.start_time||'').slice(0,5), et=(e.end_time||'').slice(0,5);
        const row=el('div',{class:'row',style:'display:flex;align-items:center;gap:10px;padding:8px 10px;border:1px solid #eee;border-radius:8px;background:#fff;margin-bottom:8px;'},
          el('div',{class:'time',style:'min-width:100px;font-weight:600;'}, `${st}–${et}`),
          el('div',{class:'info',style:'flex:1;'},
            el('div',{}, `Fan: ${e.subject_name||''}`),
            el('div',{}, `Sinf: ${e.class_name||''}${e.room? ' · Xona: '+e.room : ''}`)
          ),
          el('div',{class:'hint',style:'color:#666;'}, statusFor(e))
        );
        list.append(row);
      });
      target.innerHTML='';
      target.append(list);
    }catch(e){
      console.error(e);
      target.innerHTML = '<div class="err">Yuklashda xatolik</div>';
    }
  }

  init();
})();
