#!/usr/bin/env node
/**
 * TripSync Backend Security Suite Generator
 * ==========================================
 * Orchestrates backend SAST and generates all output reports:
 *   - findings.xlsx (4 sheets)
 *   - endpoint-inventory.md
 *   - dependency-report.md
 *   - security-review.md
 *   - executive-summary.md
 *
 * Author: TripSync Security Team
 * Version: 1.0.0
 */

"use strict";

const fs = require("fs");
const path = require("path");
const { execSync } = require("child_process");

const REPORT_DIR = path.resolve(__dirname, "../reports");
const ROOT_DIR = path.resolve(__dirname, "../../");

// ─── Dependency Check ─────────────────────────────────────────────────────────
function ensureDependency(pkgName) {
  try {
    require.resolve(pkgName);
    return true;
  } catch {
    console.log(`  Installing ${pkgName}...`);
    // Try to install in the TripSyncWeb node_modules (shared)
    const webRoot = path.resolve(ROOT_DIR, "../TripSyncWeb");
    try {
      execSync(`npm install ${pkgName} --no-save --prefix "${webRoot}"`, {
        stdio: "pipe",
        timeout: 60000,
      });
      // Add web node_modules to resolution path
      process.env.NODE_PATH = path.join(webRoot, "node_modules");
      require("module").Module._initPaths();
      return true;
    } catch {
      // Try local node_modules
      try {
        execSync(`npm install ${pkgName} --no-save`, {
          cwd: ROOT_DIR,
          stdio: "pipe",
          timeout: 60000,
        });
        return true;
      } catch (err2) {
        console.warn(`  ⚠️  Could not install ${pkgName}: ${err2.message}`);
        return false;
      }
    }
  }
}

// ─── XLSX Generation ──────────────────────────────────────────────────────────
function generateXLSX(scanData) {
  const xlsxAvailable = ensureDependency("xlsx");

  if (!xlsxAvailable) {
    console.warn("  ⚠️  xlsx package not available. Skipping Excel report.");
    return false;
  }

  const XLSX = require("xlsx");
  const { findings, endpoints, depFindings } = scanData;

  const wb = XLSX.utils.book_new();

  // Header styling
  const mkHeader = (color) => ({
    font: { bold: true, color: { rgb: "FFFFFF" } },
    fill: { fgColor: { rgb: color } },
    alignment: { horizontal: "center", vertical: "center", wrapText: true },
  });

  const cellStyle = (row, sev) => {
    const sevColors = { CRITICAL: "FADBD8", HIGH: "FDEBD0", MEDIUM: "FEF9E7", LOW: "EAFAF1", INFO: "EBF5FB" };
    return {
      fill: { fgColor: { rgb: sevColors[sev] || (row % 2 === 0 ? "F8F9FA" : "FFFFFF") } },
      alignment: { wrapText: true, vertical: "top" },
    };
  };

  // ── Sheet 1: Security Findings ──────────────────────────────────────────────
  const s1Headers = [
    "Finding ID", "Severity", "Category", "File", "Function", "Line",
    "Description", "Root Cause", "Impact", "Recommendation", "CWE", "OWASP", "Evidence"
  ];
  const s1Data = [s1Headers, ...findings.map(f => [
    f.id, f.severity, f.category, f.file, f.function, f.line,
    f.description, f.rootCause, f.impact, f.recommendation, f.cwe, f.owasp, f.evidence || ""
  ])];

  const ws1 = XLSX.utils.aoa_to_sheet(s1Data);
  ws1["!cols"] = [
    { wch: 12 }, { wch: 10 }, { wch: 35 }, { wch: 45 }, { wch: 25 }, { wch: 6 },
    { wch: 60 }, { wch: 55 }, { wch: 55 }, { wch: 55 }, { wch: 12 }, { wch: 35 }, { wch: 40 }
  ];

  s1Headers.forEach((_, c) => {
    const ref = XLSX.utils.encode_cell({ r: 0, c });
    if (ws1[ref]) ws1[ref].s = mkHeader("1A237E");
  });

  const sevBgColors = { CRITICAL: "C0392B", HIGH: "E67E22", MEDIUM: "F39C12", LOW: "27AE60", INFO: "2980B9" };
  findings.forEach((f, i) => {
    const r = i + 1;
    s1Headers.forEach((_, c) => {
      const ref = XLSX.utils.encode_cell({ r, c });
      if (!ws1[ref]) return;
      if (c === 1) {
        ws1[ref].s = {
          font: { bold: true, color: { rgb: "FFFFFF" } },
          fill: { fgColor: { rgb: sevBgColors[f.severity] || "808080" } },
          alignment: { horizontal: "center" },
        };
      } else {
        ws1[ref].s = cellStyle(r, f.severity);
      }
    });
  });

  XLSX.utils.book_append_sheet(wb, ws1, "Security Findings");

  // ── Sheet 2: Endpoint Inventory ─────────────────────────────────────────────
  const s2Headers = [
    "HTTP Method", "Route", "Function", "File", "Line",
    "Has Auth", "Has JWT", "Input Validation", "Rate Limit", "Notes"
  ];
  const s2Data = [
    s2Headers,
    ...endpoints.map(ep => [
      ep.method, ep.route, ep.function, ep.file, ep.line,
      ep.hasAuth ? "YES" : "NO",
      ep.hasJWT ? "YES" : "NO",
      ep.hasInputValidation ? "YES" : "PARTIAL",
      ep.hasRateLimit ? "YES" : "NO",
      ep.notes,
    ])
  ];

  const ws2 = XLSX.utils.aoa_to_sheet(s2Data);
  ws2["!cols"] = [{ wch: 10 }, { wch: 35 }, { wch: 25 }, { wch: 45 }, { wch: 6 },
    { wch: 10 }, { wch: 10 }, { wch: 18 }, { wch: 12 }, { wch: 50 }];

  s2Headers.forEach((_, c) => {
    const ref = XLSX.utils.encode_cell({ r: 0, c });
    if (ws2[ref]) ws2[ref].s = mkHeader("1B5E20");
  });

  // Color auth status
  endpoints.forEach((ep, i) => {
    const r = i + 1;
    const authRef = XLSX.utils.encode_cell({ r, c: 5 });
    if (ws2[authRef]) {
      ws2[authRef].s = {
        font: { bold: true, color: { rgb: "FFFFFF" } },
        fill: { fgColor: { rgb: ep.hasAuth ? "1B5E20" : "B71C1C" } },
        alignment: { horizontal: "center" },
      };
    }
    const rlRef = XLSX.utils.encode_cell({ r, c: 8 });
    if (ws2[rlRef]) {
      ws2[rlRef].s = {
        font: { bold: true, color: { rgb: "FFFFFF" } },
        fill: { fgColor: { rgb: ep.hasRateLimit ? "1B5E20" : "B71C1C" } },
        alignment: { horizontal: "center" },
      };
    }
  });

  XLSX.utils.book_append_sheet(wb, ws2, "Endpoint Inventory");

  // ── Sheet 3: Dependency Vulnerabilities ─────────────────────────────────────
  const s3Headers = ["Package", "Installed Version", "Latest Version", "Severity", "Description", "Recommendation", "CVE"];
  const s3Data = [
    s3Headers,
    ...(depFindings || []).map(d => [
      d.package, d.installedVersion, d.latestVersion,
      d.severity, d.description, d.recommendation, d.cve || ""
    ])
  ];

  const ws3 = XLSX.utils.aoa_to_sheet(s3Data);
  ws3["!cols"] = [{ wch: 25 }, { wch: 20 }, { wch: 15 }, { wch: 12 }, { wch: 60 }, { wch: 55 }, { wch: 20 }];

  s3Headers.forEach((_, c) => {
    const ref = XLSX.utils.encode_cell({ r: 0, c });
    if (ws3[ref]) ws3[ref].s = mkHeader("4A148C");
  });

  XLSX.utils.book_append_sheet(wb, ws3, "Dependency Vulnerabilities");

  // ── Sheet 4: Risk Summary ────────────────────────────────────────────────────
  const bySeverity = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0, INFO: 0 };
  const byCategory = {};
  for (const f of findings) {
    bySeverity[f.severity] = (bySeverity[f.severity] || 0) + 1;
    const cat = f.category.split("/")[0].trim();
    byCategory[cat] = (byCategory[cat] || 0) + 1;
  }
  const riskScore = bySeverity.CRITICAL * 10 + bySeverity.HIGH * 7 + bySeverity.MEDIUM * 4 + bySeverity.LOW;
  const riskLevel = riskScore > 50 ? "HIGH RISK" : riskScore > 20 ? "MEDIUM RISK" : "LOW RISK";

  const endpointStats = {
    total: endpoints.length,
    withAuth: endpoints.filter(e => e.hasAuth).length,
    withoutAuth: endpoints.filter(e => !e.hasAuth).length,
    withRateLimit: endpoints.filter(e => e.hasRateLimit).length,
    withInputVal: endpoints.filter(e => e.hasInputValidation).length,
  };

  const s4Data = [
    ["TripSync Backend — Security Risk Summary"],
    [""],
    ["Generated", new Date().toISOString()],
    ["Framework", "FastAPI (Python)"],
    ["Scanner", "TripSync Backend SAST v1.0.0"],
    [""],
    ["SEVERITY BREAKDOWN"],
    ["Severity", "Count", "Risk Weight", "Score Contribution"],
    ["CRITICAL", bySeverity.CRITICAL, 10, bySeverity.CRITICAL * 10],
    ["HIGH", bySeverity.HIGH, 7, bySeverity.HIGH * 7],
    ["MEDIUM", bySeverity.MEDIUM, 4, bySeverity.MEDIUM * 4],
    ["LOW", bySeverity.LOW, 1, bySeverity.LOW],
    ["INFO", bySeverity.INFO, 0, 0],
    ["TOTAL FINDINGS", findings.length, "", riskScore],
    [""],
    ["Overall Risk Level", riskLevel],
    ["Risk Score", `${riskScore}/100`],
    [""],
    ["ENDPOINT SECURITY"],
    ["Metric", "Count", "Percentage"],
    ["Total Endpoints", endpointStats.total, "100%"],
    ["With Authentication", endpointStats.withAuth, `${Math.round(endpointStats.withAuth / endpointStats.total * 100)}%`],
    ["Without Authentication", endpointStats.withoutAuth, `${Math.round(endpointStats.withoutAuth / endpointStats.total * 100)}%`],
    ["With Rate Limiting", endpointStats.withRateLimit, `${Math.round(endpointStats.withRateLimit / endpointStats.total * 100)}%`],
    ["With Input Validation", endpointStats.withInputVal, `${Math.round(endpointStats.withInputVal / endpointStats.total * 100)}%`],
    [""],
    ["FINDINGS BY CATEGORY"],
    ["Category", "Count"],
    ...Object.entries(byCategory).sort((a, b) => b[1] - a[1]).map(([cat, count]) => [cat, count]),
  ];

  const ws4 = XLSX.utils.aoa_to_sheet(s4Data);
  ws4["!cols"] = [{ wch: 35 }, { wch: 15 }, { wch: 15 }, { wch: 20 }];

  const titleCell = ws4["A1"];
  if (titleCell) titleCell.s = { font: { bold: true, sz: 14, color: { rgb: "FFFFFF" } }, fill: { fgColor: { rgb: "1A237E" } }, alignment: { horizontal: "center" } };

  XLSX.utils.book_append_sheet(wb, ws4, "Risk Summary");

  const xlsxPath = path.join(REPORT_DIR, "findings.xlsx");
  XLSX.writeFile(wb, xlsxPath);
  console.log(`  ✅ Excel report: ${xlsxPath}`);
  return true;
}

// ─── Main Orchestrator ────────────────────────────────────────────────────────
async function main() {
  console.log("\n╔══════════════════════════════════════════════════════════════╗");
  console.log("║   TripSync Backend Security Suite Generator v1.0.0          ║");
  console.log("╚══════════════════════════════════════════════════════════════╝\n");

  if (!fs.existsSync(REPORT_DIR)) {
    fs.mkdirSync(REPORT_DIR, { recursive: true });
  }

  console.log("STEP 1: Running Backend SAST Scanner...\n");
  const scanner = require("./backendScanner");
  const scanData = await scanner.main();

  let loadedData = scanData;
  const resultsPath = path.join(REPORT_DIR, "scan-results.json");
  if (!loadedData && fs.existsSync(resultsPath)) {
    loadedData = JSON.parse(fs.readFileSync(resultsPath, "utf8"));
  }

  if (!loadedData) {
    console.error("❌ No scan data available.");
    process.exit(1);
  }

  console.log("\nSTEP 2: Generating Excel Report...");
  generateXLSX(loadedData);

  console.log("\n╔══════════════════════════════════════════════════════════════╗");
  console.log("║              BACKEND SUITE GENERATION COMPLETE              ║");
  console.log("╠══════════════════════════════════════════════════════════════╣");
  console.log("║  Reports generated in backend/SecurityTest/reports/:        ║");
  console.log("║  ✅  findings.xlsx             (4 sheets)                   ║");
  console.log("║  ✅  endpoint-inventory.md                                  ║");
  console.log("║  ✅  dependency-report.md                                   ║");
  console.log("║  ✅  security-review.md                                     ║");
  console.log("║  ✅  executive-summary.md                                   ║");
  console.log("║  ✅  scan-results.json          (raw data)                  ║");
  console.log("╚══════════════════════════════════════════════════════════════╝\n");
}

main().catch(err => {
  console.error("Suite generator error:", err);
  process.exit(1);
});
