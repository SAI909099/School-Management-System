/* Student payments page (Uzbek labels, show class, no discount/penalty) */
(function () {
  const API = (window.API_BASE || '/api/billing').replace(/\/+$/, '');
  const token = localStorage.getItem('access');
  if (!token) { window.location.replace('/'); return; }

  const HEADERS = { 'Authorization': 'Bearer ' + token };
  const JSON_HEADERS = { ...HEADERS, 'Content-Type': 'application/json' };

  // DOM
  const monthInp = document.getElementById('monthInp');
  const classSel = document.getElementById('classSel');
  const statusSel = document.getElementById('statusSel');
  const btnLoad = document.getElementById('btnLoad');
  const btnGenerate = document.getElementById('btnGenerate');
  const tblBody = document.querySelector('#tbl tbody');
  const qSearch = document.getElementById('qSearch');

  // Bulk plans UI
  const planAmountAll = document.getElementById('planAmountAll');
  const btnPlanApplyAll = document.getElementById('btnPlanApplyAll');
  const planMultiSel = document.getElementById('planMultiSel');
  const btnPlanApplySelected = document.getElementById('btnPlanApplySelected');

  // Payment modal
  const payDlg = document.getElementById('payDlg');
  const dlgWho = document.getElementById('dlgWho');
  const payAmount = document.getElementById('payAmount');
  const payMethod = document.getElementById('payMethod');
  const payNote = document.getElementById('payNote');
  const btnPaySave = document.getElementById('btnPaySave');
  const btnPayCancel = document.getElementById('btnPayCancel');

  // State
  let classes = [];                       // [{id,name}]
  let classNameById = new Map();          // id -> name
  let plansByClass = new Map();           // class_id -> {id, amount_uzs}
  let currentPay = null;                  // {invoice_id, student_id, name}

  // Helpers
  function todayMonth() {
    const d = new Date();
    return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`;
  }
  function som(n){ return (Number(n||0)).toLocaleString('uz-UZ') + " so'm"; }
  function yymm(dateStr){ return (dateStr||'').slice(0,7); }

  // Translate status → Uzbek label
  function statusUz(status, balance) {
    if (status === 'paid' && Number(balance) < 0) return 'Oldindan';
    switch (status) {
      case 'paid': return 'To‘langan';
      case 'partial': return 'Qisman';
      case 'unpaid': return 'To‘lanmagan';
      default: return String(status || '').toUpperCase();
    }
  }
  function badge(status, balance){
    const uz = statusUz(status, balance);
    // keep css class names for colors
    if (uz === 'Oldindan') return `<span class="pill prepaid">${uz}</span>`;
    return `<span class="pill ${status}">${uz}</span>`;
  }

  async function getJSON(url){
    const r = await fetch(url, { headers: HEADERS });
    if (!r.ok) throw new Error(`${r.status} ${r.statusText}`);
    return r.json();
  }
  async function postJSON(url, body){
    const r = await fetch(url, { method:'POST', headers: JSON_HEADERS, body: JSON.stringify(body) });
    const text = await r.text();
    let json = {};
    try { json = text ? JSON.parse(text) : {}; } catch {}
    if (!r.ok) throw new Error(json.detail || text || `HTTP ${r.status}`);
    return json;
  }
  async function putJSON(url, body){
    const r = await fetch(url, { method:'PUT', headers: JSON_HEADERS, body: JSON.stringify(body) });
    const text = await r.text();
    const json = text ? JSON.parse(text) : {};
    if (!r.ok) throw new Error(json.detail || text || `HTTP ${r.status}`);
    return json;
  }

  // Load classes (directory API)
  async function loadClasses(){
    const data = await getJSON('/api/dir/classes/');
    classes = data || [];
    classNameById.clear();
    classes.forEach(c => classNameById.set(Number(c.id), c.name));

    // Filters
    classSel.innerHTML = '<option value="">— hammasi —</option>';
    classes.forEach(c => classSel.add(new Option(c.name, c.id)));
    // Bulk multi-select
    planMultiSel.innerHTML = '';
    classes.forEach(c => planMultiSel.add(new Option(c.name, c.id)));
  }

  // Load existing tuition plans
  async function loadPlans(){
    const data = await getJSON(API + '/plans/');
    plansByClass.clear();
    (data||[]).forEach(p => plansByClass.set(String(p.clazz), p));
  }

  // Try bulk-apply endpoint; fallback to looping per class
  async function applyPlans(amount, classIds) {
    try {
      const body = classIds && classIds.length
        ? { amount_uzs: Number(amount), class_ids: classIds.map(Number) }
        : { amount_uzs: Number(amount), scope: 'all' };
      const res = await postJSON(API + '/plans/bulk-apply/', body);
      return res;
    } catch (e) {
      const targets = (classIds && classIds.length)
        ? classIds.map(String)
        : classes.map(c => String(c.id));
      let created = 0, updated = 0, failed = 0;

      for (const cid of targets) {
        try {
          const existing = plansByClass.get(cid);
          const payload = { clazz: Number(cid), amount_uzs: Number(amount) };
          if (existing) {
            await putJSON(API + `/plans/${existing.id}/`, { id: existing.id, ...payload });
            updated++;
          } else {
            await postJSON(API + '/plans/', payload);
            created++;
          }
        } catch {
          failed++;
        }
      }
      return { ok: failed === 0, created, updated, failed };
    }
  }

  // Cache for student info: id -> {name, classId}
  const studentCache = new Map();
  async function getStudentInfo(studentId){
    if (studentCache.has(studentId)) return studentCache.get(studentId);
    try{
      // Directory search; pick exact id
      const sj = await getJSON(`/api/dir/students/?q=${studentId}`);
      const m = (sj||[]).find(x=>x.id===studentId);
      const name = m ? ((m.full_name || `${m.first_name||''} ${m.last_name||''}`).trim()) : `#${studentId}`;
      const classId = m?.clazz ?? m?.class ?? m?.clazz_id ?? null;
      const info = { name, classId };
      studentCache.set(studentId, info);
      return info;
    }catch{
      const info = { name: `#${studentId}`, classId: null };
      studentCache.set(studentId, info);
      return info;
    }
  }

  // Fetch invoices with filters; handle prepaid on client
  async function loadInvoices(){
    const params = new URLSearchParams();
    const m = monthInp.value;
    if (m) params.set('month', m);
    const c = classSel.value;
    if (c) params.set('class', c);
    const st = statusSel.value;
    if (st && st !== '__prepaid') params.set('status', st);

    const url = API + '/invoices/' + (params.toString() ? ('?' + params.toString()) : '');
    const data = await getJSON(url);
    let rows = Array.isArray(data) ? data : [];

    // “prepaid” filter (balance < 0)
    if (statusSel.value === '__prepaid') {
      rows = rows.filter(r => Number(r.balance_uzs) < 0);
    }

    const q = (qSearch.value||'').toLowerCase().trim();

    tblBody.innerHTML = '';
    for (const r of rows) {
      const info = await getStudentInfo(r.student);
      const sname = info.name;
      const clsName = info.classId ? (classNameById.get(Number(info.classId)) || '') : '';

      // search by name or class text
      if (q && !(sname.toLowerCase().includes(q) || clsName.toLowerCase().includes(q))) continue;

      const tr = document.createElement('tr');
      tr.innerHTML = `
        <td>${sname}</td>
        <td>${clsName}</td>
        <td>${yymm(r.month)}</td>
        <td>${som(r.amount_uzs)}</td>
        <td>${som(r.paid_uzs)}</td>
        <td>${som(r.balance_uzs)}</td>
        <td>${badge(r.status, r.balance_uzs)}</td>
        <td><button class="btn primary btn-pay" data-inv="${r.id}" data-st="${r.student}" data-month="${r.month}">To‘lov</button></td>
      `;
      tblBody.appendChild(tr);
    }

    // Wire payment buttons
    tblBody.querySelectorAll('.btn-pay').forEach(btn=>{
      btn.addEventListener('click', ()=>{
        const inv = Number(btn.dataset.inv);
        const st  = Number(btn.dataset.st);
        const when = btn.dataset.month.slice(0,7);
        const display = btn.closest('tr')?.firstChild?.textContent || `#${st}`;
        currentPay = { invoice_id: inv, student_id: st, month: when, display };
        dlgWho.textContent = `${display} — ${when}`;
        payAmount.value = '';
        payMethod.value = 'cash';
        payNote.value = '';
        payDlg.showModal();
      });
    });
  }

  // Generate invoices for month from plans
  btnGenerate.addEventListener('click', async ()=>{
    const m = monthInp.value || todayMonth();
    const cid = classSel.value;
    const due = 10;
    const def = 0; // fallback price for classes without a plan
    const qs = new URLSearchParams({ month: m, due_day: String(due) });
    if (cid) qs.set('class', cid);
    if (def) qs.set('default_amount', String(def));
    try {
      const res = await postJSON(API + '/invoices/generate/?' + qs.toString(), {});
      alert(`Yaratildi: ${res.created}, yangilandi: ${res.updated}`);
      await loadInvoices();
    } catch (e) {
      alert('Xatolik: ' + e.message);
    }
  });

  // Save payment
  btnPaySave.addEventListener('click', async ()=>{
    if (!currentPay) return;
    const amt = Number(payAmount.value||0);
    if (!amt || amt<=0) return alert('Miqdorni kiriting');
    const body = {
      student: currentPay.student_id,
      invoice: currentPay.invoice_id,
      amount_uzs: amt,
      method: payMethod.value,
      note: payNote.value||'',
    };
    try{
      await postJSON(API + '/payments-model/', body);
      payDlg.close();
      await loadInvoices();
    }catch(e){ alert('Xatolik: '+e.message); }
  });
  btnPayCancel.addEventListener('click', ()=> payDlg.close());

  // Bulk plan: ALL
  btnPlanApplyAll.addEventListener('click', async ()=>{
    const amt = Number(planAmountAll.value||0);
    if (!amt) return alert('Narxni kiriting.');
    try{
      await applyPlans(amt, null);
      await loadPlans();
      alert('Barcha sinflar uchun saqlandi.');
    }catch(e){
      alert('Xatolik: ' + e.message);
    }
  });

  // Bulk plan: SELECTED
  btnPlanApplySelected.addEventListener('click', async ()=>{
    const amt = Number(planAmountAll.value || 0);
    if (!amt) return alert('Narxni kiriting.');
    const selected = Array.from(planMultiSel.selectedOptions).map(o => Number(o.value));
    if (!selected.length) return alert('Kamida bitta sinfni tanlang.');
    try{
      await applyPlans(amt, selected);
      await loadPlans();
      alert('Tanlangan sinflar uchun saqlandi.');
    }catch(e){
      alert('Xatolik: ' + e.message);
    }
  });

  // Filters / actions
  btnLoad.addEventListener('click', loadInvoices);
  monthInp.addEventListener('change', loadInvoices);
  classSel.addEventListener('change', loadInvoices);
  statusSel.addEventListener('change', loadInvoices);
  qSearch.addEventListener('input', ()=> loadInvoices());

  // Init
  (async function init(){
    monthInp.value = todayMonth();
    await loadClasses();
    await loadPlans();
    await loadInvoices();
  })();
})();
