(function(){
  const API = (document.body.dataset.apiBase || '/api').replace(/\/+$/, '');
  const $ = (s, r=document)=>r.querySelector(s);
  const el = (t,a={},...kids)=>{ const e=document.createElement(t); for(const[k,v] of Object.entries(a)){ if(k==='class') e.className=v; else e.setAttribute(k,v);} kids.forEach(k=>e.append(k?.nodeType? k: document.createTextNode(k))); return e; };
  function todayISO(){ const d=new Date(); const m=String(d.getMonth()+1).padStart(2,'0'); const dd=String(d.getDate()).padStart(2,'0'); return `${d.getFullYear()}-${m}-${dd}`; }
  function setLoading(b){ $('#loading')?.classList.toggle('hidden', !b); }
  function msg(ok, t){ const m=$('#msg'); if(!m) return; m.className = ok? 'ok' : 'err'; m.textContent=t; m.classList.remove('hidden'); clearTimeout(msg._t); msg._t=setTimeout(()=>m.classList.add('hidden'), ok?2000:5000); }

  async function fetchWithAuth(path, opts={}, retry=true){
    const token = localStorage.getItem('access');
    const headers = Object.assign({ 'Authorization':'Bearer '+token }, opts.headers||{});
    const r = await fetch(API+path, Object.assign({}, opts, {headers}));
    if(r.status===401 && retry){
      const refresh = localStorage.getItem('refresh');
      if(refresh){
        const rr = await fetch(API+'/auth/refresh/', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({refresh})});
        if(rr.ok){ const d=await rr.json().catch(()=>({})); if(d.access){ localStorage.setItem('access', d.access); return fetchWithAuth(path, opts, false); } }
      }
    }
    return r;
  }
  async function getJSON(path){ const r=await fetchWithAuth(path); const t=await r.text(); let j=null; try{ j=t?JSON.parse(t):{} }catch{} if(!r.ok) throw new Error((j&&(j.detail||j.error))||t||('HTTP '+r.status)); return j; }

  const childSel = $('#childSel');
  const weekInp  = $('#weekInp');
  const btnLoad  = $('#btnLoad');
  const meta     = $('#meta');
  const empty    = $('#empty');
  const thead    = $('#gridTbl thead');
  const tbody    = $('#gridTbl tbody');

  // init
  weekInp.value = todayISO();

  async function loadChildren(){
    const kids = await getJSON('/parent/children/');
    childSel.innerHTML='';
    kids.forEach(k=> childSel.append(el('option', {value:k.id}, `${k.last_name||''} ${k.first_name||''}`.trim() || `#${k.id}`)));
    if(!kids.length) childSel.append(el('option', {value:''}, 'Farzand topilmadi'));
  }

  function renderGrid(data){
    // header
    thead.innerHTML=''; tbody.innerHTML=''; empty.textContent='';
    const trh = el('tr', {}, el('th', {}, 'Fan'));
    data.days.forEach(d=> trh.append(el('th', {}, d)));
    thead.append(trh);

    // rows
    if(!data.subjects.length){
      empty.textContent = 'Fanlar topilmadi.';
      return;
    }

    let hasAny = false;
    data.subjects.forEach(s=>{
      const tr = el('tr', {}, el('td', {}, s.name));
      data.days.forEach(day=>{
        const cell = (data.grid[String(s.id)]||{})[day];
        if(cell && (cell.score!=null)){ hasAny = true; }
        tr.append(el('td', {class:'cell', title: cell?.comment||''}, cell && cell.score!=null ? String(cell.score) : '—'));
      });
      tbody.append(tr);
    });

    if(!hasAny){
      empty.textContent = 'Bu hafta uchun kundalik baholar mavjud emas.';
    }
  }

  async function loadGrid(){
    const student = childSel.value;
    if(!student){ msg(false, 'Farzandni tanlang'); return; }
    const d = weekInp.value || todayISO();
    setLoading(true);
    try{
      const data = await getJSON(`/grades/daily-by-student/?student=${encodeURIComponent(student)}&week_of=${encodeURIComponent(d)}`);
      meta.textContent = `${data.student.last_name||''} ${data.student.first_name||''} • ${data.student.class_name||''}`.trim();
      renderGrid(data);
    }catch(e){
      msg(false, e.message);
    }finally{
      setLoading(false);
    }
  }

  btnLoad.addEventListener('click', loadGrid);
  weekInp.addEventListener('change', ()=> { if(childSel.value) loadGrid(); });
  childSel.addEventListener('change', ()=> { if(childSel.value) loadGrid(); });

  (async function init(){
    try{
      setLoading(true);
      await loadChildren();
      if(childSel.value) await loadGrid();
    }catch(e){
      msg(false, e.message);
    }finally{
      setLoading(false);
    }
  })();
})();

