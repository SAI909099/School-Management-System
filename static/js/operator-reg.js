/**
 * operator-reg.js
 * Dashboard statistikani yuklash
 */
(function(){
  const API = (window.API_BASE || '/api').replace(/\/+$/,'');
  const token = localStorage.getItem('access');
  const HEADERS = token ? { Authorization: 'Bearer ' + token } : {};

  async function loadStats(){
    try {
      const res = await fetch(API + '/academics/summary/', { headers: HEADERS });
      if(!res.ok) throw new Error('HTTP ' + res.status);
      const data = await res.json();
      if(data.new_today) document.getElementById('new-today').textContent = data.new_today;
      if(data.new_week) document.getElementById('new-week').textContent = data.new_week;
      if(data.active_total) document.getElementById('active-total').textContent = data.active_total;
      if(data.groups_total) document.getElementById('groups-total').textContent = data.groups_total;
    } catch(e){
      console.error('Dashboard stats error:', e);
    }
  }

  document.addEventListener('DOMContentLoaded', loadStats);
})();
