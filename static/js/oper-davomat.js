/**
 * oper-davomat.js
 * Davomat jadvali
 */
(function(){
  const API = (window.API_BASE || '/api').replace(/\/+$/,'');
  const token = localStorage.getItem('access');
  const HEADERS = token ? { Authorization: 'Bearer ' + token, 'Content-Type':'application/json' } : { 'Content-Type':'application/json' };

  const sel = document.getElementById('class-select');
  const table = document.getElementById('attendance-table').querySelector('tbody');
  const btn = document.getElementById('attendance-save');

  async function getJSON(url){
    const res = await fetch(url, { headers: HEADERS });
    if(!res.ok) throw new Error(res.status);
    return await res.json();
  }
  async function postJSON(url, body){
    const res = await fetch(url, { method:'POST', headers: HEADERS, body: JSON.stringify(body) });
    if(!res.ok) throw new Error(res.status);
    return await res.json();
  }

  async function loadClasses(){
    try {
      const classes = await getJSON(API + '/classes/');
      sel.innerHTML = '<option value="">Sinf/Guruhni tanlang</option>';
      classes.forEach(c=>{
        const opt = document.createElement('option');
        opt.value = c.id;
        opt.textContent = c.name || 'Class #' + c.id;
        sel.appendChild(opt);
      });
    } catch(e){
      console.error('Classes error:', e);
    }
  }

  async function loadStudents(classId){
    table.innerHTML = '<tr><td colspan="3">Yuklanmoqda...</td></tr>';
    try {
      const students = await getJSON(API + `/classes/${classId}/students/`);
      table.innerHTML = '';
      students.forEach((s,i)=>{
        const tr = document.createElement('tr');
        tr.innerHTML = `
          <td>${i+1}</td>
          <td>${s.full_name || s.name}</td>
          <td><input type="checkbox" class="att-present" data-id="${s.id}"></td>
        `;
        table.appendChild(tr);
      });
    } catch(e){
      table.innerHTML = '<tr><td colspan="3">Xatolik</td></tr>';
    }
  }

  async function saveAttendance(){
    const classId = sel.value;
    if(!classId) return alert('Avval guruhni tanlang');
    const items = Array.from(document.querySelectorAll('.att-present'))
      .map(chk => ({ student: parseInt(chk.dataset.id,10), present: chk.checked }));
    const today = new Date().toISOString().slice(0,10);
    try {
      await postJSON(API + '/attendance/mark/', { class_id: parseInt(classId,10), date: today, items });
      alert('Davomat saqlandi');
    } catch(e){
      alert('Saqlashda xatolik');
    }
  }

  if(sel) sel.addEventListener('change', e => { if(e.target.value) loadStudents(e.target.value); });
  if(btn) btn.addEventListener('click', saveAttendance);

  document.addEventListener('DOMContentLoaded', loadClasses);
})();
