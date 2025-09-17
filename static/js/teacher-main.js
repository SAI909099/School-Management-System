/* static/js/teacher-main.js */
(function () {
  // ===== Config =====
  // If you deploy behind a prefix (e.g. /school/api/), set this in the template:
  // <script>window.API_BASE = '/school/api/';</script>
  const API_BASE = (window.API_BASE || '/api/').replace(/\/+$/, '');

  // ===== Auth guard =====
  const access = localStorage.getItem('access');
  if (!access) {
    window.location.href = '/login/';
    return;
  }
  const HEADERS = {
    'Content-Type': 'application/json',
    'Authorization': 'Bearer ' + access
  };

  // ===== Helpers =====
  async function api(path, options = {}) {
    const url = path.startsWith('http') ? path : API_BASE + (path.startsWith('/') ? path : '/' + path);
    const res = await fetch(url, { headers: HEADERS, ...options });

    if (res.status === 401) {
      const refreshed = await tryRefresh();
      if (refreshed) {
        return api(path, options); // retry once
      }
      // refresh failed → go login
      localStorage.clear();
      window.location.href = '/login/';
      return;
    }

    if (!res.ok) {
      const txt = await res.text().catch(() => '');
      throw new Error(txt || `HTTP ${res.status}`);
    }
    return res.json();
  }

  async function tryRefresh() {
    const refresh = localStorage.getItem('refresh');
    if (!refresh) return false;
    const r = await fetch(API_BASE + '/auth/refresh/', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ refresh })
    });
    if (!r.ok) return false;
    const data = await r.json().catch(() => ({}));
    if (data && data.access) {
      localStorage.setItem('access', data.access);
      HEADERS.Authorization = 'Bearer ' + data.access;
      return true;
    }
    return false;
  }

  // Safely set text (ignores null/undefined/empty)
  function setText(el, value, fallback = '—') {
    if (!el) return;
    el.textContent = (value && String(value).trim()) || fallback;
  }

  // ===== Profile fillers (no HTML changes needed) =====
  function fillProfile(me) {
    // Your HTML:
    // <div class="profile-info">
    //   <h2>F.I.O: </h2>
    //   <p>Fan: Matematika</p>
    //   <p>Telefon: +998 90 123 45 67</p>
    //   <p>Email: teacher@mail.com</p>
    //   <p>Manzil: Qo'qon, Chorsu</p>
    // </div>
    const info = document.querySelector('.profile-info');
    if (!info) return;

    const name = [me?.last_name, me?.first_name].filter(Boolean).join(' ').trim() || (me?.phone || 'O‘qituvchi');
    const subjectName = me?.teacher?.subject_name || '—';
    const phone = me?.phone || '—';
    const email = me?.email || '—';
    const address = me?.address || '—'; // (only fills if you add it in backend later)

    // Expecting: <h2>, then 4 <p> (Fan, Telefon, Email, Manzil)
    const h2 = info.querySelector('h2');
    const ps = info.querySelectorAll('p');

    if (h2) setText(h2, `F.I.O: ${name}`);
    if (ps[0]) setText(ps[0], `Fan: ${subjectName}`);
    if (ps[1]) setText(ps[1], `Telefon: ${phone}`);
    if (ps[2]) setText(ps[2], `Email: ${email}`);
    if (ps[3]) setText(ps[3], `Manzil: ${address}`);
  }

  function enforceRole(me) {
    const role = me?.role;
    if (role === 'teacher') return; // stay here
    if (role === 'admin' || role === 'registrar') {
      window.location.href = '/dashboard/';
    } else if (role === 'parent') {
      window.location.href = '/otaona/';
    } else {
      window.location.href = '/';
    }
  }

  // Optional: load classes + schedule when you add containers later
  async function loadMyClasses() {
    try {
      const classes = await api('/teacher/classes/me/');
      // TODO: render into a container if/when you add it to HTML
      console.debug('Teacher classes:', classes);
    } catch (e) {
      console.warn('loadMyClasses failed:', e);
    }
  }

  async function loadTodaySchedule() {
    try {
      const sched = await api('/schedule/teacher/me/');
      // TODO: render into a container if/when you add it to HTML
      console.debug('Today schedule:', sched);
    } catch (e) {
      console.warn('loadTodaySchedule failed:', e);
    }
  }

  // ===== Boot =====
  (async function init() {
    try {
      const me = await api('/auth/me/');
      enforceRole(me);
      fillProfile(me);
      // Optional data
      loadMyClasses();
      loadTodaySchedule();
    } catch (e) {
      console.error('Init failed:', e);
      // fallback: go login if something is badly wrong
      // window.location.href = '/login/';
    }
  })();
})();
