// Portal: delivered vs prescribed (FR-20). Plain SVG, no library.
// 7 d / 30 d: daily totals from /api/patients/{id}/daily (simulated history).
// 24 h: there is no hourly endpoint, so it shows this session's live readings
// from the rolling buffer in data.js, and says so.
// Under-target days use a hatch pattern AND an entry in the table: never colour alone.

import { currentLang, escapeHtml, fmtNumber, fmtTime, ml, t } from "/shared/core.js";
import { api, isNotAvailable } from "/shared/data.js";

const $ = (id) => document.getElementById(id);
const H = 220;
const M = { top: 26, right: 12, bottom: 34, left: 56 };
const UNDER = 0.9; // the hub's demo exception threshold (docs/API.md)

function niceMax(v) {
  if (v <= 0) return 100;
  const step = 10 ** Math.floor(Math.log10(v));
  return Math.ceil((v * 1.1) / step) * step;
}

const fmtDay = (iso) =>
  new Date(`${iso}T00:00:00Z`).toLocaleDateString(currentLang(),
    { month: "short", day: "numeric", timeZone: "UTC" });

function svgOpen(w, titleId, descId, title, desc) {
  return `<svg width="${w}" height="${H}" viewBox="0 0 ${w} ${H}" role="img" ` +
    `aria-labelledby="${titleId} ${descId}"><title id="${titleId}">${escapeHtml(title)}</title>` +
    `<desc id="${descId}">${escapeHtml(desc)}</desc>` +
    '<defs><pattern id="hatch" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)">' +
    '<rect width="6" height="6" class="c-under-bg"/><line x1="0" y1="0" x2="0" y2="6" class="c-under-line"/></pattern></defs>';
}

function yAxis(w, max) {
  const innerH = H - M.top - M.bottom;
  let out = "";
  for (let i = 0; i <= 4; i++) {
    const v = (max / 4) * i;
    const y = M.top + innerH - (v / max) * innerH;
    out += `<line x1="${M.left}" x2="${w - M.right}" y1="${y}" y2="${y}" class="grid"/>` +
      `<text x="${M.left - 6}" y="${y + 5}" text-anchor="end" class="axis">${escapeHtml(fmtNumber(v))}</text>`;
  }
  return out + `<text x="${M.left - 6}" y="14" text-anchor="end" class="axis">mL</text>`;
}

function dailySvg(rows, w) {
  const innerW = w - M.left - M.right;
  const innerH = H - M.top - M.bottom;
  const max = niceMax(Math.max(...rows.map((r) => Math.max(r.delivered_ml, r.prescribed_ml))));
  const slot = innerW / rows.length;
  const bar = Math.max(2, slot * 0.62);
  const y = (v) => M.top + innerH - (v / max) * innerH;
  const every = Math.max(1, Math.ceil(rows.length / Math.max(1, Math.floor(innerW / 60))));
  const under = rows.filter((r) => r.delivered_ml < UNDER * r.prescribed_ml).length;

  let body = yAxis(w, max);
  rows.forEach((r, i) => {
    const x = M.left + i * slot + (slot - bar) / 2;
    const isUnder = r.delivered_ml < UNDER * r.prescribed_ml;
    body += `<rect x="${x}" y="${y(r.delivered_ml)}" width="${bar}" height="${y(0) - y(r.delivered_ml)}" ` +
      `class="${isUnder ? "c-under" : "c-delivered"}"><title>${escapeHtml(
        `${fmtDay(r.date)}: ${ml(r.delivered_ml)} / ${ml(r.prescribed_ml)}`)}</title></rect>`;
    body += `<line x1="${M.left + i * slot + 1}" x2="${M.left + (i + 1) * slot - 1}" ` +
      `y1="${y(r.prescribed_ml)}" y2="${y(r.prescribed_ml)}" class="c-prescribed"/>`;
    if (i % every === 0) {
      body += `<text x="${M.left + i * slot + slot / 2}" y="${H - 12}" text-anchor="middle" class="axis">` +
        `${escapeHtml(fmtDay(r.date))}</text>`;
    }
  });
  const desc = t("chart_desc", { days: rows.length, under });
  return svgOpen(w, "chart-t", "chart-d", t("chart_title"), desc) + body + "</svg>";
}

function liveSvg(points, w) {
  const innerW = w - M.left - M.right;
  const innerH = H - M.top - M.bottom;
  const t0 = Date.parse(points[0].at);
  const t1 = Math.max(t0 + 1000, Date.parse(points[points.length - 1].at));
  const max = niceMax(Math.max(...points.map((p) => Math.max(p.delivered_ml, p.target_ml))));
  const x = (at) => M.left + ((Date.parse(at) - t0) / (t1 - t0)) * innerW;
  const y = (v) => M.top + innerH - (v / max) * innerH;
  const line = (key) => points.map((p, i) => `${i ? "L" : "M"}${x(p.at).toFixed(1)},${y(p[key]).toFixed(1)}`).join(" ");
  const last = points[points.length - 1];
  const desc = t("chart_live_desc", { delivered: ml(last.delivered_ml), target: ml(last.target_ml) });
  return svgOpen(w, "chart-t", "chart-d", t("chart_title"), desc) + yAxis(w, max) +
    `<path d="${line("target_ml")}" class="c-prescribed-line"/>` +
    `<path d="${line("delivered_ml")}" class="c-delivered-line"/>` +
    `<text x="${M.left}" y="${H - 12}" class="axis">${escapeHtml(fmtTime(points[0].at))}</text>` +
    `<text x="${w - M.right}" y="${H - 12}" text-anchor="end" class="axis">${escapeHtml(fmtTime(last.at))}</text>` +
    "</svg>";
}

function swatch(cls) {
  return `<svg width="28" height="16" aria-hidden="true" focusable="false">${
    cls === "line"
      ? '<line x1="2" y1="8" x2="26" y2="8" class="c-prescribed"/>'
      : `<defs><pattern id="hatch-l" width="6" height="6" patternUnits="userSpaceOnUse" patternTransform="rotate(45)"><rect width="6" height="6" class="c-under-bg"/><line x1="0" y1="0" x2="0" y2="6" class="c-under-line"/></pattern></defs><rect x="2" y="2" width="24" height="12" class="${cls}"${cls === "c-under" ? ' style="fill:url(#hatch-l)"' : ""}/>`
  }</svg>`;
}

function table(headers, rows) {
  return `<table class="data"><thead><tr>${headers.map((h) => `<th scope="col">${escapeHtml(h)}</th>`).join("")}` +
    `</tr></thead><tbody>${rows.map((r) => `<tr>${r.map((c, i) =>
      i === 0 ? `<th scope="row">${escapeHtml(c)}</th>` : `<td>${escapeHtml(c)}</td>`).join("")}</tr>`).join("")}` +
    "</tbody></table>";
}

export function initChart(store) {
  let range = "7d";
  let patientId = null;
  let daily = { key: null, rows: null, error: null };

  const buttons = [...document.querySelectorAll("#ranges .range")];
  const paintButtons = () => buttons.forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.range === range)));
  buttons.forEach((b) => b.addEventListener("click", () => {
    range = b.dataset.range;
    paintButtons();
    refresh();
  }));
  paintButtons();

  async function loadDaily() {
    const days = range === "30d" ? 30 : 7;
    const key = `${patientId}/${days}`;
    if (daily.key === key) return;
    const request = { key, rows: null, error: null };
    daily = request;
    render();
    try {
      request.rows = await api.daily(patientId, days);
    } catch (err) {
      request.error = isNotAvailable(err) ? "clin_unavailable" : "error_generic";
    }
  }

  function render() {
    const el = $("chart");
    const w = Math.max(240, el.clientWidth);
    let svg = "";
    let legend = [["c-delivered", t("chart_delivered")], ["line", t("chart_prescribed")]];
    let note = "";
    let tableHtml = "";
    let summary = "";

    if (range === "24h") {
      const points = store.state.history.filter((p) => p.target_ml > 0);
      note = t("chart_live_note");
      if (points.length < 2) {
        svg = `<p class="empty">${escapeHtml(t("chart_no_data"))}</p>`;
      } else {
        svg = liveSvg(points, w);
        const last = points[points.length - 1];
        summary = t("chart_live_desc", { delivered: ml(last.delivered_ml), target: ml(last.target_ml) });
        legend = [["c-delivered", t("chart_delivered")], ["line", t("chart_prescribed")]];
        tableHtml = table([t("chart_col_time"), t("chart_delivered"), t("chart_prescribed")],
          points.slice(-12).map((p) => [fmtTime(p.at), ml(p.delivered_ml), ml(p.target_ml)]));
      }
    } else if (!patientId || daily.error || !daily.rows) {
      const key = !patientId || daily.error === "clin_unavailable" ? "clin_unavailable"
        : daily.error || "loading";
      svg = `<p class="empty">${escapeHtml(t(key))}</p>`;
    } else if (!daily.rows.length) {
      svg = `<p class="empty">${escapeHtml(t("chart_no_data"))}</p>`;
    } else {
      svg = dailySvg(daily.rows, w);
      summary = t("chart_totals", {
        days: daily.rows.length,
        delivered: ml(daily.rows.reduce((sum, r) => sum + r.delivered_ml, 0)),
        prescribed: ml(daily.rows.reduce((sum, r) => sum + r.prescribed_ml, 0)),
        under: daily.rows.filter((r) => r.delivered_ml < UNDER * r.prescribed_ml).length,
      });
      legend.push(["c-under", t("chart_under")]);
      tableHtml = table(
        [t("chart_col_date"), t("chart_delivered"), t("chart_prescribed"), t("chart_under"), t("chart_col_alarms")],
        daily.rows.map((r) => [fmtDay(r.date), ml(r.delivered_ml), ml(r.prescribed_ml),
          r.delivered_ml < UNDER * r.prescribed_ml ? t("chart_yes") : t("chart_no"), String(r.alarm_count)]));
    }
    const simulated = range !== "24h" && daily.rows?.some((r) => r.simulated);
    el.innerHTML = svg;
    $("chart-legend").innerHTML = legend.map(([cls, label]) => `<li>${swatch(cls)}<span>${escapeHtml(label)}</span></li>`).join("") +
      (simulated ? `<li class="sim-note">${escapeHtml(t("simulated_data"))}</li>` : "");
    $("chart-note").textContent = note;
    $("chart-summary").textContent = summary;
    $("chart-summary").hidden = !summary;
    $("chart-table").innerHTML = tableHtml;
    $("chart-details").hidden = !tableHtml;
  }

  async function refresh() {
    if (range !== "24h" && patientId) await loadDaily();
    render();
  }

  let lastLive = 0;
  store.subscribe(() => {
    if (range !== "24h" || Date.now() - lastLive < 2000) return;
    lastLive = Date.now();
    render();
  });
  let lastWidth = 0;
  new ResizeObserver(([entry]) => {
    const w = Math.round(entry.contentRect.width);
    if (w !== lastWidth) {
      lastWidth = w;
      render();
    }
  }).observe($("chart"));

  return {
    setPatient(id) {
      if (id === patientId) return;
      patientId = id;
      daily = { key: null, rows: null, error: null };
      refresh();
    },
    rerender: () => {
      daily.key = daily.rows ? daily.key : null;
      render();
    },
    noPatients() {
      patientId = null;
      render();
    },
  };
}
