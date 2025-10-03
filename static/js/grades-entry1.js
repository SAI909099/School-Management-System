/* SAFE TEACHER ENTRY — exam/final by default; daily can be enabled via data-allow-daily="true"
   and locked via data-lock-daily="true" (teacher daily page). */
(function () {
  // --------- read flags & API from DOM ---------
  const root = document.querySelector('.container[data-page="grades-entry"]');
  const ALLOW_DAILY = !!(root && root.dataset.allowDaily === 'true');
  const LOCK_DAILY  = !!(root && root.dataset.lockDaily === 'true');
  const API = (document.body.dataset.apiBase || '/api').replace(/\/+$/, '');

  // --------- auth guard ---------
  const access = localStorage.getItem('access');
  if (!access) { window.location.replace('/'); return; }

  // --------- network helpers (JWT + refresh) ---------
  async function tryRefresh() {
    const refresh = localStorage.getItem('refresh');
    if (!refresh) return false;
    try {
      const r = await fetch(API + '/auth/refresh/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh })
      });
      if (!r.ok) return false;
      const d = await r.json().catch(() => ({}));
      if (!d.access) return false;
      localStorage.setItem('access', d.access);
      return true;
    } catch { return false; }
  }

  async function fetchWithAuth(path, opts = {}, retry = true) {
    const token = localStorage.getItem('access');
    const headers = Object.assign(
      { 'Authorization': 'Bearer ' + token },
      opts.headers || {}
    );
    const resp = await fetch(API + path, Object.assign({}, opts, { headers }));
    if (resp.status === 401 && retry) {
      const ok = await tryRefresh();
      if (ok) return fetchWithAuth(path, opts, false);
    }
    return resp;
  }

  async function getJSON(path, signal) {
    const r = await fetchWithAuth(path, { signal });
    const t = await r.text();
    let json = null; try { json = t ? JSON.parse(t) : {}; } catch {}
    if (!r.ok) throw new Error((json && (json.detail || json.error)) || t || `HTTP ${r.status}`);
    return json;
  }

  async function postJSON(path, data) {
    const r = await fetchWithAuth(path, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data || {})
    });
    const t = await r.text();
    let json = null; try { json = t ? JSON.parse(t) : {}; } catch {}
    if (!r.ok) throw new Error((json && (json.detail || json.error)) || t || `HTTP ${r.status}`);
    return json || {};
  }

  // --------- tiny DOM helpers ---------
  const $ = (s, r = document) => r.querySelector(s);
  const el = (t, a = {}, ...kids) => {
    const e = document.createElement(t);
    for (const [k, v] of Object.entries(a)) {
      if (k === 'class') e.className = v;
      else if (v != null) e.setAttribute(k, v);
    }
    kids.forEach(k => e.append(k instanceof Node ? k : document.createTextNode(k)));
    return e;
  };
  function todayISO() {
    const d = new Date();
    const m = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    return `${d.getFullYear()}-${m}-${dd}`;
  }
  function msg(ok, text) {
    const box = $('#msg');
    if (!box) return;
    box.classList.remove('hidden');
    box.className = ok ? 'ok' : 'err';
    box.textContent = text;
    clearTimeout(msg._t);
    msg._t = setTimeout(() => { box.classList.add('hidden'); }, ok ? 2500 : 5000);
  }
  function setLoading(show) {
    const l = $('#loading');
    if (!l) return;
    l.classList.toggle('hidden', !show);
  }

  // --------- DOM refs ---------
  const classSel   = $('#classSel');
  const subjectSel = $('#subjectSel');
  const typeSel    = $('#typeSel');
  const dateInp    = $('#dateInp');
  const termInp    = $('#termInp');
  const tbl        = $('#tbl tbody');
  const btnLoad    = $('#btnLoad');
  const btnFill3   = $('#btnFill3');
  const btnFill4   = $('#btnFill4');
  const btnFill5   = $('#btnFill5');
  const btnClear   = $('#btnClear');
  const btnSave    = $('#btnSave');
  const whoBadge   = $('#whoBadge');

  // Optional day navigation (daily page)
  const btnPrevDay = $('#btnPrevDay');
  const btnNextDay = $('#btnNextDay');

  // --------- state ---------
  let students = [];  // [{id, first_name, last_name}]
  let role = '—';
  let saving = false;
  let dirty = false;
  let prefillAborter = null;

  // --------- boot defaults ---------
  if (dateInp) dateInp.value = todayISO();
  if (termInp && !termInp.value) {
    const d = new Date();
    const half = (d.getMonth() + 1) <= 6 ? 1 : 2;
    termInp.value = `${d.getFullYear()}-${half}`;
  }

  // Prevent accidental navigation if there are unsaved edits
  window.addEventListener('beforeunload', (e) => {
    if (dirty && !saving) {
      e.preventDefault();
      e.returnValue = '';
    }
  });

  // --------- load helpers ---------
  async function loadRole() {
    try {
      const me = await getJSON('/auth/me/');
      role = me.role || me.user?.role || '—';
    } catch { role = '—'; }
    if (whoBadge) whoBadge.textContent = `Rol: ${role}`;
  }

  async function loadClasses() {
    setLoading(true);
    try {
      const data = await getJSON('/dir/classes/');
      if (classSel) {
        classSel.innerHTML = '';
        (data || []).forEach(c => classSel.append(el('option', { value: c.id }, c.name)));
      }
    } finally { setLoading(false); }
  }

  async function loadTeacherDefaultClass() {
    try {
      const mine = await getJSON('/teacher/classes/me/');
      if (Array.isArray(mine) && mine.length && classSel) {
        const firstId = String(mine[0].id);
        if (![...classSel.options].some(o => o.value === firstId)) {
          classSel.append(el('option', { value: firstId }, mine[0].name || `Sinf #${firstId}`));
        }
        classSel.value = firstId;
      }
    } catch {}
  }

  async function loadSubjects() {
    setLoading(true);
    try {
      const data = await getJSON('/subjects/');
      if (subjectSel) {
        subjectSel.innerHTML = '';
        subjectSel.append(el('option', { value: '' }, '— tanlang —'));
        (data || []).forEach(s => subjectSel.append(el('option', { value: s.id }, `${s.name} (${s.code})`)));
      }
    } finally { setLoading(false); }
  }

  async function loadStudentsByClass(classId) {
    const data = await getJSON(`/classes/${classId}/students_az/`);
    students = (data || []).map(s => ({ id: s.id, first_name: s.first_name, last_name: s.last_name }));
  }

  // --------- render / inputs ---------
  function ensureTypeOptions() {
    if (!typeSel) return;
    const want = LOCK_DAILY
      ? ['daily']
      : ['exam', 'final'].concat(ALLOW_DAILY ? ['daily'] : []);
    // Remove extras
    [...typeSel.options].forEach(o => { if (!want.includes(o.value)) o.remove(); });
    // Add missing in order
    const have = new Set([...typeSel.options].map(o => o.value));
    if (!LOCK_DAILY) {
      if (!have.has('exam'))  typeSel.append(el('option', { value: 'exam' }, 'Imtihon'));
      if (!have.has('final')) typeSel.append(el('option', { value: 'final' }, 'Yakuniy'));
      if (ALLOW_DAILY && !have.has('daily')) typeSel.append(el('option', { value: 'daily' }, 'Kundalik'));
    } else {
      // force daily only
      typeSel.innerHTML = '';
      typeSel.append(el('option', { value: 'daily' }, 'Kundalik'));
      typeSel.value = 'daily';
      typeSel.disabled = true;
    }
    if (!want.includes(typeSel.value)) typeSel.value = want[0];
  }

  function renderTable(prefillMap = new Map()) {
    if (!tbl) return;
    tbl.innerHTML = '';
    if (!students.length) {
      tbl.append(el('tr', {}, el('td', { colspan: 4 }, 'O‘quvchilar topilmadi.')));
      return;
    }
    students.forEach((s, idx) => {
      const key = String(s.id);
      const pre = prefillMap.get(key) || {};
      const row = el('tr', { 'data-student': s.id },
        el('td', {}, String(idx + 1)),
        el('td', {}, `${s.last_name || ''} ${s.first_name || ''}`.trim()),
        el('td', {},
          el('input', {
            type: 'number', min: '2', max: '5', step: '1',
            class: 'score-inp', style: 'width:80px', inputmode: 'numeric', pattern: '[2-5]',
            value: pre.score != null ? String(pre.score) : ''
          })
        ),
        el('td', {},
          el('input', {
            type: 'text', class: 'comment-inp', placeholder: 'Izoh (ixtiyoriy)',
            value: pre.comment ? pre.comment : ''
          })
        )
      );
      tbl.append(row);
    });

    // validators & dirty tracking
    tbl.querySelectorAll('.score-inp').forEach(inp => {
      inp.addEventListener('input', () => {
        dirty = true;
        let v = inp.value.replace(/[^\d]/g, '');
        if (v.length > 1) v = v[0];
        const n = Number(v);
        if (Number.isFinite(n)) {
          if (n < 2) v = '2';
          if (n > 5) v = '5';
        }
        inp.value = v;
        if (!v) { inp.classList.remove('bad'); return; }
        const ok = Number(v) >= 2 && Number(v) <= 5;
        inp.classList.toggle('bad', !ok);
      });
    });
    tbl.querySelectorAll('.comment-inp').forEach(inp => {
      inp.addEventListener('input', () => { dirty = true; });
    });
  }

  function fillAll(val) {
    if (!tbl) return;
    tbl.querySelectorAll('.score-inp').forEach(inp => { inp.value = String(val); });
    dirty = true;
  }
  function clearAll() {
    if (!tbl) return;
    tbl.querySelectorAll('.score-inp').forEach(inp => inp.value = '');
    tbl.querySelectorAll('.comment-inp').forEach(inp => inp.value = '');
    dirty = true;
  }

  // --------- prefill existing (by-class API) ---------
  async function prefillExisting() {
    if (!classSel || !subjectSel || !typeSel || !dateInp) return new Map();
    const classId = classSel.value;
    const subjectId = subjectSel.value;
    const gtype = LOCK_DAILY ? 'daily' : typeSel.value;
    const dt = dateInp.value;
    if (!classId || !subjectId || !dt) return new Map();

    const allowed = LOCK_DAILY
      ? ['daily']
      : ['exam', 'final'].concat(ALLOW_DAILY ? ['daily'] : []);
    if (!allowed.includes(gtype)) return new Map();

    if (prefillAborter) prefillAborter.abort();
    prefillAborter = new AbortController();

    try {
      const list = await getJSON(
        `/grades/by-class/?class=${encodeURIComponent(classId)}&subject=${encodeURIComponent(subjectId)}&type=${encodeURIComponent(gtype)}&date=${encodeURIComponent(dt)}`,
        prefillAborter.signal
      );
      const map = new Map();
      (list || []).forEach(it => {
        map.set(String(it.student_id), { score: it.score, comment: it.comment || '' });
      });
      return map;
    } catch (e) {
      if (e.name !== 'AbortError') console.warn('Prefill failed:', e.message);
      return new Map();
    }
  }

  // --------- save ----------
  async function saveGrades() {
    if (saving) return;
    if (!classSel || !subjectSel || !typeSel || !dateInp) return;

    const classId = classSel.value;
    const subjectId = subjectSel.value;
    let gtype = LOCK_DAILY ? 'daily' : typeSel.value;
    const dt = dateInp.value;
    const term = (termInp ? termInp.value.trim() : '');

    if (!classId) { msg(false, 'Sinf tanlanmadi'); return; }
    if (!subjectId) { msg(false, 'Fan tanlanmadi'); return; }
    if (!dt) { msg(false, 'Sana tanlanmadi'); return; }

    const allowedTypes = LOCK_DAILY
      ? ['daily']
      : ['exam', 'final'].concat(ALLOW_DAILY ? ['daily'] : []);
    if (!allowedTypes.includes(gtype)) {
      msg(false, LOCK_DAILY
        ? 'Bu sahifada faqat Kundalik turiga ruxsat berilgan.'
        : (ALLOW_DAILY ? 'Baho turi noto‘g‘ri.' : 'Kundalik baholar kiritilmaydi. Faqat Imtihon yoki Yakuniy.'));
      if (LOCK_DAILY) gtype = 'daily';
      else if (!ALLOW_DAILY) gtype = 'exam';
    }

    const entries = [];
    let bad = 0;
    if (tbl) {
      tbl.querySelectorAll('tr').forEach(tr => {
        const sid = tr.getAttribute('data-student');
        const scoreStr = tr.querySelector('.score-inp')?.value;
        const comment = (tr.querySelector('.comment-inp')?.value || '').trim();
        if (!sid || !scoreStr) return;
        const n = Number(scoreStr);
        if (!Number.isFinite(n) || n < 2 || n > 5) { bad++; return; }
        entries.push({ student: Number(sid), score: n, comment });
      });
    }

    if (bad > 0) { msg(false, 'Noto‘g‘ri baholar bor (faqat 2..5).'); return; }
    if (!entries.length) { msg(false, 'Hech bo‘lmaganda bitta bahoni kiriting.'); return; }
    if (entries.length > 300) { msg(false, 'Bir vaqtda 300 tadan oshiq yozuv yuborilmaydi.'); return; }

    const payload = {
      "class": Number(classId),
      "date": dt,
      "subject": Number(subjectId),
      "type": gtype,            // exam | final | daily
      "term": term,
      "entries": entries
    };

    try {
      saving = true;
      if (btnSave) { btnSave.disabled = true; btnSave.textContent = 'Saqlanmoqda...'; }
      const res = await postJSON('/grades/bulk-set/', payload);
      const savedCount = (res && Array.isArray(res.ids)) ? res.ids.length : entries.length;
      dirty = false;
      msg(true, `Saqlanib bo‘ldi. ${savedCount} ta yozuv.`);
    } catch (e) {
      msg(false, 'Xatolik: ' + e.message);
    } finally {
      saving = false;
      if (btnSave) { btnSave.disabled = false; btnSave.textContent = 'Saqlash'; }
    }
  }

  // --------- events ----------
  if (btnFill3) btnFill3.addEventListener('click', () => fillAll(3));
  if (btnFill4) btnFill4.addEventListener('click', () => fillAll(4));
  if (btnFill5) btnFill5.addEventListener('click', () => fillAll(5));
  if (btnClear) btnClear.addEventListener('click', clearAll);
  if (btnSave)  btnSave.addEventListener('click', saveGrades);

  if (btnPrevDay) btnPrevDay.addEventListener('click', async () => {
    if (!dateInp) return;
    const d = new Date(dateInp.value || todayISO());
    d.setDate(d.getDate() - 1);
    dateInp.value = d.toISOString().slice(0,10);
    if (classSel?.value) {
      try {
        setLoading(true);
        await loadStudentsByClass(classSel.value);
        const pre = await prefillExisting();
        renderTable(pre);
      } finally { setLoading(false); }
    }
  });
  if (btnNextDay) btnNextDay.addEventListener('click', async () => {
    if (!dateInp) return;
    const d = new Date(dateInp.value || todayISO());
    d.setDate(d.getDate() + 1);
    dateInp.value = d.toISOString().slice(0,10);
    if (classSel?.value) {
      try {
        setLoading(true);
        await loadStudentsByClass(classSel.value);
        const pre = await prefillExisting();
        renderTable(pre);
      } finally { setLoading(false); }
    }
  });

  if (btnLoad) btnLoad.addEventListener('click', async () => {
    if (!classSel) return;
    const classId = classSel.value;
    if (!classId) { msg(false, 'Avval sinfni tanlang.'); return; }
    try {
      setLoading(true);
      await loadStudentsByClass(classId);
      const pre = await prefillExisting();
      renderTable(pre);
      msg(true, 'O‘quvchilar yuklandi.');
    } catch (e) {
      msg(false, 'Yuklashda xatolik: ' + e.message);
    } finally {
      setLoading(false);
    }
  });

  [classSel, subjectSel, typeSel, dateInp].forEach(inp => {
    if (!inp) return;
    inp.addEventListener('change', async () => {
      if (!tbl || !tbl.children.length) return; // only if rendered
      try {
        if (!classSel.value) return;
        setLoading(true);
        await loadStudentsByClass(classSel.value);
        const pre = await prefillExisting();
        renderTable(pre);
      } catch (e) {
        console.warn('Auto-prefill failed:', e.message);
      } finally {
        setLoading(false);
      }
    });
  });

  // --------- init ----------
  (async function init() {
    try {
      ensureTypeOptions(); // adds/removes options; locks if data-lock-daily
      setLoading(true);
      await Promise.all([loadRole(), loadClasses(), loadSubjects()]);
      await loadTeacherDefaultClass();
      // Optional: auto-load immediately when both selected
      // if (classSel && classSel.value && subjectSel && subjectSel.value) btnLoad.click();
    } catch (e) {
      console.error(e);
      msg(false, 'Boshlang‘ich yuklashda xatolik: ' + e.message);
    } finally {
      setLoading(false);
    }
  })();
})();
