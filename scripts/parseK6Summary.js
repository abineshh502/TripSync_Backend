/**
 * TripSync Backend – k6 Summary Parser + Executive HTML Report Generator
 * ─────────────────────────────────────────────────────────────────────────────
 * Reads k6-summary.json, then:
 *   1. Writes a rich Markdown table to $GITHUB_STEP_SUMMARY
 *   2. Generates executive load-test-report.html with charts, search, dark/light mode
 *
 * Defensive `getMetricValue` handles BOTH k6 JSON schemas:
 *   - Nested  : { "values": { "p(95)": 42, "avg": 10 } }   (k6 ≥ v0.40)
 *   - Flat    : { "p(95)": 42, "avg": 10 }                 (older / Rate metrics)
 *
 * Usage:
 *   node scripts/parseK6Summary.js [path/to/k6-summary.json]
 */

'use strict';

const fs   = require('fs');
const path = require('path');

// ── Paths & Environment ───────────────────────────────────────────────────────
const SUMMARY_PATH  = process.argv[2] ?? path.join(process.cwd(), 'k6-summary.json');
const HTML_OUT      = path.join(path.dirname(SUMMARY_PATH), 'load-test-report.html');
const STEP_SUMMARY  = process.env.GITHUB_STEP_SUMMARY;
const BUILD_NUMBER  = process.env.GITHUB_RUN_NUMBER  ?? 'Local';
const COMMIT_SHA    = (process.env.GITHUB_SHA        ?? 'local-dev').substring(0, 7);
const REPO          = process.env.GITHUB_REPOSITORY  ?? 'abineshh502/TripSync_Backend';
const RUN_ID        = process.env.GITHUB_RUN_ID      ?? 'N/A';
const BRANCH        = process.env.GITHUB_REF_NAME    ?? 'main';

// ── Defensive metric extractor ────────────────────────────────────────────────
function getMetricValue(metricObj, key, fb = 0) {
  if (!metricObj || typeof metricObj !== 'object') return fb;

  if (metricObj.values && typeof metricObj.values === 'object') {
    const v = metricObj.values[key];
    if (v !== undefined && v !== null && !isNaN(v)) return typeof v === 'number' ? v : Number(v) || fb;
  }

  const v = metricObj[key];
  if (v !== undefined && v !== null && !isNaN(v)) return typeof v === 'number' ? v : Number(v) || fb;

  return fb;
}

// ── Formatting helpers ────────────────────────────────────────────────────────
const safeNum = (v, fb = 0) => (typeof v === 'number' && !isNaN(v) ? v : fb);
const ms      = (v) => `${safeNum(v).toFixed(2)} ms`;
const pct     = (v) => `${(safeNum(v) * 100).toFixed(2)}%`;
const rps     = (v) => `${safeNum(v).toFixed(2)} req/s`;
const integer = (v) => `${Math.round(safeNum(v)).toLocaleString()}`;

// ── Parse k6-summary.json ─────────────────────────────────────────────────────
function parseSummary(filePath) {
  let raw = {};
  if (fs.existsSync(filePath)) {
    try {
      raw = JSON.parse(fs.readFileSync(filePath, 'utf8'));
    } catch (e) {
      console.warn(`⚠️ Failed to parse JSON from ${filePath}: ${e.message}`);
    }
  } else {
    console.warn(`⚠️ k6-summary.json not found at: ${filePath}`);
  }

  const m = raw.metrics ?? {};

  // ── Latency metrics ────────────────────────────────────────────────────────
  const dur   = m.http_req_duration ?? {};
  const avgMs = getMetricValue(dur, 'avg');
  const minMs = getMetricValue(dur, 'min');
  const maxMs = getMetricValue(dur, 'max');
  const p95Ms = getMetricValue(dur, 'p(95)');
  const p90Ms = getMetricValue(dur, 'p(90)');
  const p99Ms = getMetricValue(dur, 'p(99)');
  const medMs = getMetricValue(dur, 'med');

  // ── Throughput ─────────────────────────────────────────────────────────────
  const reqs   = m.http_reqs ?? {};
  const total  = getMetricValue(reqs, 'count');
  const rpsVal = getMetricValue(reqs, 'rate');

  // ── Failure rate ───────────────────────────────────────────────────────────
  const failed    = m.http_req_failed ?? {};
  const failRate  = getMetricValue(failed, 'rate');
  const failCount = Math.round(total * failRate);
  const passCount = total - failCount;

  // ── Assertions (checks) ────────────────────────────────────────────────────
  const checksM     = m.checks ?? {};
  const checkPasses = getMetricValue(checksM, 'passes', getMetricValue(checksM, 'count'));
  const checkFails  = getMetricValue(checksM, 'fails');
  const totalChecks = checkPasses + checkFails;
  const checkRate   = totalChecks > 0 ? (checkPasses / totalChecks) : getMetricValue(checksM, 'value', 1.0);

  // ── Per-endpoint custom metrics ────────────────────────────────────────────
  const endpointStats = {
    'Health API':  extractTrend(m.health_api_duration,  400),
    'Root API':    extractTrend(m.root_api_duration,    600),
    'Trips API':   extractTrend(m.trips_api_duration,   600),
    'Weather API': extractTrend(m.weather_api_duration, 2500),
    'Safety API':  extractTrend(m.safety_api_duration,  5000),
  };

  // ── Threshold results ──────────────────────────────────────────────────────
  const thresholds = raw.thresholds ?? {};
  const thresholdEntries = Object.values(thresholds);
  const overallPass = thresholdEntries.length === 0
    ? (failRate < 0.05)
    : thresholdEntries.every((t) => t.ok === true || t.passed === true);

  return {
    overallPass, avgMs, minMs, medMs, maxMs, p90Ms, p95Ms, p99Ms,
    total, passCount, failCount, failRate, rpsVal,
    checkRate, checkPasses, checkFails, totalChecks,
    endpointStats, thresholds,
    rawJson: raw,
    buildNumber: BUILD_NUMBER,
    commitSha: COMMIT_SHA,
    runId: RUN_ID,
    branch: BRANCH,
    repo: REPO,
  };
}

function extractTrend(metricObj, slaMs) {
  if (!metricObj) return { avg: 0, p95: 0, min: 0, max: 0, present: false, slaMs };
  return {
    avg:     getMetricValue(metricObj, 'avg'),
    p95:     getMetricValue(metricObj, 'p(95)'),
    min:     getMetricValue(metricObj, 'min'),
    max:     getMetricValue(metricObj, 'max'),
    present: true,
    slaMs,
  };
}

// ── GitHub Step Summary (Markdown) ────────────────────────────────────────────
function buildMarkdown(s) {
  const now     = new Date().toUTCString();
  const overall = s.overallPass ? '✅ **PASSED**' : '❌ **FAILED**';

  const thresholdRows = Object.entries(s.thresholds).map(([name, info]) => {
    const ok = info.ok !== undefined ? info.ok : (info.passed ?? false);
    return `| \`${name}\` | ${info.threshold ?? '—'} | ${ok ? '🟢 PASS' : '🔴 FAIL'} |`;
  });

  const endpointRows = Object.entries(s.endpointStats).map(([name, stat]) => {
    if (!stat.present) return `| **${name}** | — | — | — |`;
    const pass = stat.p95 < stat.slaMs;
    const p95Status = pass ? '🟢 PASS' : '🔴 FAIL';
    return `| **${name}** | ${ms(stat.avg)} | ${ms(stat.p95)} | ${p95Status} |`;
  });

  return `# 🚀 TripSync Backend Load Test Results

> **Overall Result:** ${overall}
> **Date:** ${now}
> **Build:** \`#${s.buildNumber}\` | **Commit:** \`${s.commitSha}\` | **Branch:** \`${s.branch}\`
> **Repository:** \`${s.repo}\` | **Run ID:** \`${s.runId}\`

---

## 📊 Request Summary

| Metric | Value |
|--------|-------|
| **Total Requests** | ${integer(s.total)} |
| **Successful Requests** | ${integer(s.passCount)} |
| **Failed Requests** | ${integer(s.failCount)} |
| **Throughput (RPS)** | ${rps(s.rpsVal)} |
| **Failure Rate** | ${pct(s.failRate)} |
| **Assertion Pass Rate** | ${pct(s.checkRate)} |

---

## ⏱️ Response Time Statistics

| Metric | Value | SLA |
|--------|-------|-----|
| **Average** | ${ms(s.avgMs)} | — |
| **Minimum** | ${ms(s.minMs)} | — |
| **Median (p50)** | ${ms(s.medMs)} | — |
| **P95 Latency** | ${ms(s.p95Ms)} | ${s.p95Ms < 5000 ? '🟢 PASS (<5000ms)' : '🔴 FAIL (≥5000ms)'} |
| **P99 Latency** | ${ms(s.p99Ms)} | — |
| **Maximum** | ${ms(s.maxMs)} | — |

---

## 🔍 Endpoint Performance

| Endpoint | Avg Latency | P95 Latency | Status |
|----------|-------------|-------------|--------|
${endpointRows.join('\n')}

---

${thresholdRows.length > 0 ? `## 📋 Threshold Results\n\n| Metric | Threshold | Status |\n|--------|-----------|--------|\n${thresholdRows.join('\n')}\n\n---\n\n` : ''}## ℹ️ Test Configuration & Artifacts

- **Virtual Users:** 100 VUs
- **Duration:** 1 minute
- **Global SLA:** \`http_req_failed < 5%\` | \`global p(95) < 5000ms\`
- **Artifacts Generated:** \`k6-summary.json\`, \`load-test-report.html\`, \`TripSync_Backend_LoadTest_Report.xlsx\`
`;
}

// ── Executive HTML Report ─────────────────────────────────────────────────────
function buildHtml(s) {
  const now = new Date().toUTCString();
  const statusColor = s.overallPass ? '#22c55e' : '#ef4444';
  const statusText = s.overallPass ? 'PASSED' : 'FAILED';
  const successPct = ((1 - s.failRate) * 100).toFixed(2);

  const endpointRows = Object.entries(s.endpointStats).map(([name, stat]) => {
    if (!stat.present) {
      return `<tr data-status="skip">
        <td><strong>${name}</strong></td>
        <td>—</td>
        <td>—</td>
        <td>—</td>
        <td>—</td>
        <td><span class="badge badge-skip">SKIPPED</span></td>
      </tr>`;
    }
    const pass = stat.p95 < stat.slaMs;
    return `<tr data-status="${pass ? 'pass' : 'fail'}">
      <td><strong>${name}</strong></td>
      <td>${stat.avg.toFixed(2)} ms</td>
      <td>${stat.min.toFixed(2)} ms</td>
      <td>${stat.p95.toFixed(2)} ms</td>
      <td>&lt; ${stat.slaMs} ms</td>
      <td><span class="badge ${pass ? 'badge-pass' : 'badge-fail'}">${pass ? 'PASS' : 'FAIL'}</span></td>
    </tr>`;
  });

  const thresholdRows = Object.entries(s.thresholds).map(([name, info]) => {
    const ok = info.ok !== undefined ? info.ok : (info.passed ?? false);
    return `<tr data-status="${ok ? 'pass' : 'fail'}">
      <td><code>${name}</code></td>
      <td>${info.threshold ?? '—'}</td>
      <td><span class="badge ${ok ? 'badge-pass' : 'badge-fail'}">${ok ? 'PASS' : 'FAIL'}</span></td>
    </tr>`;
  });

  const rawJsonStr = JSON.stringify(s.rawJson, null, 2);

  return `<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>TripSync Backend — Executive Load Test Dashboard</title>
  <style>
    :root {
      --bg: #0b1120;
      --surface: #1e293b;
      --surface-hover: #334155;
      --border: #334155;
      --text: #f8fafc;
      --text-muted: #94a3b8;
      --accent-blue: #38bdf8;
      --accent-purple: #c084fc;
      --pass-green: #22c55e;
      --fail-red: #ef4444;
      --warning-yellow: #f59e0b;
      --card-bg: rgba(30, 41, 59, 0.7);
    }
    [data-theme="light"] {
      --bg: #f8fafc;
      --surface: #ffffff;
      --surface-hover: #f1f5f9;
      --border: #e2e8f0;
      --text: #0f172a;
      --text-muted: #64748b;
      --accent-blue: #0284c7;
      --accent-purple: #7e22ce;
      --pass-green: #16a34a;
      --fail-red: #dc2626;
      --warning-yellow: #d97706;
      --card-bg: rgba(255, 255, 255, 0.9);
    }
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
      line-height: 1.5;
      padding: 24px;
      transition: background 0.3s, color 0.3s;
    }
    .container { max-width: 1240px; margin: 0 auto; }
    
    header {
      background: linear-gradient(135deg, rgba(15,23,42,0.9) 0%, rgba(30,58,138,0.8) 100%);
      border: 1px solid var(--border);
      border-radius: 16px;
      padding: 28px;
      margin-bottom: 24px;
      position: relative;
      backdrop-filter: blur(10px);
    }
    .header-top { display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 16px; }
    .title-area h1 { font-size: 2rem; font-weight: 800; color: var(--accent-blue); display: flex; align-items: center; gap: 10px; }
    .title-area p { color: var(--text-muted); font-size: 0.95rem; margin-top: 4px; }
    .actions { display: flex; gap: 12px; align-items: center; }

    .btn {
      background: var(--surface);
      border: 1px solid var(--border);
      color: var(--text);
      padding: 8px 16px;
      border-radius: 8px;
      font-size: 0.85rem;
      font-weight: 600;
      cursor: pointer;
      display: inline-flex;
      align-items: center;
      gap: 6px;
      transition: all 0.2s;
    }
    .btn:hover { background: var(--surface-hover); border-color: var(--accent-blue); }

    .badge-status {
      padding: 8px 20px;
      border-radius: 999px;
      font-size: 1rem;
      font-weight: 800;
      letter-spacing: 0.05em;
      border: 2px solid ${statusColor};
      color: ${statusColor};
      background: ${s.overallPass ? 'rgba(34,197,94,0.15)' : 'rgba(239,68,68,0.15)'};
    }

    .meta-grid {
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 16px;
      margin-top: 20px;
      padding-top: 20px;
      border-top: 1px solid var(--border);
    }
    .meta-box label { font-size: 0.75rem; text-transform: uppercase; color: var(--text-muted); letter-spacing: 0.05em; font-weight: 600; }
    .meta-box div { font-size: 0.95rem; font-weight: 600; font-family: monospace; }

    /* KPI Cards */
    .kpi-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 16px; margin-bottom: 24px; }
    .card {
      background: var(--card-bg);
      border: 1px solid var(--border);
      border-radius: 14px;
      padding: 20px;
      backdrop-filter: blur(8px);
      transition: transform 0.2s, border-color 0.2s;
    }
    .card:hover { transform: translateY(-2px); border-color: var(--accent-blue); }
    .card-title { font-size: 0.8rem; text-transform: uppercase; color: var(--text-muted); letter-spacing: 0.06em; font-weight: 700; margin-bottom: 8px; }
    .card-value { font-size: 1.8rem; font-weight: 800; color: var(--accent-blue); }
    .card-sub { font-size: 0.82rem; color: var(--text-muted); margin-top: 4px; }

    /* Charts Section */
    .section { margin-bottom: 28px; }
    .section-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; }
    .section-title { font-size: 1.1rem; font-weight: 700; color: var(--text); text-transform: uppercase; letter-spacing: 0.05em; display: flex; align-items: center; gap: 8px; }
    
    .charts-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(340px, 1fr)); gap: 20px; margin-bottom: 24px; }
    .chart-card { background: var(--card-bg); border: 1px solid var(--border); border-radius: 14px; padding: 20px; text-align: center; }
    .chart-title { font-size: 0.9rem; font-weight: 700; color: var(--text-muted); margin-bottom: 16px; }

    /* SVG Donut Chart */
    .donut-chart { position: relative; width: 140px; height: 140px; margin: 0 auto; }
    .donut-chart svg { transform: rotate(-90deg); border-radius: 50%; }
    .donut-center { position: absolute; top: 50%; left: 50%; transform: translate(-50%, -50%); font-size: 1.2rem; font-weight: 800; }

    /* Bar Charts */
    .bar-group { display: flex; flex-direction: column; gap: 12px; margin-top: 10px; }
    .bar-row { display: flex; flex-direction: column; gap: 4px; text-align: left; }
    .bar-label { display: flex; justify-content: space-between; font-size: 0.82rem; font-weight: 600; }
    .bar-track { background: var(--border); height: 10px; border-radius: 999px; overflow: hidden; }
    .bar-fill { height: 100%; border-radius: 999px; transition: width 0.6s ease; }

    /* Data Tables */
    .table-container { background: var(--card-bg); border: 1px solid var(--border); border-radius: 14px; overflow: hidden; }
    .table-toolbar { padding: 14px 20px; background: var(--surface); border-bottom: 1px solid var(--border); display: flex; justify-content: space-between; gap: 12px; flex-wrap: wrap; }
    .search-box { background: var(--bg); border: 1px solid var(--border); color: var(--text); padding: 6px 14px; border-radius: 6px; font-size: 0.85rem; width: 240px; }
    .filter-buttons { display: flex; gap: 6px; }

    table { width: 100%; border-collapse: collapse; text-align: left; font-size: 0.9rem; }
    th { background: var(--surface); color: var(--text-muted); padding: 12px 16px; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.06em; border-bottom: 1px solid var(--border); }
    td { padding: 14px 16px; border-bottom: 1px solid var(--border); }
    tr:last-child td { border-bottom: none; }
    tr:hover td { background: var(--surface-hover); }

    .badge { display: inline-block; padding: 4px 10px; border-radius: 999px; font-size: 0.75rem; font-weight: 700; text-transform: uppercase; }
    .badge-pass { background: rgba(34,197,94,0.2); color: var(--pass-green); border: 1px solid var(--pass-green); }
    .badge-fail { background: rgba(239,68,68,0.2); color: var(--fail-red); border: 1px solid var(--fail-red); }
    .badge-skip { background: rgba(148,163,184,0.2); color: var(--text-muted); border: 1px solid var(--border); }

    code { background: var(--surface); padding: 2px 6px; border-radius: 4px; font-family: monospace; color: var(--accent-purple); font-size: 0.85rem; }

    /* Collapsible JSON */
    .json-box { background: #090d16; border: 1px solid var(--border); border-radius: 8px; padding: 16px; max-height: 400px; overflow-y: auto; font-family: monospace; font-size: 0.8rem; color: #a5f3fc; }

    footer { text-align: center; margin-top: 40px; color: var(--text-muted); font-size: 0.8rem; padding-top: 20px; border-top: 1px solid var(--border); }
  </style>
</head>
<body>
<div class="container">

  <!-- Header Banner -->
  <header>
    <div class="header-top">
      <div class="title-area">
        <h1>⚡ TripSync Backend — Load Test Executive Report</h1>
        <p>Enterprise CI/CD Performance & Quality Assurance Audit Dashboard</p>
      </div>
      <div class="actions">
        <span class="badge-status">${statusText}</span>
        <button class="btn" onclick="toggleTheme()">🌓 Theme</button>
        <button class="btn" onclick="downloadJson()">📥 JSON</button>
      </div>
    </div>
    <div class="meta-grid">
      <div class="meta-box"><label>Build Number</label><div>#${s.buildNumber}</div></div>
      <div class="meta-box"><label>Commit SHA</label><div>${s.commitSha}</div></div>
      <div class="meta-box"><label>Branch</label><div>${s.branch}</div></div>
      <div class="meta-box"><label>Run ID</label><div>${s.runId}</div></div>
      <div class="meta-box"><label>Execution Date</label><div>${now}</div></div>
    </div>
  </header>

  <!-- KPI Cards Grid -->
  <div class="kpi-grid">
    <div class="card">
      <div class="card-title">Total Requests</div>
      <div class="card-value">${integer(s.total)}</div>
      <div class="card-sub">Throughput: ${rps(s.rpsVal)}</div>
    </div>
    <div class="card">
      <div class="card-title">Overall Success Rate</div>
      <div class="card-value" style="color:var(--pass-green)">${successPct}%</div>
      <div class="card-sub">${integer(s.passCount)} passed / ${integer(s.failCount)} failed</div>
    </div>
    <div class="card">
      <div class="card-title">Avg Response Time</div>
      <div class="card-value">${s.avgMs.toFixed(1)}<span style="font-size:0.9rem;font-weight:500"> ms</span></div>
      <div class="card-sub">Median (p50): ${s.medMs.toFixed(1)} ms</div>
    </div>
    <div class="card">
      <div class="card-title">P95 Latency</div>
      <div class="card-value" style="color:${s.p95Ms < 5000 ? 'var(--accent-blue)' : 'var(--fail-red)'}">${s.p95Ms.toFixed(1)}<span style="font-size:0.9rem;font-weight:500"> ms</span></div>
      <div class="card-sub">Global SLA: &lt; 5000 ms</div>
    </div>
    <div class="card">
      <div class="card-title">Assertion Pass Rate</div>
      <div class="card-value">${(s.checkRate * 100).toFixed(1)}%</div>
      <div class="card-sub">${integer(s.checkPasses)} passed checks</div>
    </div>
  </div>

  <!-- Visualizations -->
  <div class="section">
    <div class="section-title">📊 Performance Visualizations</div>
    <div class="charts-grid">
      
      <!-- Donut Chart -->
      <div class="chart-card">
        <div class="chart-title">Request Pass vs Failure Breakdown</div>
        <div class="donut-chart">
          <svg width="140" height="140" viewBox="0 0 42 42">
            <circle cx="21" cy="21" r="15.91549430918954" fill="transparent" stroke="var(--fail-red)" stroke-width="5"></circle>
            <circle cx="21" cy="21" r="15.91549430918954" fill="transparent" stroke="var(--pass-green)" stroke-width="5"
              stroke-dasharray="${(1 - s.failRate) * 100} ${s.failRate * 100}" stroke-dashoffset="25"></circle>
          </svg>
          <div class="donut-center">${successPct}%</div>
        </div>
        <div class="card-sub" style="margin-top:12px">🟢 ${integer(s.passCount)} Passed &nbsp;|&nbsp; 🔴 ${integer(s.failCount)} Failed</div>
      </div>

      <!-- Latency Distribution Bar Chart -->
      <div class="chart-card">
        <div class="chart-title">Latency Percentiles (ms)</div>
        <div class="bar-group">
          <div class="bar-row">
            <div class="bar-label"><span>Min Latency</span><span>${s.minMs.toFixed(1)} ms</span></div>
            <div class="bar-track"><div class="bar-fill" style="width:${Math.min(100, (s.minMs/s.maxMs)*100)}%; background:var(--accent-blue)"></div></div>
          </div>
          <div class="bar-row">
            <div class="bar-label"><span>Avg Latency</span><span>${s.avgMs.toFixed(1)} ms</span></div>
            <div class="bar-track"><div class="bar-fill" style="width:${Math.min(100, (s.avgMs/s.maxMs)*100)}%; background:var(--accent-blue)"></div></div>
          </div>
          <div class="bar-row">
            <div class="bar-label"><span>P95 Latency</span><span>${s.p95Ms.toFixed(1)} ms</span></div>
            <div class="bar-track"><div class="bar-fill" style="width:${Math.min(100, (s.p95Ms/s.maxMs)*100)}%; background:var(--warning-yellow)"></div></div>
          </div>
          <div class="bar-row">
            <div class="bar-label"><span>Max Latency</span><span>${s.maxMs.toFixed(1)} ms</span></div>
            <div class="bar-track"><div class="bar-fill" style="width:100%; background:var(--accent-purple)"></div></div>
          </div>
        </div>
      </div>

    </div>
  </div>

  <!-- Endpoint Status Table -->
  <div class="section">
    <div class="section-title">🔍 Endpoint Performance Audit</div>
    <div class="table-container">
      <div class="table-toolbar">
        <input type="text" id="searchInput" class="search-box" placeholder="Search endpoint..." onkeyup="filterTable()"/>
        <div class="filter-buttons">
          <button class="btn" onclick="filterStatus('all')">All</button>
          <button class="btn" onclick="filterStatus('pass')">Passed</button>
          <button class="btn" onclick="filterStatus('fail')">Failed</button>
        </div>
      </div>
      <table id="endpointTable">
        <thead>
          <tr>
            <th>Endpoint Name</th>
            <th>Avg Latency</th>
            <th>Min Latency</th>
            <th>P95 Latency</th>
            <th>Target Budget</th>
            <th>Status</th>
          </tr>
        </thead>
        <tbody>
          ${endpointRows.join('')}
        </tbody>
      </table>
    </div>
  </div>

  <!-- Threshold Results Table -->
  ${thresholdRows.length > 0 ? `
  <div class="section">
    <div class="section-title">📋 Service Level Agreement (SLA) Thresholds</div>
    <div class="table-container">
      <table>
        <thead>
          <tr><th>Metric Name</th><th>Threshold Target</th><th>Outcome</th></tr>
        </thead>
        <tbody>${thresholdRows.join('')}</tbody>
      </table>
    </div>
  </div>` : ''}

  <!-- Raw JSON Drawer -->
  <div class="section">
    <div class="section-title">
      <span>📄 Raw k6 Summary JSON</span>
      <button class="btn" style="font-size:0.75rem" onclick="toggleJson()">Toggle View</button>
    </div>
    <div id="jsonContainer" style="display:none" class="json-box">
      <pre>${rawJsonStr}</pre>
    </div>
  </div>

  <footer>
    TripSync Backend DevOps Audit Report · Generated by <strong>parseK6Summary.js</strong> · ${now}
  </footer>

</div>

<script>
  function toggleTheme() {
    const html = document.documentElement;
    const current = html.getAttribute('data-theme');
    html.setAttribute('data-theme', current === 'dark' ? 'light' : 'dark');
  }

  function filterTable() {
    const input = document.getElementById('searchInput').value.toLowerCase();
    const rows = document.querySelectorAll('#endpointTable tbody tr');
    rows.forEach(r => {
      const text = r.innerText.toLowerCase();
      r.style.display = text.includes(input) ? '' : 'none';
    });
  }

  function filterStatus(status) {
    const rows = document.querySelectorAll('#endpointTable tbody tr');
    rows.forEach(r => {
      if (status === 'all') r.style.display = '';
      else r.style.display = r.getAttribute('data-status') === status ? '' : 'none';
    });
  }

  function toggleJson() {
    const el = document.getElementById('jsonContainer');
    el.style.display = el.style.display === 'none' ? 'block' : 'none';
  }

  function downloadJson() {
    const blob = new Blob([JSON.stringify(${JSON.stringify(s.rawJson)}, null, 2)], { type: 'application/json' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = 'k6-summary.json';
    a.click();
    URL.revokeObjectURL(url);
  }
</script>
</body>
</html>`;
}

// ── Write outputs ─────────────────────────────────────────────────────────────
function writeOutputs(s) {
  const md   = buildMarkdown(s);
  const html = buildHtml(s);

  console.log(md);

  if (STEP_SUMMARY) {
    try {
      fs.appendFileSync(STEP_SUMMARY, md, 'utf8');
      console.log(`\n✅ Markdown report written to $GITHUB_STEP_SUMMARY`);
    } catch (e) {
      console.warn(`⚠️ Could not write to GITHUB_STEP_SUMMARY: ${e.message}`);
    }
  }

  try {
    fs.writeFileSync(HTML_OUT, html, 'utf8');
    console.log(`✅ Executive HTML report written to: ${HTML_OUT}`);
  } catch (e) {
    console.warn(`⚠️ Could not write HTML report: ${e.message}`);
  }
}

// ── Main ──────────────────────────────────────────────────────────────────────
(function main() {
  console.log(`📂 Reading k6 summary from: ${SUMMARY_PATH}\n`);
  try {
    const stats = parseSummary(SUMMARY_PATH);
    writeOutputs(stats);
    const exitCode = stats.overallPass ? 0 : 1;
    if (exitCode === 0) {
      console.log('\n✅ All k6 thresholds PASSED — overall result: PASSED.');
    } else {
      console.error('\n❌ One or more k6 thresholds FAILED — see table above.');
    }
    process.exit(exitCode);
  } catch (err) {
    console.error(`❌ Parser error: ${err.message}`);
    if (STEP_SUMMARY) {
      try { fs.appendFileSync(STEP_SUMMARY, `## ❌ k6 Summary Parser Error\n\n\`\`\`\n${err.message}\n\`\`\`\n`, 'utf8'); } catch (_) {}
    }
    process.exit(1);
  }
})();
