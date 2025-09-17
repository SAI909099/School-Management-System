(function(){
  const API_BASE = (window.API_BASE || '/api/').replace(/\/+$/, '');
  const access = localStorage.getItem('access');
  if(!access){ window.location.href='/login/'; return; }
  const HEADERS = { 'Content-Type':'application/json', 'Authorization':'Bearer ' + access };

  const qs=(s,r=document)=>r.querySelector(s);
  const el=(t,a={},...k)=>{const e=document.createElement(t);for(const[n,v]of Object.entries(a)){if(n==='class')e.className=v;else if(v!=null)e.setAttribute(n,v);}k.forEach(x=>e.append(x instanceof Node?x:document.createTextNode(x)));return e;};
  const msg=qs('#msg'), ok=t=>{msg.className='ok';msg.textContent=t;msg.classList.remove('hidden');}, err=t=>{msg.className='err';msg.textContent=t;msg.classList.remove('hidden');}, hide=()=>msg.classList.add('hidden');

  const classSel=qs('#classSel'), subjectSel=qs('#subjectSel'), typeSel=qs('#typeSel');
  const dateInp=qs('#dateInp'), termInp=qs('#termInp'), whoBadge=qs('#whoBadge');
  const btnLoad=qs('#btnLoad'), btnSave=qs('#btnSave'), btnClear=qs('#btnClear');
  const btnFill3=qs('#btnFill3'), btnFill4=qs('#btnFill4'), btnFill5=qs('#btnFill5');
  const tbody=qs('#tbl tbody');

  let ROLE='user';
  let CLASSES=[], STUDENTS=[], SUBJECT_OPTIONS=[];

  function todayISO(){
    const d=new Date(); const m=String(d.getMonth()+1).padStart(2,'0'); const day=String(d.getDate()).padStart(2,'0');
    return `${d.getFullYear()}-${m}-${day}`;
  }
  async function api(path,opts={}){
    const url = path.startsWith('http')? path : API_BASE + (path.startsWith('/')? path : '/'+path);
    const res = await fetch(url, {headers:HEADERS, ...opts});
    if(!res.ok) throw new Error(await res.text().catch(()=>`HTTP ${res.status}`));
    return res.json();
  }

  async function init(){
    hide();
    dateInp.value = todayISO();

    const me = await api('/auth/me/');
    ROLE = me?.role || 'user';
    whoBadge.textContent = 'Rol: ' + ROLE;

    CLASSES = (ROLE==='teacher')
      ? await api('/teacher/classes/me/')
      : await api('/classes/');

    classSel.innerHTML='';
    CLASSES.sort((a,b)=> String(a.name).localeCompare(String(b.name)));
    CLASSES.forEach(c=> classSel.append(el('option',{value:c.id}, c.name)));

    // prefer teacher’s homeroom if any
    const myId = me?.teacher?.id;
    const preferred = CLASSES.find(c => c.class_teacher === myId) || CLASSES[0];
    if(preferred) classSel.value = preferred.id;

    await loadSubjectsForClass();
  }

  async function loadSubjectsForClass(){
    subjectSel.innerHTML='<option value="">— tanlang —</option>';
    const cid = Number(classSel.value || 0);
    if(!cid) return;

    // gather subjects that actually exist in the class schedule
    const schedule = await api(`/schedule/class/${cid}/`);
    const uniq = new Map();
    schedule.forEach(s => { if(s.subject) uniq.set(s.subject, s.subject_name || 'Fan'); });

    SUBJECT_OPTIONS = Array.from(uniq.entries()).map(([id,name])=>({id,name}));
    SUBJECT_OPTIONS.sort((a,b)=> a.name.localeCompare(b.name));
    SUBJECT_OPTIONS.forEach(s => subjectSel.append(el('option',{value:s.id}, s.name)));

    // clear table until user clicks "O‘quvchilarni yuklash"
    tbody.innerHTML='';
  }

  async function loadStudents(){
    hide();
    tbody.innerHTML='';
    const cid = Number(classSel.value || 0);
    if(!cid){ err('Sinf tanlanmagan'); return; }
    STUDENTS = await api(`/classes/${cid}/students_az/`);

    STUDENTS.forEach((s,idx)=>{
      const score = el('input',{type:'number', min:'2', max:'5', step:'1', 'data-student':s.id, style:'width:90px;'});
      const comment = el('input',{type:'text', placeholder:'Izoh (ixtiyoriy)', 'data-comment':s.id});
      const tr = el('tr',{},
        el('td',{}, String(idx+1)),
        el('td',{}, `${s.last_name||''} ${s.first_name||''}`.trim()),
        el('td',{}, score),
        el('td',{}, comment),
      );
      tbody.append(tr);
    });
    ok('O‘quvchilar yuklandi ✅');

    // Immediately try to prefill after list loads
    await prefillExisting();
  }

  async function prefillExisting(){
    const cid = Number(classSel.value||0);
    const sid = Number(subjectSel.value||0);
    const typ = typeSel.value;
    const dt  = (dateInp.value || '').trim();
    const term= (termInp.value || '').trim();

    if(!cid || !sid || !typ || !dt) return; // need these to fetch

    const params = new URLSearchParams({
      'class': String(cid),
      'subject': String(sid),
      'type': typ,
      'date': dt
    });
    if(term) params.set('term', term);

    try{
      const existing = await api(`/grades/by-class/?${params.toString()}`);
      // existing: [{student_id, score, comment}, ...]
      const map = new Map(existing.map(x => [x.student_id, x]));
      tbody.querySelectorAll('input[data-student]').forEach(inp=>{
        const sid = Number(inp.getAttribute('data-student'));
        const found = map.get(sid);
        if(found){
          inp.value = found.score ?? '';
          const cmt = qs(`input[data-comment="${sid}"]`);
          if(cmt) cmt.value = found.comment || '';
        }
      });
      if(existing.length) ok('Oldingi baholar topildi va yuklandi ✨');
    }catch(e){
      // don’t block the page if nothing found
      console.warn('prefill failed', e);
    }
  }

  async function save(){
    hide();
    const cid = Number(classSel.value||0);
    const subj = Number(subjectSel.value||0);
    const typ  = typeSel.value;
    const dt   = dateInp.value || todayISO();
    const term = (termInp.value||'').trim();

    if(!cid){ return err('Sinf tanlanmagan'); }
    if(!subj){ return err('Fan tanlanmagan'); }
    if(!['daily','exam','final'].includes(typ)){ return err('Baho turi noto‘g‘ri'); }

    const entries=[];
    tbody.querySelectorAll('input[data-student]').forEach(inp=>{
      const sid = Number(inp.getAttribute('data-student'));
      const val = inp.value ? Number(inp.value) : null;
      const cmt = (qs(`input[data-comment="${sid}"]`)?.value || '').trim();
      if(val!=null){
        entries.push({ student:sid, score:val, comment:cmt });
      }
    });

    if(!entries.length){ return err('Hech bo‘lmaganda bitta bahoni kiriting.'); }

    try{
      await api('/grades/bulk-set/', {
        method:'POST',
        body: JSON.stringify({
          "class": cid,
          "date": dt,
          "subject": subj,
          "type": typ,
          "term": term,
          "entries": entries
        })
      });
      ok('Baholar saqlandi ✅');
      // after save, re-pull so any missing rows (new students, edits) reflect
      await prefillExisting();
    }catch(e){
      console.error(e); err('Saqlashda xatolik ❌\n'+e.message);
    }
  }

  // helpers
  function fillAll(v){ tbody.querySelectorAll('input[data-student]').forEach(inp => { inp.value = v; }); }
  function clearAll(){ tbody.querySelectorAll('input[data-student], input[data-comment]').forEach(inp=> inp.value=''); }

  // events
  classSel.addEventListener('change', async ()=> { await loadSubjectsForClass(); tbody.innerHTML=''; });
  subjectSel.addEventListener('change', prefillExisting);
  typeSel.addEventListener('change', prefillExisting);
  dateInp.addEventListener('change', prefillExisting);
  termInp.addEventListener('change', prefillExisting);

  btnLoad.addEventListener('click', loadStudents);
  btnSave.addEventListener('click', save);
  btnClear.addEventListener('click', clearAll);
  btnFill3.addEventListener('click', ()=> fillAll(3));
  btnFill4.addEventListener('click', ()=> fillAll(4));
  btnFill5.addEventListener('click', ()=> fillAll(5));

  init().catch(e => err('Yuklashda xatolik: '+e.message));
})();
