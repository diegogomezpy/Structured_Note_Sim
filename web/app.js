"use strict";

// ── API base URL ────────────────────────────────────────────────────────────
// Resolution order: ?api= query param → saved localStorage → same-origin (if the
// API is reverse-proxied alongside the site) → localhost:8000 for dev.
function defaultApiBase() {
  const clean = (u) => u.replace(/\/$/, "");
  const q = new URLSearchParams(location.search).get("api");
  if (q) return clean(q);                                   // per-link override
  const saved = localStorage.getItem("apiBase");
  if (saved) return clean(saved);                           // user set it in the box
  if (window.API_BASE) return clean(window.API_BASE);       // committed config.js
  if (["localhost", "127.0.0.1"].includes(location.hostname)) {
    return "http://localhost:8000";                          // local dev
  }
  return "";   // deployed but no backend configured yet — show a clear prompt
}
let API_BASE = defaultApiBase();

const $ = (id) => document.getElementById(id);

// ── Settings: editable API base ──────────────────────────────────────────────
$("apiBase").value = API_BASE;
$("saveApi").addEventListener("click", () => {
  API_BASE = $("apiBase").value.trim().replace(/\/$/, "");
  localStorage.setItem("apiBase", API_BASE);
  pingApi();
  loadUniverse();
});

async function pingApi() {
  if (!API_BASE) {
    $("apiStatus").textContent = "● no backend set";
    $("apiStatus").style.color = "var(--red)";
    return;
  }
  try {
    const r = await fetch(`${API_BASE}/health`);
    $("apiStatus").textContent = r.ok ? "● connected" : "● error";
    $("apiStatus").style.color = r.ok ? "var(--green)" : "var(--red)";
  } catch {
    $("apiStatus").textContent = "● offline";
    $("apiStatus").style.color = "var(--red)";
  }
}

// ── Populate the underlying picker from /universe ─────────────────────────────
async function loadUniverse() {
  const sel = $("tickers");
  if (!API_BASE) {
    showError("No backend configured. Set your API URL in the API panel (top-right), "
            + "or commit it to web/config.js, then reload.");
    return;
  }
  try {
    const r = await fetch(`${API_BASE}/universe`);
    const { options } = await r.json();
    sel.innerHTML = "";
    for (const o of options) {
      const opt = document.createElement("option");
      opt.value = o.symbol;
      opt.textContent = o.label;
      opt.dataset.name = o.label.includes(" — ") ? o.label.split(" — ").slice(1).join(" — ") : o.label;
      sel.appendChild(opt);
    }
    // Sensible default selection (first 3 US tech names if present).
    const want = ["MSFT", "AAPL", "NVDA"];
    let n = 0;
    for (const opt of sel.options) {
      if (want.includes(opt.value)) { opt.selected = true; n++; }
    }
    if (!n) for (let i = 0; i < Math.min(3, sel.options.length); i++) sel.options[i].selected = true;
  } catch (e) {
    showError(`Could not load universe from ${API_BASE} — is the backend running? (${e})`);
  }
}

// ── Build the NoteTerms config dict from the form ─────────────────────────────
function gatherTerms() {
  const sel = [...$("tickers").selectedOptions];
  if (sel.length < 1) throw new Error("Select at least one underlying.");
  if (sel.length > 5) throw new Error("Select at most five underlyings.");
  const tickers = {};
  for (const o of sel) tickers[o.value] = o.dataset.name || o.value;

  const basket = $("basket").value;
  const pct = (id) => parseFloat($(id).value) / 100;
  return {
    name: $("name").value || "Custom Note",
    maturity: parseFloat($("maturity").value),
    payment_freq: $("payment_freq").value,
    coupon_pa: pct("coupon_pa"),
    coupon_barrier: pct("coupon_barrier"),
    autocall_barrier: pct("autocall_barrier"),
    autocall_start_period: parseInt($("autocall_start_period").value, 10),
    knock_in_barrier: pct("knock_in_barrier"),
    memory: $("memory").checked,
    coupon_basket: basket,
    autocall_basket: basket,
    final_basket: $("rescue").checked ? "best_of" : "worst_of",
    final_redemption_barrier: 1.0,
    call_steepness: null,
    tickers,
  };
}

// ── Run simulation ────────────────────────────────────────────────────────────
$("run").addEventListener("click", runSimulation);

function requestBody() {
  return {
    terms: gatherTerms(),
    n_paths: parseInt($("n_paths").value, 10),
    seed: parseInt($("seed").value, 10),
    lang: "en",
  };
}

// POST helper that auto-retries once on 503 (the free-tier backend serialises
// heavy requests and may be waking from sleep).
async function apiPost(path, body, onWait) {
  for (let attempt = 0; attempt < 2; attempt++) {
    const r = await fetch(`${API_BASE}${path}`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (r.status !== 503 || attempt === 1) return r;
    if (onWait) onWait();
    await new Promise((res) => setTimeout(res, 6000));
  }
}

async function runSimulation() {
  showError("");
  let body;
  try { body = requestBody(); } catch (e) { return showError(e.message); }

  const btn = $("run");
  btn.disabled = true; btn.textContent = "Running…";
  try {
    const r = await apiPost("/simulate", body,
      () => { btn.textContent = "Waking backend…"; });
    if (r.status === 503) throw new Error(
      "Backend is busy or waking up (free tier sleeps when idle). Give it ~30s and click Run again.");
    if (!r.ok) throw new Error(`API ${r.status}: ${await r.text()}`);
    const data = await r.json();
    renderResults(data);
    $("pdf").disabled = false;
  } catch (e) {
    showError(`Simulation failed: ${e.message}`);
  } finally {
    btn.disabled = false; btn.textContent = "Run simulation";
  }
}

// ── Render metrics + figures ──────────────────────────────────────────────────
const METRIC_LABELS = {
  expected_irr: "Expected IRR p.a.",
  expected_total_return: "Total return",
  expected_coupon: "Expected coupon",
  prob_autocall: "P(autocall)",
  prob_barrier_event: "P(knock-in)",
  loss_given_knock_in: "Loss given knock-in",
};
const fmtPct = (v) => (v == null ? "—" : (v * 100).toFixed(2) + "%");

function renderResults(data) {
  $("results").classList.remove("hidden");
  $("resultTitle").textContent = `Results — ${data.meta.n_paths.toLocaleString()} paths`;

  const m = data.metrics;
  $("metrics").innerHTML = Object.entries(METRIC_LABELS)
    .map(([k, label]) => `<div class="metric"><div class="k">${label}</div><div class="v">${fmtPct(m[k])}</div></div>`)
    .join("");

  drawFig("fig_irr", data.figures.irr_dist);
  drawFig("fig_wof", data.figures.wof_fan);
  drawFig("fig_corr", data.figures.corr);

  const fans = $("fans");
  fans.innerHTML = "";
  (data.figures.individual || []).forEach((d, i) => {
    const div = document.createElement("div");
    div.className = "card";
    const chart = document.createElement("div");
    chart.id = `fan_${i}`; chart.className = "chart";
    div.appendChild(chart); fans.appendChild(div);
    drawFig(`fan_${i}`, d.figure);
  });
  $("results").scrollIntoView({ behavior: "smooth", block: "start" });
}

function drawFig(divId, figJson) {
  const fig = JSON.parse(figJson);
  Plotly.newPlot(divId, fig.data, fig.layout, { responsive: true, displaylogo: false });
}

// ── PDF download ──────────────────────────────────────────────────────────────
$("pdf").addEventListener("click", async () => {
  showError("");
  let body;
  try { body = requestBody(); } catch (e) { return showError(e.message); }
  const btn = $("pdf");
  btn.disabled = true; btn.textContent = "Building…";
  try {
    const r = await apiPost("/pdf", body, () => { btn.textContent = "Waking backend…"; });
    if (r.status === 503) throw new Error("Backend busy — wait a moment and try again.");
    if (!r.ok) throw new Error(`API ${r.status}`);
    const blob = await r.blob();
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = (body.terms.name || "note").replace(/[^A-Za-z0-9._-]+/g, "_") + "_report.pdf";
    a.click();
    URL.revokeObjectURL(a.href);
  } catch (e) {
    showError(`PDF failed: ${e.message}`);
  } finally {
    btn.disabled = false; btn.textContent = "Download PDF";
  }
});

function showError(msg) { $("error").textContent = msg; }

// ── Boot ──────────────────────────────────────────────────────────────────────
pingApi();
loadUniverse();
