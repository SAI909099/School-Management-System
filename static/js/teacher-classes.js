/* static/js/teacher-classes.js */
(function () {
  // ===== Config =====
  const API_BASE = (window.API_BASE || '/api/').replace(/\/+$/, '');

  // ===== Auth guard =====
  const access = localStorage.getItem('access');
  if (!access) { window.location.href = '/login/'; return; }
  const HEADERS = { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + access };

  // ===== Utilities =====
  async function api(path, opts = {}) {
    const url = path.startsWith('http') ? path : API_BASE + (path.startsWith('/') ? path : '/' + path);
    const res = await fetch(url, { headers: HEADERS, ...opts });

    if (res.status === 401) {
      const ok = await tryRefresh();
      if (ok) return api(path, opts);
      localStorage.clear();
      window.location.href = '/login/';
      return;
    }
    if (!res.ok) throw new Error(await res.text().catch(()=>'') || `HTTP ${res.status}`);
    return res.json();
  }

  async function tryRefresh() {
    const refresh = localStorage.getItem('refresh');
    if (!refresh) return false;
    const r = await fetch(API_BASE + '/auth/refresh/', {
      method: 'POST', headers: {'Content-Type':'application/json'},
      body: JSON.stringify({ refresh })
    });
    if (!r.ok) return false;
    const data = await r.json().catch(()=>({}));
    if (data.access) { localStorage.setItem('access', data.access); HEADERS.Authorization = 'Bearer ' + data.access; return true; }
    return false;
  }

  function el(tag, attrs = {}, ...kids) {
    const e = document.createElement(tag);
    for (const [k,v] of Object.entries(attrs)) {
      if (k === 'class') e.className = v; else if (v != null) e.setAttribute(k,v);
    }
    for (const k of kids) e.append(k instanceof Node ? k : document.createTextNode(k));
    return e;
  }
  function todayISO() {
    const d = new Date(); const m = String(d.getMonth()+1).padStart(2,'0'); const day = String(d.getDate()).padStart(2,'0');
    return `${d.getFullYear()}-${m}-${day}`;
  }

  // ===== Role enforcement & store current teacher id =====
  let CURRENT_ME = null;
  let CURRENT_TEACHER_ID = null;

  async function loadMe() {
    const me = await api('/auth/me/');
    const role = me?.role;
    if (role === 'teacher') {
      CURRENT_ME = me;
      CURRENT_TEACHER_ID = me?.teacher?.id || null;
      return me;
    }
    if (role === 'admin' || role === 'registrar') window.location.href = '/dashboard/';
    else if (role === 'parent') window.location.href = '/otaona/';
    else window.location.href = '/';
    throw new Error('Wrong role for page');
  }

  // ===== DOM targets =====
  const cardsWrap = document.querySelector('.cards');
  const main = document.querySelector('main.content') || document.body;
  const searchInput = document.querySelector('.topbar input[type="text"]');

  // Attendance panel container
  const panel = el('section', { class: 'attendance-panel', style: 'margin-top:16px; display:none;' });
  main.appendChild(panel);

  // ===== Render: ALL classes (my class first) =====
  let ALL_CLASSES = [];

  function renderCards(list) {
    if (!cardsWrap) return;
    cardsWrap.innerHTML = '';
    if (!list || !list.length) {
      cardsWrap.append(el('div', {class:'card'}, 'Sinf topilmadi'));
      return;
    }

    list.forEach(c => {
      const isMyClass = (c.class_teacher === CURRENT_TEACHER_ID);
      const card = el('div', {class:'card', style:'cursor:pointer; position:relative;'});
      if (isMyClass) {
        card.appendChild(
          el('div', {
            class: 'badge-my-class',
            style: 'position:absolute; top:10px; right:10px; background:#4f46e5; color:#fff; padding:2px 8px; border-radius:999px; font-size:12px;'
          }, 'Mening sinfim')
        );
      }
      card.append(
        el('h3', {}, c.name || ('Sinf #' + c.id)),
        el('p', {}, `O‘quvchilar soni : ${c.student_count ?? '—'} ta`),
        el('p', {}, el('b', {}, 'Kurator : '), (c.class_teacher_name || '—'))
      );
      card.addEventListener('click', () => openAttendance(c));
      cardsWrap.append(card);
    });
  }

  async function loadClasses() {
    // fetch ALL classes
    ALL_CLASSES = await api('/classes/');

    // sort: my class first, then by name
    ALL_CLASSES.sort((a, b) => {
      const aMine = (a.class_teacher === CURRENT_TEACHER_ID) ? 1 : 0;
      const bMine = (b.class_teacher === CURRENT_TEACHER_ID) ? 1 : 0;
      if (aMine !== bMine) return bMine - aMine;
      return String(a.name || '').localeCompare(String(b.name || ''));
    });

    renderCards(ALL_CLASSES);
  }

  // Simple client-side search by class name
  if (searchInput) {
    searchInput.addEventListener('input', () => {
      const q = searchInput.value.trim().toLowerCase();
      const filtered = !q ? ALL_CLASSES :
        ALL_CLASSES.filter(c => String(c.name || '').toLowerCase().includes(q));
      renderCards(filtered);
    });
  }

  // ===== Attendance: open, load students & lessons =====
  async function openAttendance(clazz) {
    panel.style.display = '';
    panel.innerHTML = '';

    const header = el('div', {class:'panel-header'},
      el('h3', {}, `Davomat — ${clazz.name}`),
    );

    const controls = el('div', {class:'controls', style:'display:flex; gap:12px; align-items:center; flex-wrap:wrap;'});
    const dateInp = el('input', {type:'date', value: todayISO()});
    const lessonSel = el('select', {});
    const btnReload = el('button', {class:'btn'}, 'Yuklash');
    const btnAllPresent = el('button', {class:'btn'}, 'Barchasini “kelgan”');
    const btnSave = el('button', {class:'btn btn-primary'}, 'Saqlash');

    controls.append(
      el('label', {}, 'Sana: '), dateInp,
      el('label', {style:'margin-left:8px;'}, 'Dars: '), lessonSel,
      btnReload, btnAllPresent, btnSave
    );

    const tableWrap = el('div', {class:'table-wrap'});
    const table = el('table', {class:'att-table'});
    const thead = el('thead', {}, el('tr', {}, el('th', {}, '№'), el('th', {}, 'F.I.O'), el('th', {}, 'Holat'), el('th', {}, 'Izoh')));
    const tbody = el('tbody', {});
    table.append(thead, tbody);
    tableWrap.append(table);

    panel.append(header, controls, tableWrap);

    async function loadLessons() {
      lessonSel.innerHTML = '';
      const schedule = await api(`/schedule/class/${clazz.id}/`);
      schedule.forEach(item => {
        const st = (item.start_time || '').slice(0,5);
        const et = (item.end_time || '').slice(0,5);
        const name = (item.subject_name || 'Fan');
        const opt = el('option', { value: item.subject }, `${st || '--:--'}–${et || '--:--'} — ${name}`);
        lessonSel.append(opt);
      });
      if (!lessonSel.options.length) lessonSel.append(el('option', {value:''}, 'Dars topilmadi'));
    }

    async function loadStudents() {
      tbody.innerHTML = '';
      const students = await api(`/classes/${clazz.id}/students_az/`);
      students.forEach((s, idx) => {
        const tr = el('tr', {});
        const statusSel = el('select', { 'data-student': s.id },
          el('option', {value:'present', selected:true}, 'kelgan'),
          el('option', {value:'absent'}, 'kelmagan'),
          el('option', {value:'late'}, 'kechikkan'),
          el('option', {value:'excused'}, 'uzrli')
        );
        const noteInp = el('input', {type:'text', placeholder:'Izoh (ixtiyoriy)', 'data-note-for': s.id});
        tr.append(
          el('td', {}, String(idx+1)),
          el('td', {}, `${s.last_name || ''} ${s.first_name || ''}`.trim()),
          el('td', {}, statusSel),
          el('td', {}, noteInp),
        );
        tbody.append(tr);
      });
    }

    await loadLessons();
    await loadStudents();

    btnReload.addEventListener('click', async () => {
      await loadLessons();
      await loadStudents();
    });

    btnAllPresent.addEventListener('click', () => {
      tbody.querySelectorAll('select[data-student]').forEach(sel => { sel.value = 'present'; });
    });

    btnSave.addEventListener('click', async () => {
      const dateVal = dateInp.value || todayISO();
      const subjectId = lessonSel.value ? Number(lessonSel.value) : null;

      const entries = [];
      tbody.querySelectorAll('select[data-student]').forEach(sel => {
        const student = Number(sel.getAttribute('data-student'));
        const status = sel.value;
        const note = (panel.querySelector(`input[data-note-for="${student}"]`)?.value || '').trim();
        entries.push({ student, status, note });
      });

      try {
        const payload = { "class": clazz.id, "date": dateVal, "subject": subjectId, "entries": entries };
        await api('/attendance/bulk-mark/', { method:'POST', body: JSON.stringify(payload) });
        alert('Davomat saqlandi ✅');
      } catch (e) {
        console.error(e);
        alert('Saqlashda xatolik ❌');
      }
    });
  }

  // ===== Start =====
  (async function init() {
    await loadMe();
    await loadClasses();
  })();
})();
