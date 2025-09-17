(function(){
  const API_BASE=(window.API_BASE||'/api/').replace(/\/+$/,'');
  const access=localStorage.getItem('access');
  if(!access){ window.location.href='/login/'; return; }
  const HEADERS={'Content-Type':'application/json','Authorization':'Bearer '+access};

  const qs=(s,r=document)=>r.querySelector(s);
  const el=(t,a={},...k)=>{const e=document.createElement(t);for(const[n,v]of Object.entries(a)){if(n==='class')e.className=v;else if(v!=null)e.setAttribute(n,v);}k.forEach(x=>e.append(x instanceof Node?x:document.createTextNode(x)));return e;};
  async function api(path){ const url=path.startsWith('http')?path:API_BASE+(path.startsWith('/')?path:'/'+path);
    const r=await fetch(url,{headers:HEADERS}); if(!r.ok) throw new Error(await r.text().catch(()=>`HTTP ${r.status}`)); return r.json();
  }

  const classSel=qs('#classSel');
  const tbl=qs('#tbl'); const meta=qs('#meta');
  const btnReload=qs('#btnReload'); const btnPrint=qs('#btnPrint');
  const msg=qs('#msg');
  const ok=t=>{msg.className='ok';msg.textContent=t;msg.classList.remove('hidden');};
  const err=t=>{msg.className='err';msg.textContent=t;msg.classList.remove('hidden');};
  const hide=()=>msg.classList.add('hidden');

  let CLASSES=[], SELECTED_C=null;

  function defaultTimes(n){
    const starts=['08:30','09:25','10:20','11:15','12:10','13:05','14:00','14:55','15:50','16:45'];
    const ends  =['09:15','10:10','11:05','12:00','12:55','13:50','14:45','15:40','16:35','17:30'];
    return Array.from({length:n},(_,i)=>({start:starts[i]||'', end:ends[i]||''}));
  }

  async function init(){
    hide();
    // load classes for dropdown
    CLASSES = await api('/classes/');
    classSel.innerHTML='';
    CLASSES
      .slice()
      .sort((a,b)=> String(a.name).localeCompare(String(b.name)))
      .forEach(c=> classSel.append(el('option',{value:c.id}, c.name)));

    // deep-link support: ?class=<id>
    const url = new URL(window.location.href);
    const cParam = url.searchParams.get('class');
    if(cParam && CLASSES.some(c=> String(c.id)===String(cParam))){
      classSel.value = String(cParam);
    }

    await buildForSelected();
    ok('Jadval yuklandi ✅');
  }

  classSel.addEventListener('change', buildForSelected);
  btnReload.addEventListener('click', buildForSelected);
  btnPrint.addEventListener('click', ()=> window.print());

  async function buildForSelected(){
    hide(); tbl.innerHTML='';
    const cId = Number(classSel.value||0);
    if(!cId){ err('Sinf tanlanmagan'); return; }
    SELECTED_C = CLASSES.find(c=>c.id===cId) || null;

    // Use optimized endpoint for class:
    const data = await api(`/schedule/class/${cId}/`);

    // Group by weekday & sort by start_time
    const byWd = {1:[],2:[],3:[],4:[],5:[],6:[]};
    data.forEach(x=> { if(byWd[x.weekday]) byWd[x.weekday].push(x); });
    Object.values(byWd).forEach(a => a.sort((a,b)=> String(a.start_time).localeCompare(String(b.start_time)) ));

    const maxRows = Math.max(...Object.values(byWd).map(a=>a.length), 0);
    const rowCount = Math.max(1, maxRows || 8);
    const times = defaultTimes(rowCount);

    const thead = el('thead',{}, el('tr',{},
      el('th',{}, '№ / vaqt'),
      el('th',{}, 'Dushanba'),
      el('th',{}, 'Seshanba'),
      el('th',{}, 'Chorshanba'),
      el('th',{}, 'Payshanba'),
      el('th',{}, 'Juma'),
      el('th',{}, 'Shanba'),
    ));
    const tbody = el('tbody',{});

    for(let i=0;i<rowCount;i++){
      const tr=el('tr',{});
      const tm = times[i]||{start:'',end:''};
      tr.append(el('td',{}, `#${i+1} ${tm.start}–${tm.end}`));

      for(let wd=1; wd<=6; wd++){
        const e = byWd[wd][i];
        if(e){
          const line1 = e.subject_name ? `Fan: ${e.subject_name}` : '';
          const line2 = e.teacher_name ? `O‘qituvchi: ${e.teacher_name}` : '';
          const line3 = e.room         ? `Xona: ${e.room}`         : '';
          tr.append(el('td',{}, el('div',{class:'slot'},
            el('b',{}, `${(e.start_time||'').slice(0,5)}–${(e.end_time||'').slice(0,5)}`),
            [line1, line2, line3].filter(Boolean).join('\n')
          )));
        }else{
          tr.append(el('td',{}, ''));
        }
      }
      tbody.append(tr);
    }
    tbl.append(thead, tbody);

    meta.textContent = `Sinf: ${SELECTED_C?.name || '—'}`;
  }

  init().catch(e=> err('Yuklashda xatolik: '+e.message));
})();
