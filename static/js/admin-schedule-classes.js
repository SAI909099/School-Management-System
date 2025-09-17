(function(){
  // ===== Auth & API =====
  const API_BASE = (window.API_BASE || '/api/').replace(/\/+$/, '');
  const access = localStorage.getItem('access');
  if(!access){ window.location.href='/login/'; return; }
  const HEADERS = { 'Content-Type':'application/json', 'Authorization':'Bearer '+access };

  async function tryRefresh(){
    const refresh = localStorage.getItem('refresh'); if(!refresh) return false;
    const r = await fetch(API_BASE+'/auth/refresh/', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({refresh})});
    if(!r.ok) return false; const data = await r.json().catch(()=>({}));
    if(data.access){ localStorage.setItem('access', data.access); HEADERS.Authorization='Bearer '+data.access; return true; }
    return false;
  }
  async function api(path, opts={}){
    const url = path.startsWith('http')? path : API_BASE + (path.startsWith('/')?path:'/'+path);
    const res = await fetch(url, {headers:HEADERS, ...opts});
    if(res.status===401){ const rf = await tryRefresh(); if(rf) return api(path, opts); localStorage.clear(); window.location.href='/login/'; return; }
    if(!res.ok){ const t = await res.text().catch(()=> ''); throw new Error(t || `HTTP ${res.status}`); }
    return res.json();
  }

  // ===== DOM =====
  const msg = document.getElementById('msg');
  function ok(t){ msg.className='ok'; msg.textContent=t; msg.classList.remove('hidden'); }
  function err(t){ msg.className='err'; msg.textContent=t; msg.classList.remove('hidden'); }
  function hideMsg(){ msg.classList.add('hidden'); }

  const classSearch = document.getElementById('classSearch');
  const classesList = document.getElementById('classesList');
  const periodCount = document.getElementById('periodCount');
  const timeTemplate= document.getElementById('timeTemplate');
  const btnBuild    = document.getElementById('btnBuild');
  const btnLoad     = document.getElementById('btnLoad');
  const btnSaveAll  = document.getElementById('btnSaveAll');
  const btnPrint    = document.getElementById('btnPrint');
  const table       = document.getElementById('timetable');
  const currentClass= document.getElementById('currentClass');

  // ===== Data caches =====
  let CLASSES=[], SUBJECTS=[], TEACHERS=[];
  let SELECTED_CLASS=null;
  // cell key: `${weekday}_${period}` → existing schedule entry or null
  let CELL_MAP=new Map();

  function el(t,attrs={},...kids){
    const e=document.createElement(t);
    for(const [k,v] of Object.entries(attrs)){ if(k==='class') e.className=v; else if(v!=null) e.setAttribute(k,v); }
    for(const k of kids){ e.append(k instanceof Node? k : document.createTextNode(k)); }
    return e;
  }

  // ---- helper: fill teacher options filtered by specialty (subject id)
  function fillTeacherOptions(selectEl, subjectId, preselectValue){
    selectEl.innerHTML = '';
    const placeholder = el('option',{value:''}, '— o‘qituvchi —');
    selectEl.append(placeholder);

    let count = 0;
    const wanted = subjectId ? Number(subjectId) : null;
    TEACHERS.forEach(t=>{
      // serializer provides t.specialty (id) and t.specialty_name
      const specId = t.specialty ?? null;
      if (!wanted || (specId && Number(specId) === wanted)){
        const txt = t.user_full_name || ('#'+t.user);
        const opt = el('option', {value: t.id}, txt + (t.specialty_name ? (' — '+t.specialty_name) : ''));
        selectEl.append(opt);
        count++;
      }
    });

    if(count === 0){
      selectEl.append(el('option',{value:'', disabled:true}, 'Mos o‘qituvchi topilmadi'));
    }

    if(preselectValue != null){
      selectEl.value = String(preselectValue);
      // if filtered out, ensure it stays empty
      if(selectEl.value !== String(preselectValue)) selectEl.value = '';
    }
  }

  // ===== Load lookups =====
  async function loadLookups(){
    const me = await api('/auth/me/');
    if(!['admin','registrar'].includes(me?.role)){
      if(me?.role==='teacher') window.location.href='/teachers/';
      else if(me?.role==='parent') window.location.href='/otaona/';
      else window.location.href='/';
      return false;
    }
    [CLASSES, SUBJECTS, TEACHERS] = await Promise.all([
      api('/classes/'),
      api('/subjects/'),
      api('/teachers/')
    ]);
    return true;
  }

  // ===== Render class list =====
  function renderClassList(){
    classesList.innerHTML='';
    const q=(classSearch.value||'').toLowerCase().trim();
    const list = CLASSES
      .slice()
      .sort((a,b)=>String(a.name).localeCompare(String(b.name)))
      .filter(c => !q || String(c.name).toLowerCase().includes(q));
    list.forEach(c=>{
      const item = el('div',{class:'class-item', 'data-id':c.id}, c.name);
      if(SELECTED_CLASS && c.id===SELECTED_CLASS.id) item.classList.add('active');
      item.addEventListener('click', ()=> { SELECTED_CLASS=c; renderClassList(); setCurrentClassBadge(); buildGrid(); loadScheduleForClass(); });
      classesList.appendChild(item);
    });
  }
  classSearch.addEventListener('input', renderClassList);

  function setCurrentClassBadge(){ currentClass.textContent = 'Sinf: ' + (SELECTED_CLASS?.name || '—'); }

  // ===== Grid builder =====
  function defaultTimes(n){
    const starts = ['08:30','09:25','10:20','11:15','12:10','13:05','14:00','14:55','15:50','16:45','17:40','18:35'];
    const ends   = ['09:15','10:10','11:05','12:00','12:55','13:50','14:45','15:40','16:35','17:30','18:25','19:20'];
    return Array.from({length:n}, (_,i)=>({start: starts[i]||'08:30', end: ends[i]||'09:15'}));
  }

  function buildGrid(){
    hideMsg(); CELL_MAP.clear(); table.innerHTML='';
    const n = Math.max(1, Math.min(12, Number(periodCount.value||8)));
    const times = timeTemplate.value==='default' ? defaultTimes(n) : Array.from({length:n}, ()=>({start:'', end:''}));

    const head = el('thead',{}, el('tr',{},
      el('th',{},'№ / vaqt'),
      el('th',{},'Dushanba'),
      el('th',{},'Seshanba'),
      el('th',{},'Chorshanba'),
      el('th',{},'Payshanba'),
      el('th',{},'Juma'),
      el('th',{},'Shanba'),
    ));
    const body = el('tbody',{});

    for(let p=1;p<=n;p++){
      const tr=el('tr',{});
      const timeTd=el('td',{style:'min-width:210px;'});
      const tbox=el('div',{class:'timebox'},
        el('span',{},'#'+p),
        el('input',{type:'time','data-role':'start', value:times[p-1].start||''}),
        el('input',{type:'time','data-role':'end',   value:times[p-1].end||''})
      );
      timeTd.append(tbox);
      tr.append(timeTd);

      for(let wd=1; wd<=6; wd++){
        const td = el('td', {});
        const key = `${wd}_${p}`;

        // subject select
        const subjSel = el('select', {'data-role':'subject'});
        subjSel.append(el('option',{value:''},'— fan —'));
        SUBJECTS.forEach(s=> subjSel.append(el('option',{value:s.id}, s.name)));

        // teacher select (will be filtered by subject)
        const teachSel = el('select', {'data-role':'teacher'});

        // initially show all teachers until subject chosen
        fillTeacherOptions(teachSel, null, null);

        const roomInp = el('input', {type:'text','data-role':'room', placeholder:'xona', class:'room'});

        // when subject changes → refilter teachers
        subjSel.addEventListener('change', ()=>{
          const currentChosenTeacher = teachSel.value || null;
          fillTeacherOptions(teachSel, subjSel.value || null, currentChosenTeacher);
        });

        const wrap = el('div', {'data-key':key, class:'cell-wrap'}, subjSel, teachSel, roomInp);
        td.append(wrap);
        tr.append(td);
      }
      body.append(tr);
    }
    table.append(head, body);
  }

  // ===== Load existing class schedule & fill cells by time order
  async function loadScheduleForClass(){
    if(!SELECTED_CLASS) return;
    const data = await api(`/schedule/class/${SELECTED_CLASS.id}/`);
    // group by weekday, order by time
    const byWd = {1:[],2:[],3:[],4:[],5:[],6:[]};
    data.forEach(x=> { if(byWd[x.weekday]) byWd[x.weekday].push(x); });
    Object.values(byWd).forEach(arr=> arr.sort((a,b)=> String(a.start_time).localeCompare(String(b.start_time)) ));

    const rows = Array.from(table.querySelectorAll('tbody tr'));
    rows.forEach((tr,rowIdx)=>{
      const period=rowIdx+1;
      for(let wd=1; wd<=6; wd++){
        const key=`${wd}_${period}`;
        const container = tr.children[wd].querySelector(`[data-key="${key}"]`);
        const subjSel = container.querySelector('[data-role="subject"]');
        const teachSel= container.querySelector('[data-role="teacher"]');
        const roomInp = container.querySelector('[data-role="room"]');
        const entry = byWd[wd][rowIdx] || null;

        if(entry){
          // 1) set subject
          subjSel.value  = String(entry.subject);
          // 2) refilter teachers based on that subject, then set teacher
          fillTeacherOptions(teachSel, subjSel.value, String(entry.teacher));
          // 3) room
          roomInp.value  = entry.room || '';
          CELL_MAP.set(key, entry);
        }else{
          // keep selects empty; ensure teacher list is filtered by (empty) subject = all
          fillTeacherOptions(teachSel, null, null);
          roomInp.value = '';
          CELL_MAP.set(key, null);
        }
      }
    });

    ok('Mavjud jadval yuklandi ✅');
    runConflicts(); // highlight if any
  }

  // ===== Conflict detection (teacher/time & room/time collisions)
  function runConflicts(){
    table.querySelectorAll('.conflict').forEach(n=> n.classList.remove('conflict'));

    const rows = Array.from(table.querySelectorAll('tbody tr'));
    const seenTeach = new Map();
    const seenRoom  = new Map();

    rows.forEach((tr,rowIdx)=>{
      const period=rowIdx+1;
      for(let wd=1; wd<=6; wd++){
        const container = tr.children[wd].querySelector('.cell-wrap');
        const subjSel = container.querySelector('[data-role="subject"]');
        const teachSel= container.querySelector('[data-role="teacher"]');
        const roomInp = container.querySelector('[data-role="room"]');

        const teach=teachSel.value, room=(roomInp.value||'').trim();
        if(teach){
          const key = `${teach}_${wd}_${period}`;
          if(seenTeach.has(key)){ container.classList.add('conflict'); seenTeach.get(key).classList.add('conflict'); }
          else seenTeach.set(key, container);
        }
        if(room){
          const key2 = `${room}_${wd}_${period}`;
          if(seenRoom.has(key2)){ container.classList.add('conflict'); seenRoom.get(key2).classList.add('conflict'); }
          else seenRoom.set(key2, container);
        }
      }
    });
  }

  table.addEventListener('change', (e)=>{
    if(e.target.matches('select, input')) runConflicts();
  });

  // ===== Save all for class
  async function saveAll(){
    hideMsg();
    if(!SELECTED_CLASS){ err('Sinf tanlanmagan.'); return; }

    const rows = Array.from(table.querySelectorAll('tbody tr'));
    const ops = [];

    rows.forEach((tr,rowIdx)=>{
      const period=rowIdx+1;
      const timeInputs = tr.querySelectorAll('input[type="time"]');
      const start = timeInputs[0]?.value || '';
      const end   = timeInputs[1]?.value || '';

      for(let wd=1; wd<=6; wd++){
        const td = tr.children[wd];
        const container = td.querySelector(`[data-key="${wd}_${period}"]`);
        const subjSel = container.querySelector('[data-role="subject"]');
        const teachSel= container.querySelector('[data-role="teacher"]');
        const roomInp = container.querySelector('[data-role="room"]');

        const subject = subjSel.value ? Number(subjSel.value) : null;
        const teacher = teachSel.value ? Number(teachSel.value) : null;
        const room = (roomInp.value||'').trim();

        const existing = CELL_MAP.get(`${wd}_${period}`) || null;

        if(subject && teacher && start && end){
          const payload = JSON.stringify({
            clazz: SELECTED_CLASS.id, subject, teacher, weekday: wd,
            start_time: start, end_time: end, room
          });

          if(existing){
            ops.push(fetch(API_BASE+`/schedule/${existing.id}/`, {method:'PUT', headers:HEADERS, body:payload}));
          }else{
            ops.push(fetch(API_BASE+`/schedule/`, {method:'POST', headers:HEADERS, body:payload}));
          }
        }else if(existing){
          ops.push(fetch(API_BASE+`/schedule/${existing.id}/`, {method:'DELETE', headers:HEADERS}));
        }
      }
    });

    try{
      const resps = await Promise.all(ops);
      const bad = resps.find(r => !(r.ok || r.status===204));
      if(bad){
        const t = await bad.text().catch(()=> ''); throw new Error(t || `HTTP ${bad.status}`);
      }
      ok('Jadval saqlandi ✅');
      await loadScheduleForClass(); // refresh IDs
    }catch(e){
      console.error(e); err('Saqlashda xatolik ❌\n'+e.message);
    }
  }

  // ===== Events
  btnBuild.addEventListener('click', buildGrid);
  btnLoad.addEventListener('click', loadScheduleForClass);
  btnSaveAll.addEventListener('click', saveAll);
  btnPrint?.addEventListener('click', ()=> window.print());

  // ===== Init
  (async function init(){
    try{
      const okGuard = await loadLookups(); if(!okGuard) return;
      // choose first class by default
      SELECTED_CLASS = CLASSES[0] || null;
      renderClassList();
      setCurrentClassBadge();
      buildGrid();
      if(SELECTED_CLASS) await loadScheduleForClass();
    }catch(e){ console.error(e); err('Yuklashda xatolik: '+e.message); }
  })();
})();
