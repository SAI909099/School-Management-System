// static/js/class-manager.js
(function(){
  const API = (window.API_BASE || '/api').replace(/\/+$/,'');
  const access = localStorage.getItem('access');
  if (!access) { window.location.replace('/'); return; }

  const HEADERS = { 'Authorization':'Bearer '+access, 'Accept':'application/json' };
  const JSON_HEADERS = { ...HEADERS, 'Content-Type':'application/json' };

  // DOM
  const classSel = document.getElementById('classSel');
  const classNameInp = document.getElementById('classNameInp');
  const btnRename = document.getElementById('btnRename');
  const classMeta = document.getElementById('classMeta');

  const tblBody = document.querySelector('#tbl tbody');
  const countBox = document.getElementById('countBox');
  const qGlobal = document.getElementById('q');
  const qStudents = document.getElementById('studentSearch');

  // State
  let CLASSES = [];         // [{id,name}, ...]
  let STUDENTS = [];        // students of selected class
  let ALL_CLASSES_MAP = new Map(); // id -> name

  // Helpers
  const pad = n => String(n).padStart(2,'0');
  function fullName(s){
    const fn = (s.first_name||'').trim();
    const ln = (s.last_name||'').trim();
    return (ln+' '+fn).trim() || (s.full_name || ('#'+s.id));
  }
  async function getJSON(url){
    const r = await fetch(url, {headers: HEADERS});
    if (!r.ok) throw new Error(`HTTP ${r.status}`);
    return r.json();
  }
  async function patchJSON(url, body){
    const r = await fetch(url, {method:'PATCH', headers: JSON_HEADERS, body: JSON.stringify(body||{})});
    const txt = await r.text(); let data = {};
    try{ data = txt?JSON.parse(txt):{} }catch{}
    if (!r.ok) throw new Error(data.detail || txt || `HTTP ${r.status}`);
    return data;
  }
  async function putJSON(url, body){
    const r = await fetch(url, {method:'PUT', headers: JSON_HEADERS, body: JSON.stringify(body||{})});
    const txt = await r.text(); let data = {};
    try{ data = txt?JSON.parse(txt):{} }catch{}
    if (!r.ok) throw new Error(data.detail || txt || `HTTP ${r.status}`);
    return data;
  }

  // Load classes (for picker and for move targets)
  async function loadClasses(){
    // Prefer lightweight directory
    let rows = [];
    try {
      rows = await getJSON(`${API}/dir/classes/`);
    } catch {
      // Fallback to full classes
      rows = await getJSON(`${API}/classes/`);
    }
    CLASSES = (rows || []).map(c => ({ id: c.id, name: c.name || c.title || (`Sinf #${c.id}`) }));
    ALL_CLASSES_MAP = new Map(CLASSES.map(c => [Number(c.id), c.name]));
    classSel.innerHTML = '';
    CLASSES.forEach(c => classSel.add(new Option(c.name, c.id)));
  }

  // Load students of a class (prefer @action, fallback to filter)
  async function loadStudentsOf(classId){
    let rows = [];
    // Try custom action: /classes/{id}/students_az/
    try{
      rows = await getJSON(`${API}/classes/${classId}/students_az/`);
    }catch(_e){
      // Fallback: /students/?clazz=ID
      try {
        rows = await getJSON(`${API}/students/?clazz=${classId}`);
      } catch {
        rows = [];
      }
    }
    // Normalize a bit
    STUDENTS = (rows || []).map(s => ({
      id: s.id,
      first_name: s.first_name || '',
      last_name: s.last_name || '',
      full_name: s.full_name || '',
      clazz: s.clazz || s.class_id || classId
    }));
  }

  function renderTable(){
    const q1 = (qGlobal.value||'').toLowerCase().trim();
    const q2 = (qStudents.value||'').toLowerCase().trim();
    const q = (q2 || q1);

    const filtered = (STUDENTS || []).filter(s => {
      const hay = [s.first_name, s.last_name, s.full_name].join(' ').toLowerCase();
      return !q || hay.includes(q);
    });

    tblBody.innerHTML = '';
    filtered.forEach((s, i) => {
      const tr = document.createElement('tr');
      const fromId = Number(classSel.value);
      const optionsHtml = CLASSES
        .map(c => `<option value="${c.id}" ${Number(c.id)===fromId?'disabled':''}>${c.name}</option>`)
        .join('');

      tr.innerHTML = `
        <td>${i+1}</td>
        <td>${fullName(s)}</td>
        <td><span class="pill">${ALL_CLASSES_MAP.get(fromId) || '-'}</span></td>
        <td>
          <div class="row" style="gap:6px;margin:0">
            <select data-move-target="${s.id}">${optionsHtml}</select>
            <button class="btn primary" data-move="${s.id}">Ko‘chirish</button>
          </div>
        </td>
        <td>
          <button class="btn danger" data-leave="${s.id}">Sinfdan chiqarish</button>
        </td>
      `;
      tblBody.appendChild(tr);
    });

    countBox.textContent = String(filtered.length);

    // Bind buttons
    tblBody.querySelectorAll('button[data-move]').forEach(btn=>{
      btn.addEventListener('click', ()=> onMoveClick(btn));
    });
    tblBody.querySelectorAll('button[data-leave]').forEach(btn=>{
      btn.addEventListener('click', ()=> onLeaveClick(btn));
    });
  }

  async function onMoveClick(btn){
    const sid = Number(btn.getAttribute('data-move'));
    const select = tblBody.querySelector(`select[data-move-target="${sid}"]`);
    const targetId = Number(select?.value || 0);
    const fromId = Number(classSel.value);

    if (!targetId || targetId === fromId){
      alert('Iltimos, boshqa sinfni tanlang.');
      return;
    }

    if (!confirm('O‘quvchini boshqa sinfga ko‘chirmoqchimisiz?')) return;

    btn.disabled = true;
    const old = btn.textContent;
    btn.textContent = 'Ko‘chirilmoqda...';

    try{
      // Preferred: PATCH student with clazz=targetId
      try{
        await patchJSON(`${API}/students/${sid}/`, { clazz: targetId });
      }catch{
        // Fallback: PUT if PATCH not allowed
        await putJSON(`${API}/students/${sid}/`, { clazz: targetId });
      }
      await loadStudentsOf(fromId); // reload current list (student will disappear)
      renderTable();
      alert('Ko‘chirildi ✅');
    }catch(e){
      console.error(e);
      alert('Ko‘chirishda xatolik ❌');
    }finally{
      btn.disabled = false; btn.textContent = old;
    }
  }

  async function onLeaveClick(btn){
    const sid = Number(btn.getAttribute('data-leave'));
    const fromId = Number(classSel.value);
    if (!confirm('O‘quvchini sinfdan chiqarishni tasdiqlaysizmi?')) return;

    btn.disabled = true;
    const old = btn.textContent;
    btn.textContent = 'Chiqarilmoqda...';

    try{
      // Try to clear clazz and (optionally) mark inactive
      try{
        await patchJSON(`${API}/students/${sid}/`, { clazz: null, status: 'inactive' });
      }catch{
        // If status choice not accepted, try only clearing class
        await patchJSON(`${API}/students/${sid}/`, { clazz: null });
      }
      await loadStudentsOf(fromId);
      renderTable();
      alert('Sinfdan chiqarildi ✅');
    }catch(e){
      console.error(e);
      alert('Amalda xatolik ❌');
    }finally{
      btn.disabled = false; btn.textContent = old;
    }
  }

  // Rename class
  async function renameClass(){
    const id = Number(classSel.value);
    const newName = (classNameInp.value || '').trim();
    if (!id || !newName){ alert('Sinf va yangi nomni tanlang.'); return; }

    btnRename.disabled = true;
    const old = btnRename.textContent;
    btnRename.textContent = 'Saqlanmoqda...';
    try{
      // PATCH preferred, PUT fallback
      try{
        await patchJSON(`${API}/classes/${id}/`, { name: newName });
      }catch{
        await putJSON(`${API}/classes/${id}/`, { id, name: newName });
      }
      // refresh classes list so UI shows latest name
      await loadClasses();
      classSel.value = String(id);
      classNameInp.value = '';
      classMeta.textContent = `Nom yangilandi: ${ALL_CLASSES_MAP.get(id)}`;
      // reload students just to be safe
      await loadStudentsOf(id);
      renderTable();
      alert('Nom yangilandi ✅');
    }catch(e){
      console.error(e);
      alert('Nomni o‘zgartirishda xatolik ❌');
    }finally{
      btnRename.disabled = false;
      btnRename.textContent = old;
    }
  }

  // Events
  btnRename.addEventListener('click', renameClass);
  classSel.addEventListener('change', async ()=>{
    const id = Number(classSel.value);
    classMeta.textContent = '';
    await loadStudentsOf(id);
    renderTable();
  });
  qGlobal.addEventListener('input', renderTable);
  qStudents.addEventListener('input', renderTable);

  // Init
  (async function init(){
    try{
      await loadClasses();
      if (CLASSES.length){
        classSel.value = String(CLASSES[0].id);
        await loadStudentsOf(CLASSES[0].id);
      }
      renderTable();
    }catch(e){
      console.error(e);
      alert('Ma’lumotlarni yuklashda xatolik.');
    }
  })();
})();
