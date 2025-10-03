/**
 * moliya-main.js (Option B — expense computed from rows)
 * Endpoints used:
 *  - GET /api/billing/summary/?from=YYYY-MM-DD&to=YYYY-MM-DD
 *  - GET /api/billing/payments/?type=income&from=...&to=...
 *  - GET /api/billing/payments/?type=expense&from=...&to=...&include_salaries=1
 */
(function () {
  const API = (window.API_BASE || "/api/billing").replace(/\/+$/, "");
  const token = localStorage.getItem("access");
  if (!token) { window.location.replace("/"); return; }

  const HEADERS = { Authorization: "Bearer " + token, Accept: "application/json" };

  // DOM
  const fromDate = document.getElementById("fromDate");
  const toDate   = document.getElementById("toDate");
  const btnLoad  = document.getElementById("btnLoad");
  const btnThisMonth = document.getElementById("btnThisMonth");
  const rangeInfo = document.getElementById("rangeInfo");

  const incomeTotal = document.getElementById("incomeTotal");
  const incomeCash  = document.getElementById("incomeCash");
  const incomeCard  = document.getElementById("incomeCard");
  const incomeTransfer = document.getElementById("incomeTransfer");

  const expenseTotal = document.getElementById("expenseTotal");
  const expenseCash  = document.getElementById("expenseCash");
  const expenseCard  = document.getElementById("expenseCard");
  const expenseTransfer = document.getElementById("expenseTransfer");

  const profit = document.getElementById("profit");
  const balance = document.getElementById("balance");
  const debtorsCount = document.getElementById("debtorsCount");
  const periodLabel = document.getElementById("periodLabel");

  // charts
  let lineChart, pieIncome, pieExpense;

  // helpers
  const pad = (n) => String(n).padStart(2, "0");
  function thisMonthRange() {
    const d = new Date();
    const y = d.getFullYear(), m = d.getMonth() + 1;
    const first = `${y}-${pad(m)}-01`;
    const last = `${y}-${pad(m)}-${pad(new Date(y, m, 0).getDate())}`;
    return { first, last };
  }
  function som(n) { return (Number(n || 0)).toLocaleString("uz-UZ") + " so'm"; }
  async function getJSON(url) {
    const r = await fetch(url, { headers: HEADERS });
    if (r.status === 401) {
      localStorage.removeItem("access");
      alert("Sessiya tugagan. Iltimos, qayta tizimga kiring.");
      window.location.replace("/");
      throw new Error("401");
    }
    if (!r.ok) throw new Error("HTTP " + r.status);
    return r.json();
  }
  function dateList(from, to) {
    if (!from || !to) return [];
    const out = [];
    const a = new Date(from + "T00:00:00");
    const b = new Date(to + "T00:00:00");
    for (let d = new Date(a); d <= b; d.setDate(d.getDate() + 1)) {
      out.push(d.toISOString().slice(0, 10));
    }
    return out;
  }
  function amt(x) { return Number(x?.amount_uzs ?? x?.amount ?? 0); }
  function methodKey(m) {
    const k = (m || "").toLowerCase();
    if (k === "cash" || k === "naqd") return "cash";
    if (k === "card" || k === "karta") return "card";
    if (k === "transfer" || k === "o‘tkazma" || k === "otkazma") return "transfer";
    if (k === "salary") return "salary";
    return "cash";
  }

  function destroyCharts() {
    [lineChart, pieIncome, pieExpense].forEach(ch => { if (ch) ch?.destroy?.(); });
    lineChart = pieIncome = pieExpense = null;
  }

  function renderCharts(labels, incomeDaily, expenseDaily, incMethods, expMethods) {
    const lc = document.getElementById("lineChart");
    const pi = document.getElementById("pieIncome");
    const pe = document.getElementById("pieExpense");

    // Line: income vs expense per day
    lineChart = new Chart(lc.getContext("2d"), {
      type: "line",
      data: {
        labels,
        datasets: [
          { label: "Kirim",  data: incomeDaily, tension: 0.25, borderWidth: 2, fill: false },
          { label: "Chiqim", data: expenseDaily, tension: 0.25, borderWidth: 2, fill: false }
        ]
      },
      options: {
        responsive: true,
        interaction: { mode: "index", intersect: false },
        scales: { y: { ticks: { callback: v => v.toLocaleString("uz-UZ") } } },
        plugins: { legend: { position: "top" } }
      }
    });

    // Pie: income methods (3 slices)
    pieIncome = new Chart(pi.getContext("2d"), {
      type: "doughnut",
      data: {
        labels: ["Naqd", "Karta", "O‘tkazma"],
        datasets: [{ data: [incMethods.cash, incMethods.card, incMethods.transfer] }]
      },
      options: { plugins: { legend: { position: "bottom" } } }
    });

    // Pie: expense methods (4 slices — include salary so KPI matches)
    pieExpense = new Chart(pe.getContext("2d"), {
      type: "doughnut",
      data: {
        labels: ["Naqd", "Karta", "O‘tkazma", "Oylik"],
        datasets: [{ data: [
          expMethods.cash, expMethods.card, expMethods.transfer, expMethods.salary
        ] }]
      },
      options: { plugins: { legend: { position: "bottom" } } }
    });
  }

  function setDashes() {
    [incomeTotal, incomeCash, incomeCard, incomeTransfer,
     expenseTotal, expenseCash, expenseCard, expenseTransfer,
     profit, balance].forEach(el => el.textContent = "—");
    debtorsCount.textContent = "—";
    periodLabel.textContent = "—";
    rangeInfo.textContent = "";
    destroyCharts();
  }

  async function load() {
    const from = fromDate.value, to = toDate.value;
    const qs = new URLSearchParams();
    if (from) qs.set("from", from);
    if (to)   qs.set("to",   to);

    try {
      // 1) Summary (useful for quick income totals & debtors)
      const summary = await getJSON(`${API}/summary/${qs.toString() ? "?" + qs.toString() : ""}`);
      const income = Number(summary.income || 0);

      // Fill INCOME KPI from summary
      const ib = summary.income_by_method || {};
      incomeTotal.textContent = som(income);
      incomeCash.textContent = som(ib.cash || 0);
      incomeCard.textContent = som(ib.card || 0);
      incomeTransfer.textContent = som(ib.transfer || 0);

      const f = summary.from || from || "";
      const t = summary.to   || to   || "";
      periodLabel.textContent = (f && t) ? `${f} — ${t}` : "—";
      rangeInfo.textContent = (f && t) ? `Davr: ${f} — ${t}` : "";
      debtorsCount.textContent = String(summary.debtors_count ?? "—");

      // 2) Rows for charts and EXPENSE KPI (match Chiqim page exactly)
      const rowsQs = new URLSearchParams();
      if (from) rowsQs.set("from", from);
      if (to)   rowsQs.set("to",   to);

      const [incRows, expRows] = await Promise.all([
        getJSON(`${API}/payments/?type=income&${rowsQs.toString()}`),
        getJSON(`${API}/payments/?type=expense&include_salaries=1&${rowsQs.toString()}`)
      ]);

      const labels = dateList(f || from, t || to);
      const incMap = Object.create(null);
      const expMap = Object.create(null);
      labels.forEach(d => { incMap[d] = 0; expMap[d] = 0; });

      // Daily sums
      (Array.isArray(incRows) ? incRows : []).forEach(r => {
        const d = (r.date || r.paid_at || "").slice(0,10);
        if (d in incMap) incMap[d] += amt(r);
      });
      (Array.isArray(expRows) ? expRows : []).forEach(r => {
        const d = (r.date || r.paid_at || "").slice(0,10);
        if (d in expMap) expMap[d] += amt(r);
      });

      const incomeDaily = labels.map(d => incMap[d] || 0);
      const expenseDaily = labels.map(d => expMap[d] || 0);

      // Method breakdowns from rows
      const incMethods = { cash:0, card:0, transfer:0 };
      (Array.isArray(incRows) ? incRows : []).forEach(r => {
        const k = methodKey(r.method);
        if (k in incMethods) incMethods[k] += amt(r);
      });

      const expMethods = { cash:0, card:0, transfer:0, salary:0 };
      let expenseTotalCalc = 0;
      (Array.isArray(expRows) ? expRows : []).forEach(r => {
        const a = amt(r);
        expenseTotalCalc += a;
        const k = methodKey(r.method);
        if (k in expMethods) expMethods[k] += a;
      });

      // Overwrite EXPENSE KPI from rows (so it matches Chiqim)
      expenseTotal.textContent    = som(expenseTotalCalc);
      expenseCash.textContent     = som(expMethods.cash || 0);
      expenseCard.textContent     = som(expMethods.card || 0);
      expenseTransfer.textContent = som(expMethods.transfer || 0);

      // Profit/balance using computed expense
      const profCalc = income - expenseTotalCalc;
      profit.textContent  = som(profCalc);
      balance.textContent = som(profCalc);

      destroyCharts();
      if (labels.length) {
        renderCharts(labels, incomeDaily, expenseDaily, incMethods, expMethods);
      }

    } catch (e) {
      console.error("Summary load failed:", e);
      setDashes();
    }
  }

  document.addEventListener("DOMContentLoaded", () => {
    const { first, last } = thisMonthRange();
    fromDate.value = first; toDate.value = last;
    btnLoad.addEventListener("click", load);
    btnThisMonth.addEventListener("click", () => {
      const r = thisMonthRange();
      fromDate.value = r.first; toDate.value = r.last;
      load();
    });
    load();
  });
})();
