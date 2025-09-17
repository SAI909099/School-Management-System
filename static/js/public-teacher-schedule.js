(function(){
  const API_BASE = (window.API_BASE || '/api/').replace(/\/+$/, '');
  const WEEKDAYS = {1:'Dushanba',2:'Seshanba',3:'Chorshanba',4:'Payshanba',5:'Juma',6:'Shanba'};

  function getTeacherIdFromPath(){
    const parts = window.location.pathname.split('/').filter(Boolean);
    const idx = parts.indexOf('teacher');
    if(idx>=0 && parts[idx+1] && parts[idx+1]!=='me') return Number(parts[idx+1]);
    return 0; // 0 → will fall back to /auth/me + /schedule/teacher/me
  }

  const title = document.getElementById('title');
  const table = document.getElementById('scheduleTable');
  const btnPrint = document.getElementById('btnPrint');
  const msg = document.getElementById('msg');
  function err(t){ msg.className='err'; msg.textContent=t; msg.classList.remove('hidden'); }
  function hideMsg(){ msg.classList.add('hidden'); }

  async function api(path, auth=false){
    const headers = auth ? buildHeaders() : {};
    const res = await fetch(API_BASE + (path.startsWith('/')?path:'/'+path), {headers});
    if(!res.ok) throw new Error(await res.text().catch(()=>`HTTP ${res.status}`));
    return res.json();
  }
  function buildHeaders(){
    const access = localStorage.getItem('access');
    return access ? { 'Authorization': 'Bearer '+access } : {};
  }

  function renderGrid(entries){
    // group by weekday
    const byWd = {1:[],2:[],3:[],4:[],5:[],6:[]};
    entries.forEach(x=> { if(byWd[x.weekday]) byWd[x.weekday].push(x); });
    Object.values(byWd).forEach(arr=> arr.sort((a,b)=> String(a.start_time).localeCompare(String(b.start_time)) ));

    // max rows
    const maxRows = Math.max(...Object.values(byWd).map(a=>a.length), 0);

    table.innerHTML = '';
    const thead = document.createElement('thead');
    thead.innerHTML = `
      <tr>
        <th>№ / Vaqt</th>
        <th>${WEEKDAYS[1]}</th>
        <th>${WEEKDAYS[2]}</th>
        <th>${WEEKDAYS[3]}</th>
        <th>${WEEKDAYS[4]}</th>
        <th>${WEEKDAYS[5]}</th>
        <th>${WEEKDAYS[6]}</th>
      </tr>`;
    table.appendChild(thead);

    const tbody = document.createElement('tbody');
    for(let r=0; r<maxRows; r++){
      const tr = document.createElement('tr');

      // time column
      let timeLabel = '';
      for(let d=1; d<=6; d++){
        const e = byWd[d][r];
        if(e){ timeLabel = `${(e.start_time||'').slice(0,5)}–${(e.end_time||'').slice(0,5)}`; break; }
      }
      const tdTime = document.createElement('td');
      tdTime.textContent = `${r+1}. ${timeLabel || ''}`;
      tr.appendChild(tdTime);

      for(let d=1; d<=6; d++){
        const td = document.createElement('td');
        const e  = byWd[d][r];
        if(e){
          td.innerHTML = `
            <div class="entry">
              <div class="subj">${e.subject_name || 'Fan'}</div>
              <div class="class">Sinf: ${e.class_name || ''}</div>
              <div class="room">Xona: ${e.room || '—'}</div>
              <div class="time">${(e.start_time||'').slice(0,5)}–${(e.end_time||'').slice(0,5)}</div>
            </div>`;
        } else {
          td.innerHTML = `<div class="entry"><div class="subj" style="color:#9ca3af;">—</div></div>`;
        }
        tr.appendChild(td);
      }
      tbody.appendChild(tr);
    }
    table.appendChild(tbody);
  }

  async function init(){
    hideMsg();
    try{
      let teacherId = getTeacherIdFromPath();
      let teacherName = '';
      let entries = [];

      if(teacherId){
        // public/admin view for specific teacher id
        const [teacher, data] = await Promise.all([
          api(`/teachers/${teacherId}/`, true),                     // needs auth (admin/registrar)
          api(`/schedule/teacher/${teacherId}/`)                    // open read-only ok
        ]);
        teacherName = teacher.user_full_name || '—';
        entries = data;
      } else {
        // teacher's own view (no id in URL)
        const me = await api('/auth/me/', true);
        teacherName = (me?.last_name ? (me.last_name + ' ') : '') + (me?.first_name || '');
        entries = await api('/schedule/teacher/me/', true);
      }

      title.textContent = `O‘qituvchi: ${teacherName || '—'}`;
      renderGrid(entries);
      btnPrint.addEventListener('click', ()=> window.print());
    }catch(e){
      console.error(e); err('Yuklashda xatolik: '+e.message);
    }
  }
  init();
})();
