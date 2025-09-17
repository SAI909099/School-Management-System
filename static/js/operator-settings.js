/**
 * operator-settings.js
 * Profil sozlamalari
 */
(function(){
  const API = (window.API_BASE || '/api').replace(/\/+$/,'');
  const token = localStorage.getItem('access');
  const HEADERS = token ? { Authorization: 'Bearer ' + token } : {};

  const form = document.getElementById('operator-settings-form');

  async function patchFormData(url, fd){
    const res = await fetch(url, { method:'PATCH', headers: HEADERS, body: fd });
    if(!res.ok) throw new Error(await res.text());
    return await res.json();
  }

  if(form){
    form.addEventListener('submit', async e=>{
      e.preventDefault();
      const fd = new FormData(form);
      try {
        await patchFormData(API + '/auth/me/', fd);
        alert('Sozlamalar saqlandi');
      } catch(err){
        alert('Xatolik: ' + err);
      }
    });
  }
})();
