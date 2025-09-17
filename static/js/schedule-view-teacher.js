/* static/js/schedule-view-teacher.js */
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
  const subjectFilter = qs('#subjectFilter');
  const teacherSel    = qs('#teacherSel');
  const tbl           = qs('#tbl');
  const meta          = qs('#meta');
  const btnReload     = qs('#btnReload');
  const btnPrint      = qs('#btnPrint');
  let   btnCsv        = qs('#btnCsv'); // optional (we’ll create if missing)
  const msg           = qs('#msg');

  // ---- Messages
  const ok   = t => { msg.className = 'ok';  msg.textContent = t; msg.classList.remove('hidden'); };
  const err  = t => { msg.className = 'err'; msg.textContent = t; msg.classList.remove('hidden'); };
  const hide = () => msg.classList.add('hidden');

  // ---- Data caches
  let SUBJECTS = [], TEACHERS = [], SELECTED_T = null;

  function defaultTimes(n) {
    const starts = ['08:30','09:25','10:20','11:15','12:10','13:05','14:00','14:55','15:50','16:45','17:40','18:35'];
    const ends   = ['09:15','10:10','11:05','12:00','12:55','13:50','14:45','15:40','16:35','17:30','18:25','19:20'];
    return Array.from({ length: n }, (_, i) => ({ start: starts[i] || '', end: ends[i] || '' }));
  }

  async function init() {
    hide();

    // Load subjects
    SUBJECTS = await api('/subjects/');
    if (subjectFilter) {
      subjectFilter.innerHTML = '<option value="">(hammasi)</option>';
      SUBJECTS.forEach(s => subjectFilter.append(el('option', { value: String(s.id) }, s.name)));
    }

    // Load teachers (filtered by subject if selected)
    await loadTeachers();

    // deep-link support: ?teacher=<id>
    const url = new URL(window.location.href);
    const tParam = url.searchParams.get('teacher');
    if (tParam && TEACHERS.some(t => String(t.id) === String(tParam))) {
      teacherSel.value = String(tParam);
    }

    // Ensure CSV button exists; create if missing
    if (!btnCsv) {
      const controls = teacherSel?.closest('.card') || document.body;
      btnCsv = el('button', { id: 'btnCsv', class: 'btn', style: 'padding:10px 14px; margin-left:8px;' }, 'CSV chiqarish');
      // place after print if available
      (btnPrint && btnPrint.parentNode) ? btnPrint.parentNode.insertBefore(btnCsv, btnPrint.nextSibling)
                                        : controls.append(btnCsv);
    }

    attachEvents();
    await buildForSelected();
    ok('Jadval yuklandi ✅');
  }

  async function loadTeachers() {
    const all = await api('/teachers/');
    const subj = subjectFilter ? subjectFilter.value : '';
    TEACHERS = subj ? all.filter(t => String(t.specialty || '') === String(subj)) : all;

    teacherSel.innerHTML = '';
    TEACHERS
      .slice()
      .sort((a, b) => String(a.user_full_name || '').localeCompare(String(b.user_full_name || '')))
      .forEach(t => teacherSel.append(el('option', { value: t.id }, t.user_full_name || ('#' + t.user))));
  }

  function attachEvents() {
    subjectFilter?.addEventListener('change', async () => {
      await loadTeachers();
      await buildForSelected();
    });

    teacherSel?.addEventListener('change', buildForSelected);
    btnReload?.addEventListener('click', buildForSelected);
    btnPrint?.addEventListener('click', () => window.print());
    btnCsv?.addEventListener('click', downloadCsv);
  }

  async function buildForSelected() {
    hide();
    tbl.innerHTML = '';

    const tId = Number(teacherSel?.value || 0);
    if (!tId) { err('O‘qituvchi tanlanmagan'); return; }

    SELECTED_T = TEACHERS.find(t => t.id === tId) || null;

    // No dedicated teacher filter on API -> pull all and filter client-side
    const all = await api('/schedule/');
    const data = all.filter(x => x.teacher === tId);

    // Group by weekday, sort by start_time
    const byWd = { 1: [], 2: [], 3: [], 4: [], 5: [], 6: [] };
    data.forEach(x => { if (byWd[x.weekday]) byWd[x.weekday].push(x); });
    Object.values(byWd).forEach(a => a.sort((a, b) => String(a.start_time).localeCompare(String(b.start_time))));

    const maxRows = Math.max(...Object.values(byWd).map(a => a.length), 0);
    const rowCount = Math.max(1, maxRows || 8);
    const times = defaultTimes(rowCount);

    const thead = el('thead', {}, el('tr', {},
      el('th', {}, '№ / vaqt'),
      el('th', {}, 'Dushanba'),
      el('th', {}, 'Seshanba'),
      el('th', {}, 'Chorshanba'),
      el('th', {}, 'Payshanba'),
      el('th', {}, 'Juma'),
      el('th', {}, 'Shanba'),
    ));
    const tbody = el('tbody', {});

    for (let i = 0; i < rowCount; i++) {
      const tr = el('tr', {});
      const tm = times[i] || { start: '', end: '' };
      tr.append(el('td', {}, `#${i + 1} ${tm.start}–${tm.end}`));

      for (let wd = 1; wd <= 6; wd++) {
        const e = byWd[wd][i];
        if (e) {
          const subj = e.subject_name ? `Fan: ${e.subject_name}` : '';
          const cls  = e.class_name   ? `Sinf: ${e.class_name}`   : '';
          const room = e.room         ? `Xona: ${e.room}`         : '';
          tr.append(el('td', {}, el('div', { class: 'slot' },
            el('b', {}, `${(e.start_time || '').slice(0, 5)}–${(e.end_time || '').slice(0, 5)}`),
            '\n' + [subj, cls, room].filter(Boolean).join('\n')
          )));
        } else {
          tr.append(el('td', {}, ''));
        }
      }
      tbody.append(tr);
    }
    tbl.append(thead, tbody);

    const name = SELECTED_T?.user_full_name || '—';
    const spec = SELECTED_T?.specialty_name ? `, Fan: ${SELECTED_T.specialty_name}` : '';
    if (meta) meta.textContent = `O‘qituvchi: ${name}${spec}`;
  }

  // ---- CSV export
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
    const nameFromMeta = (meta?.textContent || 'jadval').replace(/[^A-Za-z0-9_ -]+/g, '').trim() || 'jadval';
    const csv = tableToCsv();
    const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${nameFromMeta}.csv`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
  }

  // ---- Start
  init().catch(e => err('Yuklashda xatolik: ' + e.message));
})();
