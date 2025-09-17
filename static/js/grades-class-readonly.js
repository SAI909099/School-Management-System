/* static/js/grades-class-readonly.js */
(function () {
  const API_BASE = (window.API_BASE || '/api/').replace(/\/+$/, '');
  const access = localStorage.getItem('access');
  if (!access) { window.location.href = '/login/'; return; }
  const HEADERS = { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + access };

  // ---- DOM helpers
  const qs = (s, r = document) => r.querySelector(s);
  const el = (t, a = {}, ...kids) => {
    const e = document.createElement(t);
    for (const [k, v] of Object.entries(a)) {
      if (k === 'class') e.className = v; else if (v != null) e.setAttribute(k, v);
    }
    kids.forEach(k => e.append(k instanceof Node ? k : document.createTextNode(k)));
    return e;
  };
  async function api(path) {
    const url = path.startsWith('http') ? path : API_BASE + (path.startsWith('/') ? path : '/' + path);
    const r = await fetch(url, { headers: HEADERS });
    if (!r.ok) throw new Error(await r.text().catch(() => `HTTP ${r.status}`));
    return r.json();
  }

  // ---- Elements
  const msg       = qs('#msg');
  const classSel  = qs('#classSel');
  const typeSel   = qs('#typeSel');
  const termInp   = qs('#termInp');
  const btnLoad   = qs('#btnLoad');
  const btnPrint  = qs('#btnPrint');
  const btnCsv    = qs('#btnCsv');
  const tbl       = qs('#gradesTbl');

  const ok  = t => { msg.className = 'ok'; msg.textContent = t; msg.classList.remove('hidden'); };
  const err = t => { msg.className = 'err'; msg.textContent = t; msg.classList.remove('hidden'); };
  const hide= () => msg.classList.add('hidden');

  // ---- Data caches
  let CLASSES = [], SUBJECTS = [], STUDENTS = [];
  let SUBJECT_INDEX = new Map();   // id -> subject
  let STUDENT_INDEX = new Map();   // id -> {id, first_name, last_name}

  async function init() {
    hide();

    // role guard (read-only for teacher/admin/registrar; parents typically use parent pages)
    try {
      const me = await api('/auth/me/');
      if (!['admin','registrar','teacher'].includes(me?.role)) {
        if (me?.role === 'parent') { window.location.href = '/otaona/'; return; }
      }
    } catch (_) { /* ignore */ }

    // load lookups
    [CLASSES, SUBJECTS] = await Promise.all([
      api('/classes/'),
      api('/subjects/')
    ]);
    SUBJECT_INDEX = new Map(SUBJECTS.map(s => [s.id, s]));

    // fill class select
    classSel.innerHTML = '';
    CLASSES
      .slice()
      .sort((a, b) => String(a.name).localeCompare(String(b.name)))
      .forEach(c => classSel.append(el('option', { value: c.id }, c.name)));

    // deep link ?class=<id>
    const url = new URL(window.location.href);
    const cid = url.searchParams.get('class');
    if (cid && CLASSES.some(c => String(c.id) === String(cid))) {
      classSel.value = String(cid);
    }

    // load first time
    await loadDataAndRender();

    // events
    btnLoad.addEventListener('click', loadDataAndRender);
    btnPrint.addEventListener('click', () => window.print());
    btnCsv.addEventListener('click', downloadCsv);
    classSel.addEventListener('change', loadDataAndRender);
    typeSel.addEventListener('change', loadDataAndRender);
  }

  async function loadDataAndRender() {
    hide();
    tbl.innerHTML = '';

    const classId = Number(classSel.value || 0);
    if (!classId) { err('Sinf tanlanmagan'); return; }

    // students list (ordered A→Z)
    STUDENTS = await api(`/classes/${classId}/students_az/`);
    STUDENT_INDEX = new Map(STUDENTS.map(s => [s.id, s]));

    // which type?
    const type = typeSel.value === 'final' ? 'final' : 'exam';
    const term = (termInp.value || '').trim();

    // data: { student_id: [{subject, date, score}, ...], ... }
    const endpoint = type === 'final' ? `/classes/${classId}/gradebook_final/`
                                      : `/classes/${classId}/gradebook_exams/`;
    const url = term ? `${endpoint}?term=${encodeURIComponent(term)}` : endpoint;
    const raw = await api(url);

    // Build a unified subject list that actually appears in data (to avoid many empty columns)
    const usedSubjectIds = new Set();
    Object.values(raw).forEach(arr => (arr || []).forEach(e => usedSubjectIds.add(e.subject)));
    const usedSubjects = SUBJECTS.filter(s => usedSubjectIds.has(s.id))
                                 .sort((a,b) => String(a.name).localeCompare(String(b.name)));

    // Header
    const thead = el('thead', {}, el('tr', {},
      el('th', { class: 'student-col' }, 'O‘quvchi'),
      ...usedSubjects.map(s => el('th', {}, s.name))
    ));

    // Body rows
    const tbody = el('tbody', {});
    STUDENTS.forEach(s => {
      const row = el('tr', {});
      const fio = `${s.last_name || ''} ${s.first_name || ''}`.trim();
      row.append(el('td', { class: 'student-col' }, fio || `#${s.id}`));

      const entries = (raw[String(s.id)] || []).slice();
      // per subject → list of {date, score}; show latest by date; tooltip with all
      const bySubject = new Map();
      entries.forEach(e => {
        const list = bySubject.get(e.subject) || [];
        list.push(e);
        bySubject.set(e.subject, list);
      });

      usedSubjects.forEach(sub => {
        const list = (bySubject.get(sub.id) || []).sort((a,b) => String(a.date).localeCompare(String(b.date)));
        if (!list.length) {
          row.append(el('td', {}, ''));
        } else {
          const last = list[list.length - 1];
          const all  = list.map(x => `${x.date}: ${x.score}`).join('\n');
          const cell = el('td', { title: all }, String(last.score));
          row.append(cell);
        }
      });

      tbody.append(row);
    });

    tbl.append(thead, tbody);
    ok('Baholar yuklandi ✅');
  }

  // ---- CSV Export
  function tableToCsv() {
    const rows = Array.from(tbl.querySelectorAll('tr'));
    return rows.map(tr => {
      const cols = Array.from(tr.children).map(td => {
        const t = td.innerText.replace(/\s*\n\s*/g, ' ').trim();
        return /[",;]/.test(t) ? `"${t.replace(/"/g, '""')}"` : t;
      });
      return cols.join(',');
    }).join('\n');
  }
  function downloadCsv() {
    const className = classSel.options[classSel.selectedIndex]?.text || 'sinf';
    const typeName  = typeSel.value === 'final' ? 'final' : 'exam';
    const termStr   = (termInp.value || '').trim();
    const filename  = ['grades', className, typeName, termStr].filter(Boolean).join('_').replace(/\s+/g,'-');

    const csv = tableToCsv();
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url  = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url; a.download = `${filename}.csv`;
    document.body.appendChild(a); a.click(); document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  init().catch(e => { console.error(e); err('Yuklashda xatolik: ' + e.message); });
})();
