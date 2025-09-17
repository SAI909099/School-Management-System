(function(){
  const API_BASE = (window.API_BASE || '/api/').replace(/\/+$/, '');

  // Parse class_id from URL: /schedule/class/<id>/view/
  function getClassIdFromPath(){
    const parts = window.location.pathname.split('/').filter(Boolean);
    const idx = parts.indexOf('class');
    if(idx>=0 && parts[idx+1]) return Number(parts[idx+1]);
    // fallback: ?class_id=123
    const u = new URLSearchParams(location.search);
    return Number(u.get('class_id') || 0);
  }

  const WEEKDAYS = {1:'Dushanba',2:'Seshanba',3:'Chorshanba',4:'Payshanba',5:'Juma',6:'Shanba'};

  const title = document.getElementById('title');
  const meta  = document.getElementById('meta');
  const table = document.getElementById('scheduleTable');
  const btnPrint = document.getElementById('btnPrint');
  const btnOpenEditor = document.getElementById('btnOpenEditor');
  const msg = document.getElementById('msg');

  function err(t){ msg.className='err'; msg.textContent=t; msg.classList.remove('hidden'); }
  function hideMsg(){ msg.classList.add('hidden'); }

  async function api(path){
    const res = await fetch(API_BASE + (path.startsWith('/')?path:'/'+path));
    if(!res.ok) throw new Error(await res.text().catch(()=>`HTTP ${res.status}`));
    return res.json();
  }

  function renderGrid(entries){
    // group by weekday, then sort by start_time
    const byWd = {1:[],2:[],3:[],4:[],5:[],6:[]};
    entries.forEach(x=> { if(byWd[x.weekday]) byWd[x.weekday].push(x); });
    Object.values(byWd).forEach(arr=> arr.sort((a,b)=> String(a.start_time).localeCompare(String(b.start_time)) ));

    // collect the maximum lessons per day to define rows
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

      // time column: if any day has r-th lesson, show its time (first non-empty)
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
              <div class="teacher">${e.teacher_name || ''}</div>
              <div class="room">Xona: ${e.room || '—'}</div>
              <div class="time">${(e.start_time||'').slice(0,5)}–${(e.end_time||'').slice(0,5)}</div>
            </div>
          `;
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
    const classId = getClassIdFromPath();
    if(!classId){ err('Sinf ID topilmadi.'); return; }

    try{
      const [clazz, entries] = await Promise.all([
        api(`/classes/${classId}/`),
        api(`/schedule/class/${classId}/`)
      ]);
      title.textContent = `Sinf: ${clazz.name}`;
      meta.textContent  = `O‘quvchilar: ${clazz.student_count ?? '—'} • Sinf rahbari: ${clazz.class_teacher_name || '—'}`;
      renderGrid(entries);

      btnPrint.addEventListener('click', ()=> window.print());
      btnOpenEditor.addEventListener('click', ()=> window.location.href = '/schedule/classes/');
    }catch(e){
      console.error(e); err('Yuklashda xatolik: '+e.message);
    }
  }
  init();
})();
