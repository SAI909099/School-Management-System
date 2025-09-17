/* static/js/parent-child-today.js */
(function () {
  const API_BASE = (window.API_BASE || '/api/').replace(/\/+$/, '');
  const access = localStorage.getItem('access');
  if (!access) { return; }
  const HEADERS = { 'Content-Type': 'application/json', 'Authorization': 'Bearer ' + access };

  const host = document.getElementById('child-today-lessons');
  if (!host) return;

  // Resolve student id
  let studentId = host.getAttribute('data-student');
  if (!studentId) {
    const url = new URL(window.location.href);
    studentId = url.searchParams.get('student') || '';
  }
  if (!studentId) { host.textContent = 'O‘quvchi tanlanmagan.'; return; }

  const el = (t, a = {}, ...kids) => {
    const e = document.createElement(t);
    for (const [k, v] of Object.entries(a)) {
      if (k === 'class') e.className = v; else if (v != null) e.setAttribute(k, v);
    }
    kids.forEach(k => e.append(k instanceof Node ? k : document.createTextNode(k)));
    return e;
  };

  async function api(path) {
    const r = await fetch(API_BASE + path, { headers: HEADERS });
    if (!r.ok) throw new Error(await r.text().catch(() => `HTTP ${r.status}`));
    return r.json();
  }

  function weekdayIndex(d) { const x = d.getDay(); return x === 0 ? 7 : x; } // Sun->7
  const WEEKDAY_MAP = { 1: 'Dushanba', 2: 'Seshanba', 3: 'Chorshanba', 4: 'Payshanba', 5: 'Juma', 6: 'Shanba', 7: 'Yakshanba' };

  async function init() {
    host.innerHTML = 'Yuklanmoqda...';
    try {
      const data = await api(`/parent/child/${studentId}/overview/`);
      const today = weekdayIndex(new Date());
      const list = (data?.timetable || [])
        .filter(x => x.weekday === today)
        .sort((a, b) => String(a.start_time).localeCompare(String(b.start_time)));

      if (!list.length) {
        host.innerHTML = `<div class="empty">Bugun (${WEEKDAY_MAP[today]}) dars yo‘q.</div>`;
        return;
      }

      const wrap = el('div', { class: 'list' });
      list.forEach(e => {
        const st = (e.start_time || '').slice(0, 5);
        const et = (e.end_time || '').slice(0, 5);
        wrap.append(
          el('div', { class: 'row', style: 'display:flex;align-items:center;gap:10px;padding:8px 10px;border:1px solid #eee;border-radius:8px;background:#fff;margin-bottom:8px;' },
            el('div', { style: 'min-width:100px;font-weight:600;' }, `${st}–${et}`),
            el('div', { style: 'flex:1;' },
              el('div', {}, `Fan: ${e.subject_name || ''}`),
              el('div', {}, `O‘qituvchi: ${e.teacher_name || ''}${e.room ? ' · Xona: ' + e.room : ''}`)
            )
          )
        );
      });
      host.innerHTML = '';
      host.append(wrap);
    } catch (e) {
      console.error(e);
      host.innerHTML = '<div class="err">Yuklashda xatolik</div>';
    }
  }

  init();
})();
