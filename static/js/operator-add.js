/**
 * operator-add.js
 * Yangi o‘quvchi qo‘shish
 */
(function(){
  const API = (window.API_BASE || '/api').replace(/\/+$/,'');
  const token = localStorage.getItem('access');
  const HEADERS = token ? { Authorization: 'Bearer ' + token, 'Content-Type':'application/json' } : { 'Content-Type':'application/json' };

  const form = document.querySelector('.student-form');

  async function postJSON(url, body){
    const res = await fetch(url, { method:'POST', headers: HEADERS, body: JSON.stringify(body) });
    if(!res.ok) throw new Error(await res.text());
    return await res.json();
  }

  if(form){
    form.addEventListener('submit', async e=>{
      e.preventDefault();
      const data = {
        first_name: form.ism.value,
        last_name: form.familiya.value,
        parent_name: form.otaona.value,
        birth_day: form.kun.value,
        birth_month: form.oy.value,
        birth_year: form.yil.value,
        clazz: form.sinf.value,
        kurator: form.kurator.value,
      };
      try {
        await postJSON(API + '/students/', data);
        alert('O‘quvchi qo‘shildi');
        form.reset();
      } catch(err){
        alert('Xatolik: ' + err);
      }
    });
  }
})();
