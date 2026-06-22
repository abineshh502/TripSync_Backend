/**
 * TripSync Backend – k6 Summary Parser + HTML Report Generator
 * ─────────────────────────────────────────────────────────────────────────────
 * Reads k6-summary.json, then:
 *   1. Writes a rich Markdown table to $GITHUB_STEP_SUMMARY
 *   2. Generates load-test-report.html for artifact download
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

// ── Paths ─────────────────────────────────────────────────────────────────────
const SUMMARY_PATH  = process.argv[2] ?? path.join(process.cwd(), 'k6-summary.json');
const HTML_OUT      = path.join(path.dirname(SUMMARY_PATH), 'load-test-report.html');
const STEP_SUMMARY  = process.env.GITHUB_STEP_SUMMARY;
const BUILD_NUMBER  = process.env.GITHUB_RUN_NUMBER  ?? 'local';
const COMMIT_SHA    = process.env.GITHUB_SHA         ?? 'local';
const REPO          = process.env.GITHUB_REPOSITORY  ?? 'TripSync_Backend';

// ── Defensive metric extractor ────────────────────────────────────────────────
/**
 * Extract a numeric value from a k6 metric object.
 * Safely handles nested { values: { key } } AND flat { key } schemas.
 *
 * @param {object|null|undefined} metricObj - Sub-object from k6 summary.json
 * @param {string}                key       - e.g. "avg", "p(95)", "rate", "count"
 * @param {number}                [fb=0]    - Fallback when key is absent
 * @returns {number}
 */
function getMetricValue(metricObj, key, fb = 0) {
  if (!metricObj || typeof metricObj !== 'object') return fb;

  // Strategy 1 – nested under .values (k6 ≥ v0.40, Trend / Gauge)
  if (metricObj.values && typeof metricObj.values === 'object') {
    const v = metricObj.values[key];
    if (v !== undefined) return typeof v === 'number' ? v : fb;
  }

  // Strategy 2 – flat (Counter / Rate metrics, older k6 versions)
  const v = metricObj[key];
  if (v !== undefined) return typeof v === 'number' ? v : fb;

  return fb;
}

// ── Formatting helpers ────────────────────────────────────────────────────────
const ms      = (v) => `${(+v || 0).toFixed(2)} ms`;
const pct     = (v) => `${((+v || 0) * 100).toFixed(2)}%`;
const rps     = (v) => `${(+v || 0).toFixed(2)} req/s`;
const integer = (v) => `${Math.round(+v || 0).toLocaleString()}`;
const light   = (pass) => pass ? '🟢 PASS' : '🔴 FAIL';
const emoji   = (pass) => pass ? '✅' : '❌';

// ── Parse k6-summary.json ─────────────────────────────────────────────────────
function parseSummary(filePath) {
  if (!fs.existsSync(filePath)) {
    throw new Error(`k6-summary.json not found at: ${filePath}`);
  }

  let raw;
  try {
    raw = JSON.parse(fs.readFileSync(filePath, 'utf8'));
  } catch (e) {
    throw new Error(`Failed to parse k6-summary.json: ${e.message}`);
  }

  const m = raw.metrics ?? {};

  // ── Latency ────────────────────────────────────────────────────────────────
  const dur  = m.http_req_duration ?? {};
  const avgMs  = getMetricValue(dur, 'avg');
  const minMs  = getMetricValue(dur, 'min');
  const maxMs  = getMetricValue(dur, 'max');
  const p95Ms  = getMetricValue(dur, 'p(95)');
  const medMs  = getMetricValue(dur, 'med');

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
  const checksM    = m.checks ?? {};
  const checkPasses = getMetricValue(checksM, 'passes', getMetricValue(checksM, 'count'));
  const checkFails  = getMetricValue(checksM, 'fails');
  const totalChecks = checkPasses + checkFails;
  const checkRate   = totalChecks > 0 ? (checkPasses / totalChecks) : getMetricValue(checksM, 'value');

  // ── Per-endpoint custom metrics ────────────────────────────────────────────
  const endpointStats = {
    'Health API':  extractTrend(m.health_api_duration),
    'Trips API':   extractTrend(m.trips_api_duration),
    'Safety API':  extractTrend(m.safety_api_duration),
    'Weather API': extractTrend(m.weather_api_duration),
  };

  // ── Threshold results ──────────────────────────────────────────────────────
  const thresholds = raw.thresholds ?? {};

  // ── Overall pass/fail — driven by ACTUAL k6 threshold results ─────────────
  // Do NOT use hardcoded latency comparisons — those caused parse step to fail
  // even when k6 passed all thresholds. Use the ok/passed field k6 writes.
  const thresholdEntries = Object.values(thresholds);
  const overallPass = thresholdEntries.length === 0
    ? (failRate < 0.05)
    : thresholdEntries.every((t) => t.ok === true || t.passed === true);

  return {
    overallPass, avgMs, minMs, medMs, maxMs, p95Ms,
    total, passCount, failCount, failRate, rpsVal,
    checkRate, checkPasses, checkFails,
    endpointStats, thresholds,
    buildNumber: BUILD_NUMBER,
    commitSha: COMMIT_SHA.substring(0, 7),
  };
}

/** Extract p95, avg, min, max from a named Trend metric (or return zeroes). */
function extractTrend(metricObj) {
  if (!metricObj) return { avg: 0, p95: 0, min: 0, max: 0, present: false };
  return {
    avg:     getMetricValue(metricObj, 'avg'),
    p95:     getMetricValue(metricObj, 'p(95)'),
    min:     getMetricValue(metricObj, 'min'),
    max:     getMetricValue(metricObj, 'max'),
    present: true,
  };
}

// ── GitHub Actions Step Summary (Markdown) ────────────────────────────────────
function buildMarkdown(s) {
  const now     = new Date().toUTCString();
  const overall = s.overallPass ? '✅ **PASSED**' : '❌ **FAILED**';

  // Threshold table
  const thresholdRows = Object.entries(s.thresholds).map(([name, info]) => {
    const ok = info.ok !== undefined ? info.ok : (info.passed ?? false);
    return `| \`${name}\` | ${info.threshold ?? '—'} | ${ok ? '🟢 PASS' : '🔴 FAIL'} |`;
  });

  // Per-endpoint rows
  const endpointRows = Object.entries(s.endpointStats).map(([name, stat]) => {
    if (!stat.present) return `| **${name}** | — | — | — |`;
    const slaMap = { 'Health API': 400, 'Root API': 600, 'Trips API': 600, 'Weather API': 2500, 'Safety API': 5000 };
    const pass = stat.p95 < (slaMap[name] ?? 3000);
    const p95Status = pass ? '🟢 PASS' : '🔴 FAIL';
    return `| **${name}** | ${ms(stat.avg)} | ${ms(stat.p95)} | ${p95Status} |`;
  });

  return `# 🚀 TripSync Backend Load Test Results

> **Overall Result:** ${overall}
> **Date:** ${now}
> **Build:** \`#${s.buildNumber}\` | **Commit:** \`${s.commitSha}\`
> **Repository:** \`${REPO}\`

---

## 📊 Request Summary

| Metric | Value |
|--------|-------|
| **Total Requests** | ${integer(s.total)} |
| **Successful Requests** | ${integer(s.passCount)} |
| **Failed Requests** | ${integer(s.failCount)} |
| **Throughput (RPS)** | ${rps(s.rpsVal)} |
| **Error Rate** | ${pct(s.failRate)} |

---

## ⏱️ Response Time Statistics

| Metric | Value | SLA |
|--------|-------|-----|
| **Average** | ${ms(s.avgMs)} | — |
| **Minimum** | ${ms(s.minMs)} | — |
| **Median (p50)** | ${ms(s.medMs)} | — |
| **P95** | ${ms(s.p95Ms)} | ${s.p95Ms < 5000 ? '🟢 PASS (<5000ms)' : '🔴 FAIL (≥5000ms)'} |
| **Maximum** | ${ms(s.maxMs)} | — |

---

## 🔍 Endpoint Status

| Endpoint | Avg Latency | P95 Latency | Status |
|----------|-------------|-------------|--------|
${endpointRows.join('\n')}

---

## ✅ Assertions

| Metric | Value |
|--------|-------|
| **Check Pass Rate** | ${pct(s.checkRate)} |
| **Checks Passed** | ${integer(s.checkPasses)} |
| **Checks Failed** | ${integer(s.checkFails)} |

---

${thresholdRows.length > 0 ? `## 📋 Threshold Results\n\n| Metric | Threshold | Status |\n|--------|-----------|--------|\n${thresholdRows.join('\n')}\n\n---\n\n` : ''}## ℹ️ Test Configuration

- **Virtual Users:** 100 VUs
- **Duration:** 1 minute
- **Thresholds:** \`http_req_failed < 5%\` | \`global p(95) < 5000ms\` | \`safety p(95) < 5000ms\`
- **Download Artifacts:** \`k6-summary.json\` and \`load-test-report.html\` are attached to this run.
`;
}

// ── HTML Report ───────────────────────────────────────────────────────────────
function buildHtml(s) {
  const now     = new Date().toUTCString();
  const bg      = s.overallPass ? '#0f2a1a' : '#2a0f0f';
  const badgeColor = s.overallPass ? '#22c55e' : '#ef4444';
  const badgeText  = s.overallPass ? 'PASSED' : 'FAILED';

  const endpointRows = Object.entries(s.endpointStats).map(([name, stat]) => {
    if (!stat.present) {
      return `<tr><td>${name}</td><td>—</td><td>—</td><td>—</td><td><span class="badge badge-skip">N/A</span></td></tr>`;
    }
    const slaMap = { 'Health API': 400, 'Root API': 600, 'Trips API': 600, 'Weather API': 2500, 'Safety API': 5000 };
    const pass = stat.p95 < (slaMap[name] ?? 3000);
    return `<tr>
      <td>${name}</td>
      <td>${stat.avg.toFixed(2)} ms</td>
      <td>${stat.min.toFixed(2)} ms</td>
      <td>${stat.p95.toFixed(2)} ms</td>
      <td><span class="badge ${pass ? 'badge-pass' : 'badge-fail'}">${pass ? 'PASS' : 'FAIL'}</span></td>
    </tr>`;
  });

  const thresholdRows = Object.entries(s.thresholds).map(([name, info]) => {
    const ok = info.ok !== undefined ? info.ok : (info.passed ?? false);
    return `<tr>
      <td><code>${name}</code></td>
      <td>${info.threshold ?? '—'}</td>
      <td><span class="badge ${ok ? 'badge-pass' : 'badge-fail'}">${ok ? 'PASS' : 'FAIL'}</span></td>
    </tr>`;
  });

  return `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>TripSync Backend Load Test Report</title>
  <style>
    *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
    :root {
      --bg: #0a0f1a;
      --surface: #111827;
      --surface2: #1f2937;
      --border: #374151;
      --text: #f3f4f6;
      --muted: #9ca3af;
      --green: #22c55e;
      --red: #ef4444;
      --yellow: #f59e0b;
      --blue: #38bdf8;
      --purple: #a78bfa;
    }
    body {
      background: var(--bg);
      color: var(--text);
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      line-height: 1.6;
      padding: 24px;
    }
    .container { max-width: 1100px; margin: 0 auto; }
    header {
      background: linear-gradient(135deg, #1e3a5f 0%, #0f172a 100%);
      border: 1px solid #1d4ed8;
      border-radius: 16px;
      padding: 32px;
      margin-bottom: 28px;
      position: relative;
      overflow: hidden;
    }
    header::before {
      content: '';
      position: absolute;
      top: -50%;
      left: -50%;
      width: 200%;
      height: 200%;
      background: radial-gradient(circle at 30% 50%, rgba(56, 189, 248, 0.06) 0%, transparent 60%);
      pointer-events: none;
    }
    .header-top { display: flex; justify-content: space-between; align-items: flex-start; flex-wrap: wrap; gap: 16px; }
    h1 { font-size: 1.8rem; font-weight: 700; color: var(--blue); }
    .badge {
      display: inline-block;
      padding: 4px 14px;
      border-radius: 999px;
      font-size: 0.8rem;
      font-weight: 700;
      letter-spacing: 0.05em;
      text-transform: uppercase;
    }
    .badge-pass  { background: rgba(34,197,94,0.15);  color: var(--green); border: 1px solid var(--green); }
    .badge-fail  { background: rgba(239,68,68,0.15);  color: var(--red);   border: 1px solid var(--red);   }
    .badge-skip  { background: rgba(156,163,175,0.15); color: var(--muted); border: 1px solid var(--border);}
    .badge-overall {
      padding: 8px 24px;
      font-size: 1rem;
      background: ${s.overallPass ? 'rgba(34,197,94,0.2)' : 'rgba(239,68,68,0.2)'};
      color: ${badgeColor};
      border: 2px solid ${badgeColor};
    }
    .meta { margin-top: 16px; display: flex; flex-wrap: wrap; gap: 24px; }
    .meta-item { display: flex; flex-direction: column; gap: 2px; }
    .meta-label { font-size: 0.72rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; }
    .meta-value { font-size: 0.9rem; font-weight: 600; color: var(--text); font-family: monospace; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; margin-bottom: 24px; }
    .card {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: 12px;
      padding: 20px;
      transition: border-color 0.2s;
    }
    .card:hover { border-color: var(--blue); }
    .card-label { font-size: 0.75rem; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 8px; }
    .card-value { font-size: 1.6rem; font-weight: 700; color: var(--blue); }
    .card-sub   { font-size: 0.78rem; color: var(--muted); margin-top: 4px; }
    .section { margin-bottom: 28px; }
    .section-title {
      font-size: 1rem;
      font-weight: 600;
      color: var(--muted);
      text-transform: uppercase;
      letter-spacing: 0.1em;
      margin-bottom: 14px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--border);
    }
    table { width: 100%; border-collapse: collapse; font-size: 0.9rem; }
    th {
      background: var(--surface2);
      color: var(--muted);
      text-align: left;
      padding: 10px 14px;
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      border-bottom: 1px solid var(--border);
    }
    td {
      padding: 12px 14px;
      border-bottom: 1px solid var(--border);
      color: var(--text);
    }
    tr:last-child td { border-bottom: none; }
    tr:hover td { background: rgba(255,255,255,0.02); }
    code { background: var(--surface2); padding: 2px 6px; border-radius: 4px; font-size: 0.82rem; color: var(--purple); }
    .pass-val { color: var(--green); font-weight: 600; }
    .fail-val  { color: var(--red);   font-weight: 600; }
    .footer {
      margin-top: 40px;
      padding: 16px;
      text-align: center;
      color: var(--muted);
      font-size: 0.78rem;
      border-top: 1px solid var(--border);
    }
  </style>
</head>
<body>
<div class="container">

  <!-- Header -->
  <header>
    <div class="header-top">
      <div>
        <div style="font-size:0.8rem; color:var(--muted); margin-bottom:6px;">TRIPSYNC BACKEND</div>
        <h1>⚡ Load Test Report</h1>
      </div>
      <span class="badge badge-overall">${badgeText}</span>
    </div>
    <div class="meta">
      <div class="meta-item"><span class="meta-label">Build</span><span class="meta-value">#${s.buildNumber}</span></div>
      <div class="meta-item"><span class="meta-label">Commit</span><span class="meta-value">${s.commitSha}</span></div>
      <div class="meta-item"><span class="meta-label">Date</span><span class="meta-value">${now}</span></div>
      <div class="meta-item"><span class="meta-label">Config</span><span class="meta-value">100 VUs · 1 min</span></div>
    </div>
  </header>

  <!-- KPI Cards -->
  <div class="grid">
    <div class="card">
      <div class="card-label">Total Requests</div>
      <div class="card-value">${integer(s.total)}</div>
      <div class="card-sub">${rps(s.rpsVal)}</div>
    </div>
    <div class="card">
      <div class="card-label">Successful</div>
      <div class="card-value" style="color:var(--green)">${integer(s.passCount)}</div>
      <div class="card-sub">${pct(1 - s.failRate)} success rate</div>
    </div>
    <div class="card">
      <div class="card-label">Failed</div>
      <div class="card-value" style="color:${s.failCount > 0 ? 'var(--red)' : 'var(--green)'}">${integer(s.failCount)}</div>
      <div class="card-sub">Error rate: ${pct(s.failRate)}</div>
    </div>
    <div class="card">
      <div class="card-label">Avg Response Time</div>
      <div class="card-value">${s.avgMs.toFixed(0)}<span style="font-size:0.9rem;font-weight:400"> ms</span></div>
      <div class="card-sub">Median: ${s.medMs.toFixed(0)} ms</div>
    </div>
    <div class="card">
      <div class="card-label">P95 Latency</div>
      <div class="card-value" style="color:${s.p95Ms < 5000 ? 'var(--green)' : 'var(--red)'}">${s.p95Ms.toFixed(0)}<span style="font-size:0.9rem;font-weight:400"> ms</span></div>
      <div class="card-sub">SLA: &lt; 5000 ms (mixed workload)</div>
    </div>
    <div class="card">
      <div class="card-label">Check Pass Rate</div>
      <div class="card-value">${(s.checkRate * 100).toFixed(1)}<span style="font-size:0.9rem;font-weight:400">%</span></div>
      <div class="card-sub">${integer(s.checkPasses)} passed / ${integer(s.checkFails)} failed</div>
    </div>
  </div>

  <!-- Endpoint Status -->
  <div class="section">
    <div class="section-title">🔍 Endpoint Status</div>
    <table>
      <thead><tr><th>Endpoint</th><th>Avg Latency</th><th>Min Latency</th><th>P95 Latency</th><th>Status</th></tr></thead>
      <tbody>${endpointRows.join('')}</tbody>
    </table>
  </div>

  <!-- Latency Table -->
  <div class="section">
    <div class="section-title">⏱ Response Time Distribution</div>
    <table>
      <thead><tr><th>Percentile / Stat</th><th>Value</th><th>SLA Threshold</th><th>Status</th></tr></thead>
      <tbody>
        <tr><td>Average</td><td>${ms(s.avgMs)}</td><td>—</td><td>—</td></tr>
        <tr><td>Minimum</td><td>${ms(s.minMs)}</td><td>—</td><td>—</td></tr>
        <tr><td>Median (p50)</td><td>${ms(s.medMs)}</td><td>—</td><td>—</td></tr>
        <tr>
          <td>P95</td>
          <td class="${s.p95Ms < 5000 ? 'pass-val' : 'fail-val'}">${ms(s.p95Ms)}</td>
          <td>&lt; 5000 ms (mixed SLA)</td>
          <td><span class="badge ${s.p95Ms < 5000 ? 'badge-pass' : 'badge-fail'}">${s.p95Ms < 5000 ? 'PASS' : 'FAIL'}</span></td>
        </tr>
        <tr><td>Maximum</td><td>${ms(s.maxMs)}</td><td>—</td><td>—</td></tr>
      </tbody>
    </table>
  </div>

  <!-- Threshold Results -->
  ${thresholdRows.length > 0 ? `
  <div class="section">
    <div class="section-title">📋 Threshold Results</div>
    <table>
      <thead><tr><th>Metric</th><th>Threshold</th><th>Result</th></tr></thead>
      <tbody>${thresholdRows.join('')}</tbody>
    </table>
  </div>` : ''}

  <div class="footer">
    Generated by <strong>parseK6Summary.js</strong> · TripSync Backend CI · ${now}
  </div>
</div>
</body>
</html>`;
}

// ── Write outputs ─────────────────────────────────────────────────────────────
function writeOutputs(s) {
  const md   = buildMarkdown(s);
  const html = buildHtml(s);

  // ── 1. Stdout (always visible in GHA logs)
  console.log(md);

  // ── 2. GitHub Step Summary
  if (STEP_SUMMARY) {
    try {
      fs.appendFileSync(STEP_SUMMARY, md, 'utf8');
      console.log(`\n✅ Markdown report written to $GITHUB_STEP_SUMMARY`);
    } catch (e) {
      console.warn(`⚠️  Could not write to GITHUB_STEP_SUMMARY: ${e.message}`);
    }
  } else {
    console.warn('ℹ️  GITHUB_STEP_SUMMARY not set (running locally — stdout only).');
  }

  // ── 3. HTML Report (artifact)
  try {
    fs.writeFileSync(HTML_OUT, html, 'utf8');
    console.log(`✅ HTML report written to: ${HTML_OUT}`);
  } catch (e) {
    console.warn(`⚠️  Could not write HTML report: ${e.message}`);
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
    const errMd = `## ❌ k6 Summary Parser Error\n\n\`\`\`\n${err.message}\n\`\`\`\n`;
    console.error(err.message);
    if (STEP_SUMMARY) {
      try { fs.appendFileSync(STEP_SUMMARY, errMd, 'utf8'); } catch (_) {}
    }
    process.exit(1);
  }
})();
