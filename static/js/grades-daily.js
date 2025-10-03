/* static/js/grades-daily.js */
(function(){
  const API = (window.API_BASE || '/api').replace(/\/+$/,'');
  const access = localStorage.getItem('access');
  if (!access) { window.location.replace('/'); return; }
  const HEADERS = { 'Content-Type':'application/json', 'Authorization':'Bearer '+access };

  const $ = (s, r=document)=>r.querySelector(s);
  const el = (t,a={},...kids)=>{const e=document.createElement(t);
    for(const[k,v] of Object.entries(a)){ if(k==='class') e.className=v; else if(v!=null) e.setAttribute(k,v); }
    kids.forEach(k=>e.append(k instanceof Node?k:document.createTextNode(k)));
    return e;
  };

  const classSel = $('#classSel');
  const subjectSel = $('#subjectSel');
  const weekInp = $('#weekInp');
  const btnLoad = $('#btnLoad');
  const theadRow = $('#theadRow');
  const tbody = $('#tbl tbody');
  const whoBadge = $('#whoBadge');

  function todayISO(){
    const d=new Date(); const m=String(d.getMonth()+1).padStart(2,'0'); const dd=String(d.getDate()).padStart(2,'0');
    return `${d.getFullYear()}-${m}-${dd}`;
  }
  weekInp.value = todayISO();

  async function apiGET(path){
    const r = await fetch(API+path, { headers: HEADERS });
    if(!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
  }

  async function loadRole(){
    try { const me=await apiGET('/auth/me/'); whoBadge.textContent = `Rol: ${me.role || me.user?.role || '—'}`; }
    catch { whoBadge.textContent = 'Rol: —'; }
  }
  async function loadClasses(){
    const data = await apiGET('/dir/classes/');
    (data||[]).forEach(c=> classSel.append(el('option',{value:c.id}, c.name)));
  }
  async function loadTeacherDefaultClass(){
    try{
      const mine = await apiGET('/teacher/classes/me/');
      if(Array.isArray(mine)&&mine.length){
        const firstId = String(mine[0].id);
        if (![...classSel.options].some(o=>o.value===firstId)){
          classSel.append(el('option',{value:firstId}, mine[0].name||`Sinf #${firstId}`));
        }
        classSel.value = firstId;
      }
    }catch(_){}
  }
  async function loadSubjects(){
    const data = await apiGET('/subjects/');
    subjectSel.innerHTML='';
    subjectSel.append(el('option',{value:''}, '— tanlang —'));
    (data||[]).forEach(s=> subjectSel.append(el('option',{value:s.id}, `${s.name} (${s.code})`)));
  }

  function renderGrid(students, days, grid){
    // header
    theadRow.innerHTML='';
    theadRow.append(
      el('th', {style:'width:60px;'}, '№'),
      el('th', {}, 'Familiya Ism'),
      ...days.map(d => el('th', {}, d))
    );
    // body
    tbody.innerHTML='';
    if(!students.length){
      tbody.append(el('tr',{}, el('td',{colspan:2+days.length}, 'O‘quvchilar topilmadi.')));
      return;
    }
    students.forEach((s,idx)=>{
      const row = el('tr',{},
        el('td',{}, String(idx+1)),
        el('td',{}, `${s.last_name||''} ${s.first_name||''}`.trim()),
        ...days.map(d=>{
          const cell = (grid[String(s.id)]||{})[d];
          const txt = cell ? String(cell.score) : '';
          const title = cell && cell.comment ? cell.comment : '';
          return el('td', {title}, el('span', {class:'score'}, txt));
        })
      );
      tbody.append(row);
    });
  }

  async function loadDaily(){
    const classId = classSel.value;
    const subjectId = subjectSel.value;
    const wk = weekInp.value;
    if(!classId){ alert('Sinf tanlanmadi'); return; }
    if(!subjectId){ alert('Fan tanlanmadi'); return; }
    const data = await apiGET(`/grades/daily-grid/?class=${classId}&subject=${subjectId}&week_of=${wk}`);
    renderGrid(data.students || [], data.days || [], data.grid || {});
  }

  btnLoad.addEventListener('click', loadDaily);

  (async function init(){
    await Promise.all([loadRole(), loadClasses(), loadSubjects()]);
    await loadTeacherDefaultClass();
  })();
})();
