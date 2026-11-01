// Dashboard helpers. One y-axis per chart (never dual-axis); thin lines; crosshair tooltip.
const PW = (() => {
  const css = (name) => getComputedStyle(document.body).getPropertyValue(name).trim();
  const SERIES = () => [1, 2, 3, 4, 5, 6, 7, 8].map((i) => css(`--series-${i}`));
  const base = (yTitle) => ({
    responsive: true,
    maintainAspectRatio: false,
    interaction: { mode: "index", intersect: false },
    plugins: {
      legend: { display: false },
      tooltip: {
        callbacks: { label: (c) => `${c.dataset.label}: ${Math.round(c.parsed.y).toLocaleString()} ${yTitle}` },
      },
    },
    elements: { line: { borderWidth: 2, tension: 0.2 }, point: { radius: 0, hitRadius: 10, hoverRadius: 4 } },
    scales: {
      x: { type: "time", grid: { display: false }, ticks: { color: css("--text-secondary"), maxTicksLimit: 6 } },
      y: { grid: { color: css("--grid") }, ticks: { color: css("--text-secondary"), callback: (v) => v.toLocaleString() } },
    },
  });

  async function marketCharts() {
    for (const el of document.querySelectorAll("canvas[data-kind]")) {
      const r = await fetch(`/api/market/${el.dataset.kind}?days=90`);
      const { points } = await r.json();
      if (points.length < 2) { el.parentElement.hidden = true; continue; } // nothing to draw yet, so don't hold the space
      new Chart(el, {
        type: "line",
        data: { datasets: [{ label: el.dataset.label, data: points.map(([d, v]) => ({ x: d, y: v })), borderColor: SERIES()[0], fill: false }] },
        options: { ...base(""), scales: { x: { display: false, type: "time" }, y: { display: false } }, plugins: { legend: { display: false }, tooltip: base("").plugins.tooltip } },
      });
    }
  }

  function sparklines() {
    document.querySelectorAll("canvas.spark").forEach((c) => {
      const pts = JSON.parse(c.dataset.points || "[]");
      const ctx = c.getContext("2d");
      if (pts.length < 2) return;
      const min = Math.min(...pts), max = Math.max(...pts), w = c.width, h = c.height;
      ctx.strokeStyle = SERIES()[0]; ctx.lineWidth = 1.5; ctx.beginPath();
      pts.forEach((p, i) => {
        const x = (i / (pts.length - 1)) * (w - 2) + 1;
        const y = max === min ? h / 2 : h - 2 - ((p - min) / (max - min)) * (h - 4);
        i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
      });
      ctx.stroke();
    });
  }

  let hist;
  async function historyChart(itemId, days = 90) {
    const el = document.getElementById("histChart");
    const r = await fetch(`/api/items/${itemId}/history?days=${days}`);
    const data = await r.json();
    const colors = SERIES();
    const names = Object.keys(data).sort();
    const datasets = names.map((name, i) => ({
      label: name,
      data: data[name].map(([d, v]) => ({ x: d, y: v })),
      borderColor: colors[i % 8],
      fill: false,
      stepped: true,
    }));
    if (hist) hist.destroy();
    hist = new Chart(el, { type: "line", data: { datasets }, options: base("EGP") });
    const legend = document.getElementById("histLegend");
    legend.innerHTML = names.length
      ? names.map((n, i) => `<span><span class="sw" style="background:${colors[i % 8]}"></span>${n}</span>`).join("")
      : '<span>No price history yet — the first scan fills this in.</span>';
    document.querySelectorAll("#rangeBtns button").forEach((b) => {
      b.classList.toggle("active", +b.dataset.days === days);
      b.onclick = () => historyChart(itemId, +b.dataset.days);
    });
  }

  async function testVendor(id) {
    const out = document.getElementById(`out-${id}`);
    const q = document.getElementById(`q-${id}`).value;
    out.textContent = "Running live search… (browser vendors take ~10–20s)";
    const fd = new FormData(); fd.append("q", q);
    try {
      const r = await fetch(`/api/vendors/${id}/test`, { method: "POST", body: fd });
      const j = await r.json();
      let s = `strategy: ${j.strategy_used || "-"}   results: ${j.count}${j.error ? `\nERROR: ${j.error}` : ""}\n\n`;
      for (const c of j.candidates) s += `${c.price == null ? "   —   " : String(Math.round(c.price)).padStart(7)}  ${c.title}\n          ${c.url}\n`;
      out.textContent = s || "no candidates";
    } catch (e) { out.textContent = "request failed: " + e; }
  }

  function openDialog(id) { document.getElementById(id).showModal(); }
  function openVendorForm() { openDialog("vendorDialog"); }
  function openPin(btn) {
    document.getElementById("pinForm").action = btn.dataset.action;
    document.getElementById("pinVendor").textContent = btn.dataset.vendor;
    document.getElementById("pinUrl").value = btn.dataset.url;
    openDialog("pinDialog");
  }
  function showQuiet(btn) {
    document.querySelectorAll("tr[data-quiet]").forEach((tr) => { tr.hidden = false; });
    btn.hidden = true;
  }

  async function pollStatus() {
    try {
      const st = await (await fetch("/api/status")).json();
      const el = document.getElementById("sched-status");
      if (el) el.textContent = st.scanning ? "⏳ scanning…" : st.last_scan ? `last scan ${new Date(st.last_scan + "Z").toLocaleTimeString()}` : "scan pending";
    } catch {}
  }
  setInterval(pollStatus, 15000);

  return { marketCharts, sparklines, historyChart, testVendor, openDialog, openVendorForm, openPin, showQuiet };
})();
