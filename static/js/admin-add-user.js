/* admin-add-user.js */
(function(){
  const API_BASE = (window.API_BASE || '/api/').replace(/\/+$/, '');
  const access = localStorage.getItem('access');
  if (!access) { window.location.href = '/login/'; return; }
  const HEADERS = { 'Content-Type':'application/json', 'Authorization':'Bearer ' + access };

  const msg = document.getElementById('msg');
  const form = document.getElementById('addUserForm');
  const phoneEl = document.getElementById('phone');
  const passEl = document.getElementById('password');
  const lnEl = document.getElementById('last_name');
  const fnEl = document.getElementById('first_name');
  const roleEl = document.getElementById('role');

  const tBlock = document.getElementById('teacherBlock');
  const specEl = document.getElementById('specialty');
  const isClassEl = document.getElementById('is_class_teacher');
  const notesEl = document.getElementById('notes');

  const resetBtn = document.getElementById('resetBtn');

  // ----- helpers
  function ok(text){ msg.className='ok'; msg.textContent=text; msg.style.margin='12px 0'; msg.classList.remove('hidden'); }
  function err(text){ msg.className='err'; msg.textContent=text; msg.style.margin='12px 0'; msg.classList.remove('hidden'); }
  function hideMsg(){ msg.classList.add('hidden'); }
  function normalizePhone(s){
    if(!s) return s;
    s = String(s);
    s = s.replace(/[^\d+]/g,'');          // keep only + and digits
    if (!s.startsWith('+') && s.startsWith('998')) s = '+' + s;
    return s;
  }
  async function api(path, opts={}){
    const url = path.startsWith('http') ? path : API_BASE + (path.startsWith('/')?path:'/'+path);
    const res = await fetch(url, {headers:HEADERS, ...opts});
    if(res.status===401){
      // try refresh
      const ok = await tryRefresh();
      if(ok) return api(path, opts);
      localStorage.clear(); window.location.href='/login/'; return;
    }
    if(!res.ok){
      const t = await res.text().catch(()=> '');
      throw new Error(t || `HTTP ${res.status}`);
    }
    return res.json();
  }
  async function tryRefresh(){
    const refresh = localStorage.getItem('refresh');
    if(!refresh) return false;
    const r = await fetch(API_BASE + '/auth/refresh/', {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({refresh})});
    if(!r.ok) return false;
    const data = await r.json().catch(()=> ({}));
    if(data.access){ localStorage.setItem('access', data.access); HEADERS.Authorization = 'Bearer '+data.access; return true; }
    return false;
  }

  // ----- guard: only admin/registrar can open
  async function guard(){
    const me = await api('/auth/me/');
    if (!['admin','registrar'].includes(me?.role)) {
      if (me?.role === 'teacher') window.location.href = '/teachers/';
      else if (me?.role === 'parent') window.location.href = '/otaona/';
      else window.location.href = '/';
      throw new Error('Forbidden');
    }
  }

  // ----- load subjects for teacher specialty
  async function loadSubjects(){
    specEl.innerHTML = '<option value="">—</option>';
    try{
      const subs = await api('/subjects/');
      subs.forEach(s=>{
        const opt = document.createElement('option');
        opt.value = s.id; opt.textContent = `${s.name}`;
        specEl.appendChild(opt);
      });
    }catch(e){ /* leave empty */ }
  }

  // show/hide teacher block depending on role
  function toggleTeacherBlock(){
    const isTeacher = roleEl.value === 'teacher';
    tBlock.style.display = isTeacher ? '' : 'none';
  }

  // ----- submit
  form.addEventListener('submit', async (ev)=>{
    ev.preventDefault();
    hideMsg();

    const payload = {
      phone: normalizePhone(phoneEl.value),
      password: passEl.value,
      first_name: fnEl.value || '',
      last_name: lnEl.value || '',
      role: roleEl.value
    };

    if(!payload.phone || !payload.password){ err('Telefon va parol kiritilishi shart.'); return; }

    try{
      // 1) create User
      const user = await api('/auth/register/', {method:'POST', body: JSON.stringify(payload)});

      // 2) if role=teacher → create Teacher profile
      if (payload.role === 'teacher') {
        const teacherPayload = {
          user: user.id,
          specialty: specEl.value ? Number(specEl.value) : null,
          is_class_teacher: (isClassEl.value === 'true'),
          notes: (notesEl.value || '')
        };
        await api('/teachers/', {method:'POST', body: JSON.stringify(teacherPayload)});
      }

      ok('Foydalanuvchi muvaffaqiyatli yaratildi ✅');
      form.reset();
      toggleTeacherBlock();
    }catch(e){
      err('Xatolik:\n' + e.message);
    }
  });

  resetBtn.addEventListener('click', ()=> { hideMsg(); form.reset(); toggleTeacherBlock(); });

  roleEl.addEventListener('change', toggleTeacherBlock);

  // ----- boot
  (async function init(){
    await guard();
    await loadSubjects();
    toggleTeacherBlock();
  })();
})();

