#!/usr/bin/env python3
"""
TripSync Backend Load Test Report Generator
─────────────────────────────────────────────────────────────────────────────
Parses k6-summary.json and raw k6-results.ndjson to output a professional,
multi-sheet Excel report (TripSync_Backend_LoadTest_Report.xlsx).
Matches the QA formatting style of the Selenium Web Testing report.
"""

import os
import sys
import json
from datetime import datetime
import pandas as pd

# Openpyxl styling imports
from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
from openpyxl.utils import get_column_letter

# Styles definition
FONT_NAME = "Segoe UI"
FONT_NORMAL = Font(name=FONT_NAME, size=10)
FONT_BOLD = Font(name=FONT_NAME, size=10, bold=True)
FONT_HEADER = Font(name=FONT_NAME, size=11, bold=True, color="FFFFFF")
FONT_TITLE = Font(name=FONT_NAME, size=16, bold=True, color="FFFFFF")

FILL_HEADER = PatternFill(start_color="1F4E78", end_color="1F4E78", fill_type="solid") # Steel Blue
FILL_TITLE = PatternFill(start_color="0F2942", end_color="0F2942", fill_type="solid") # Dark Navy
FILL_ZEBRA = PatternFill(start_color="F2F6FA", end_color="F2F6FA", fill_type="solid") # Off-white/Ice Blue
FILL_PASS = PatternFill(start_color="C6EFCE", end_color="C6EFCE", fill_type="solid") # Light Green
FONT_PASS = Font(name=FONT_NAME, size=10, color="006100", bold=True)
FILL_FAIL = PatternFill(start_color="FFC7CE", end_color="FFC7CE", fill_type="solid") # Light Red
FONT_FAIL = Font(name=FONT_NAME, size=10, color="9C0006", bold=True)
FILL_INFO = PatternFill(start_color="FFF2CC", end_color="FFF2CC", fill_type="solid") # Light Yellow
FONT_INFO = Font(name=FONT_NAME, size=10, color="7F6000", bold=True)

BORDER_THIN = Border(
    left=Side(style='thin', color='D9D9D9'),
    right=Side(style='thin', color='D9D9D9'),
    top=Side(style='thin', color='D9D9D9'),
    bottom=Side(style='thin', color='D9D9D9')
)

ALIGN_LEFT = Alignment(horizontal='left', vertical='center')
ALIGN_CENTER = Alignment(horizontal='center', vertical='center')
ALIGN_RIGHT = Alignment(horizontal='right', vertical='center')


def apply_auto_width_and_borders(ws):
    """Automatically adjusts column widths and applies thin borders to data cells."""
    for col in ws.columns:
        max_len = 0
        col_letter = get_column_letter(col[0].column)
        for cell in col:
            # Check length of string value
            val = str(cell.value or '')
            if '\n' in val:
                val = max(val.split('\n'), key=len)
            max_len = max(max_len, len(val))
            
            # Apply default font if none is set
            if cell.font.name != FONT_NAME:
                cell.font = FONT_NORMAL
                
            # Apply border to all non-title cells
            if cell.row > 1:
                cell.border = BORDER_THIN
                
        # Set adjusted width
        ws.column_dimensions[col_letter].width = max(max_len + 3, 12)


def style_header(ws, start_row=1):
    """Styles the header row with background fill, bold white font, and center alignment."""
    for col in range(1, ws.max_column + 1):
        cell = ws.cell(row=start_row, column=col)
        cell.font = FONT_HEADER
        cell.fill = FILL_HEADER
        cell.alignment = ALIGN_CENTER
        cell.border = BORDER_THIN
    ws.row_dimensions[start_row].height = 25


def style_title_block(ws, title_text, subtitle_text):
    """Creates a beautiful header banner block at the top of the worksheet."""
    # Insert 2 rows at the beginning
    ws.insert_rows(1, 2)
    
    # Merge cells for title
    max_col = max(ws.max_column, 4)
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=max_col)
    ws.merge_cells(start_row=2, start_column=1, end_row=2, end_column=max_col)
    
    # Set values
    cell_title = ws.cell(row=1, column=1, value=title_text)
    cell_sub = ws.cell(row=2, column=1, value=subtitle_text)
    
    # Style title
    cell_title.font = FONT_TITLE
    cell_title.fill = FILL_TITLE
    cell_title.alignment = Alignment(horizontal='left', vertical='center', indent=1)
    
    # Style subtitle
    cell_sub.font = Font(name=FONT_NAME, size=10, italic=True, color="D9D9D9")
    cell_sub.fill = FILL_TITLE
    cell_sub.alignment = Alignment(horizontal='left', vertical='center', indent=1)
    
    # Set heights
    ws.row_dimensions[1].height = 35
    ws.row_dimensions[2].height = 20


def color_status_cells(ws, col_index, pass_value="PASS", fail_value="FAIL"):
    """Finds cells in the given column and applies green pass / red fail fills."""
    for row in range(2, ws.max_row + 1):
        cell = ws.cell(row=row, column=col_index)
        val = str(cell.value).strip()
        if val == pass_value or "🟢" in val:
            cell.fill = FILL_PASS
            cell.font = FONT_PASS
            cell.alignment = ALIGN_CENTER
        elif val == fail_value or "🔴" in val:
            cell.fill = FILL_FAIL
            cell.font = FONT_FAIL
            cell.alignment = ALIGN_CENTER


def parse_k6_summary(summary_path):
    """Parses aggregated metric statistics from k6-summary.json."""
    if not os.path.exists(summary_path):
        print(f"[WARNING] Summary file not found at: {summary_path}")
        return {}

    with open(summary_path, 'r', encoding='utf-8') as f:
        raw = json.load(f)
    
    metrics = raw.get("metrics", {})
    
    # Helper to extract value safely
    def get_val(metric_obj, key):
        if not metric_obj:
            return 0.0
        if "values" in metric_obj and isinstance(metric_obj["values"], dict):
            return metric_obj["values"].get(key, 0.0)
        return metric_obj.get(key, 0.0)

    dur = metrics.get("http_req_duration", {})
    reqs = metrics.get("http_reqs", {})
    failed = metrics.get("http_req_failed", {})
    checks = metrics.get("checks", {})
    
    total = get_val(reqs, "count")
    fail_rate = get_val(failed, "rate")
    fail_count = int(total * fail_rate)
    success_count = int(total - fail_count)
    
    check_passes = get_val(checks, "passes")
    check_fails = get_val(checks, "fails")
    total_checks = check_passes + check_fails
    check_rate = (check_passes / total_checks) if total_checks > 0 else get_val(checks, "value")

    return {
        "total_requests": int(total),
        "success_requests": success_count,
        "failed_requests": fail_count,
        "error_rate": fail_rate,
        "avg_duration": get_val(dur, "avg"),
        "min_duration": get_val(dur, "min"),
        "med_duration": get_val(dur, "med"),
        "p95_duration": get_val(dur, "p(95)"),
        "p99_duration": get_val(dur, "p(99)"),
        "max_duration": get_val(dur, "max"),
        "rps": get_val(reqs, "rate"),
        "check_rate": check_rate,
        "checks_passed": int(check_passes),
        "checks_failed": int(check_fails),
        "raw_thresholds": raw.get("thresholds", {})
    }


def parse_k6_results(ndjson_path):
    """Parses individual request transaction points from raw results JSON Lines file."""
    requests = []
    if not os.path.exists(ndjson_path):
        print(f"[WARNING] Raw results file not found at: {ndjson_path}")
        return requests

    with open(ndjson_path, 'r', encoding='utf-8') as f:
        for idx, line in enumerate(f):
            try:
                data = json.loads(line)
                if data.get("type") == "Point" and data.get("metric") == "http_req_duration":
                    pt = data.get("data", {})
                    tags = pt.get("tags", {})
                    group = tags.get("group", "")
                    
                    if group.startswith("::"):
                        group = group[2:]
                    elif not group:
                        group = "Root API"
                    
                    status = tags.get("status", "0")
                    duration = pt.get("value", 0.0)
                    timestamp = pt.get("time", "")
                    method = tags.get("method", "GET")
                    
                    # Success criteria matching load-test.js
                    if group == "Safety API":
                        success = status in ["200", "503"]
                    else:
                        success = status == "200"
                        
                    requests.append({
                        "Request ID": f"REQ_{idx+1:05d}",
                        "Timestamp": timestamp,
                        "API Group": group,
                        "Method": method,
                        "Duration (ms)": duration,
                        "Status Code": status,
                        "Result": "PASS" if success else "FAIL"
                    })
            except Exception:
                continue
    return requests


def main():
    summary_file = sys.argv[1] if len(sys.argv) > 1 else "k6-summary.json"
    results_file = sys.argv[2] if len(sys.argv) > 2 else "k6-results.ndjson"
    output_excel = sys.argv[3] if len(sys.argv) > 3 else "TripSync_Backend_LoadTest_Report.xlsx"

    print(f"[INFO] Generating Excel report from {summary_file} and {results_file} ...")
    
    # 1. Parse JSON files
    sum_data = parse_k6_summary(summary_file)
    requests = parse_k6_results(results_file)
    
    # Check fallback if raw results is empty
    df_req = pd.DataFrame(requests)
    if df_req.empty:
        print("[WARNING] Raw request log is empty. Standardizing fallback placeholders.")
        df_req = pd.DataFrame(columns=["Request ID", "Timestamp", "API Group", "Method", "Duration (ms)", "Status Code", "Result"])

    # Extract build & metadata
    build_num = os.environ.get("GITHUB_RUN_NUMBER", "Local")
    commit_sha = os.environ.get("GITHUB_SHA", "Local")[:7]
    exec_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Target SLAs per group
    sla_limits = {
        "Health API": 400.0,
        "Root API": 600.0,
        "Trips API": 600.0,
        "Weather API": 2500.0,
        "Safety API": 5000.0
    }

    # Helper to calculate stats per group
    def calculate_group_stats(group_name):
        if df_req.empty:
            return [0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, "N/A"]
        
        grp = df_req[df_req["API Group"] == group_name]
        if grp.empty:
            return [0, 0, 0, 0.0, 0.0, 0.0, 0.0, 0.0, "N/A"]
        
        total = len(grp)
        passed = sum(grp["Result"] == "PASS")
        failed = total - passed
        avg_t = grp["Duration (ms)"].mean()
        min_t = grp["Duration (ms)"].min()
        max_t = grp["Duration (ms)"].max()
        p95 = grp["Duration (ms)"].quantile(0.95)
        p99 = grp["Duration (ms)"].quantile(0.99)
        
        limit = sla_limits.get(group_name, 3000.0)
        sla_pass = "🟢 PASS" if p95 < limit else "🔴 FAIL"
        
        return [
            total, passed, failed,
            round(avg_t, 2), round(min_t, 2), round(max_t, 2),
            round(p95, 2), round(p99, 2),
            sla_pass
        ]

    # Initialize Excel writer
    with pd.ExcelWriter(output_excel, engine="openpyxl") as writer:
        
        # ─────────────────────────────────────────────────────────────────────
        # SHEET 1: Executive Summary
        # ─────────────────────────────────────────────────────────────────────
        summary_rows = [
            ("Total Requests", sum_data.get("total_requests", len(requests)), "count"),
            ("Successful Requests", sum_data.get("success_requests", sum(1 for r in requests if r["Result"] == "PASS")), "count"),
            ("Failed Requests", sum_data.get("failed_requests", sum(1 for r in requests if r["Result"] == "FAIL")), "count"),
            ("Error Rate", f"{sum_data.get('error_rate', 0.0) * 100:.2f}%", "< 5% SLA"),
            ("Average Response Time", f"{sum_data.get('avg_duration', 0.0):.2f} ms", "—"),
            ("P95 Response Time", f"{sum_data.get('p95_duration', 0.0):.2f} ms", "< 5000 ms Mixed SLA"),
            ("P99 Response Time", f"{sum_data.get('p99_duration', 0.0):.2f} ms", "—"),
            ("Throughput", f"{sum_data.get('rps', 0.0):.2f} RPS", "Requests/sec"),
            ("Build Number", f"#{build_num}", "GitHub Actions Run"),
            ("Commit SHA", commit_sha, "Git Code Ref"),
            ("Execution Date", exec_date, "UTC Timestamp")
        ]
        df_exec = pd.DataFrame(summary_rows, columns=["Metric Description", "Value", "Reference / Target SLA"])
        df_exec.to_excel(writer, sheet_name="Executive Summary", index=False)

        # ─────────────────────────────────────────────────────────────────────
        # SHEET 2 - 5: API Endpoint Sheets
        # ─────────────────────────────────────────────────────────────────────
        api_sheets = ["Health API", "Trips API", "Safety API", "Weather API"]
        for api in api_sheets:
            stats = calculate_group_stats(api)
            api_rows = [
                ("Request Count", stats[0]),
                ("Success Count", stats[1]),
                ("Failure Count", stats[2]),
                ("Avg Response Time (ms)", stats[3]),
                ("Min Response Time (ms)", stats[4]),
                ("Max Response Time (ms)", stats[5]),
                ("P95 Latency (ms)", stats[6]),
                ("P99 Latency (ms)", stats[7]),
                ("SLA Status", stats[8]),
                ("SLA Target Budget (ms)", sla_limits.get(api))
            ]
            df_api = pd.DataFrame(api_rows, columns=["Metric", "Value"])
            df_api.to_excel(writer, sheet_name=api, index=False)

        # ─────────────────────────────────────────────────────────────────────
        # SHEET 6: Performance Metrics
        # ─────────────────────────────────────────────────────────────────────
        perf_rows = []
        groups = ["Health API", "Root API", "Trips API", "Weather API", "Safety API"]
        for g in groups:
            if not df_req.empty:
                grp = df_req[df_req["API Group"] == g]
                if not grp.empty:
                    perf_rows.append({
                        "API Endpoint": g,
                        "Count": len(grp),
                        "Avg (ms)": round(grp["Duration (ms)"].mean(), 2),
                        "Min (ms)": round(grp["Duration (ms)"].min(), 2),
                        "Median (ms)": round(grp["Duration (ms)"].median(), 2),
                        "P90 (ms)": round(grp["Duration (ms)"].quantile(0.90), 2),
                        "P95 (ms)": round(grp["Duration (ms)"].quantile(0.95), 2),
                        "P99 (ms)": round(grp["Duration (ms)"].quantile(0.99), 2),
                        "Max (ms)": round(grp["Duration (ms)"].max(), 2)
                    })
        # Add global row if possible
        if not df_req.empty:
            perf_rows.append({
                "API Endpoint": "GLOBAL SYSTEM",
                "Count": len(df_req),
                "Avg (ms)": round(df_req["Duration (ms)"].mean(), 2),
                "Min (ms)": round(df_req["Duration (ms)"].min(), 2),
                "Median (ms)": round(df_req["Duration (ms)"].median(), 2),
                "P90 (ms)": round(df_req["Duration (ms)"].quantile(0.90), 2),
                "P95 (ms)": round(df_req["Duration (ms)"].quantile(0.95), 2),
                "P99 (ms)": round(df_req["Duration (ms)"].quantile(0.99), 2),
                "Max (ms)": round(df_req["Duration (ms)"].max(), 2)
            })
        df_perf = pd.DataFrame(perf_rows)
        if df_perf.empty:
            df_perf = pd.DataFrame(columns=["API Endpoint", "Count", "Avg (ms)", "Min (ms)", "Median (ms)", "P90 (ms)", "P95 (ms)", "P99 (ms)", "Max (ms)"])
        df_perf.to_excel(writer, sheet_name="Performance Metrics", index=False)

        # ─────────────────────────────────────────────────────────────────────
        # SHEET 7: SLA Validation
        # ─────────────────────────────────────────────────────────────────────
        sla_rows = []
        global_err = sum_data.get("error_rate", 0.0)
        global_p95 = sum_data.get("p95_duration", 0.0)
        
        sla_rows.append(("GLOBAL SYSTEM", "Error Rate", "< 5.0%", f"{global_err*100:.2f}%", "🟢 PASS" if global_err < 0.05 else "🔴 FAIL"))
        sla_rows.append(("GLOBAL SYSTEM", "P95 Response Time", "< 5000 ms", f"{global_p95:.2f} ms", "🟢 PASS" if global_p95 < 5000.0 else "🔴 FAIL"))
        
        for name, limit in sla_limits.items():
            stats = calculate_group_stats(name)
            p95_val = stats[6]
            status = "🟢 PASS" if p95_val < limit else "🔴 FAIL"
            if stats[0] > 0: # only append if run
                sla_rows.append((name, "P95 Response Time", f"< {limit} ms", f"{p95_val:.2f} ms", status))

        df_sla = pd.DataFrame(sla_rows, columns=["Scope", "Target Metric", "SLA Threshold", "Actual Value", "Validation Status"])
        df_sla.to_excel(writer, sheet_name="SLA Validation", index=False)

        # ─────────────────────────────────────────────────────────────────────
        # SHEET 8: Error Analysis
        # ─────────────────────────────────────────────────────────────────────
        if not df_req.empty:
            df_errors = df_req[df_req["Result"] == "FAIL"]
            if df_errors.empty:
                df_errors = pd.DataFrame([["None", "All requests succeeded. No errors encountered during load testing.", "—", "—", "—", "—"]], 
                                         columns=["Request ID", "Timestamp", "API Group", "Method", "Duration (ms)", "Status Code"])
            else:
                df_errors = df_errors.copy()
                df_errors.drop(columns=["Result"], inplace=True)
        else:
            df_errors = pd.DataFrame([["N/A", "No request logs parsed.", "—", "—", "—", "—"]], 
                                     columns=["Request ID", "Timestamp", "API Group", "Method", "Duration (ms)", "Status Code"])
        df_errors.to_excel(writer, sheet_name="Error Analysis", index=False)

        # ─────────────────────────────────────────────────────────────────────
        # SHEET 9: Load Test Results
        # ─────────────────────────────────────────────────────────────────────
        test_info = [
            ("Target URL", sum_data.get("raw_thresholds", {}).get("http_req_duration", {}).get("target", "https://tripsyncbackend-production-37a2.up.railway.app")),
            ("Virtual Users (VUs)", 100),
            ("Load Test Duration", "1 minute"),
            ("RPS Throughput Rate", round(sum_data.get("rps", 0.0), 2)),
            ("Checks Pass Rate", f"{sum_data.get('check_rate', 0.0)*100:.2f}%"),
            ("Total Checks Passed", sum_data.get("checks_passed", 0)),
            ("Total Checks Failed", sum_data.get("checks_failed", 0)),
            ("SLA Validation Result", "🟢 PASSED" if sum_data.get("checks_failed", 0) == 0 and global_err < 0.05 and global_p95 < 5000.0 else "🔴 FAILED")
        ]
        df_lt = pd.DataFrame(test_info, columns=["Configuration Detail", "Value"])
        df_lt.to_excel(writer, sheet_name="Load Test Results", index=False)

        # ─────────────────────────────────────────────────────────────────────
        # SHEET 10: All Results
        # ─────────────────────────────────────────────────────────────────────
        # Write top 50,000 requests max to avoid blowing up Excel sizes (well within 1m run at 100 VUs)
        df_req.head(50000).to_excel(writer, sheet_name="All Results", index=False)

    # 2. Add gorgeous styling and design to workbook via openpyxl
    import openpyxl
    wb = openpyxl.load_workbook(output_excel)

    # Styling for sheet "Executive Summary"
    ws = wb["Executive Summary"]
    style_header(ws)
    style_title_block(ws, "⚡ TripSync Backend Load Test Summary", f"Build #{build_num} | Commit: {commit_sha} | Date: {exec_date}")
    # Color-code the error rate row and overall status
    for row in range(4, ws.max_row + 1):
        cell_metric = ws.cell(row=row, column=1)
        cell_val = ws.cell(row=row, column=2)
        if "Error Rate" in str(cell_metric.value):
            rate_val = float(str(cell_val.value).replace('%', ''))
            if rate_val < 5.0:
                cell_val.fill = FILL_PASS
                cell_val.font = FONT_PASS
            else:
                cell_val.fill = FILL_FAIL
                cell_val.font = FONT_FAIL
        elif "P95 Response" in str(cell_metric.value):
            dur_val = float(str(cell_val.value).replace(' ms', ''))
            if dur_val < 5000.0:
                cell_val.fill = FILL_PASS
                cell_val.font = FONT_PASS
            else:
                cell_val.fill = FILL_FAIL
                cell_val.font = FONT_FAIL
    apply_auto_width_and_borders(ws)

    # Styling for API sheets (Health, Trips, Safety, Weather)
    for api in api_sheets:
        ws = wb[api]
        style_header(ws)
        style_title_block(ws, f"📈 {api} Performance Metrics", f"Detailed aggregate statistics for the {api} endpoint")
        color_status_cells(ws, 2, "🟢 PASS", "🔴 FAIL")
        apply_auto_width_and_borders(ws)

    # Styling for Performance Metrics
    ws = wb["Performance Metrics"]
    style_header(ws)
    style_title_block(ws, "⏱️ API Latency Percentile Distribution", "Calculated statistics across all API routes")
    apply_auto_width_and_borders(ws)

    # Styling for SLA Validation
    ws = wb["SLA Validation"]
    style_header(ws)
    style_title_block(ws, "📋 SLA Threshold Validation Report", "Detailed check against service-level agreement metrics")
    color_status_cells(ws, 5, "🟢 PASS", "🔴 FAIL")
    apply_auto_width_and_borders(ws)

    # Styling for Error Analysis
    ws = wb["Error Analysis"]
    style_header(ws)
    style_title_block(ws, "🔍 Error Log & Root Cause Analysis", "Chronological list of failing requests during execution")
    for r in range(4, ws.max_row + 1):
        cell_status = ws.cell(row=r, column=6)
        if cell_status.value and cell_status.value != "—":
            cell_status.fill = FILL_FAIL
            cell_status.font = FONT_FAIL
            cell_status.alignment = ALIGN_CENTER
    apply_auto_width_and_borders(ws)

    # Styling for Load Test Results
    ws = wb["Load Test Results"]
    style_header(ws)
    style_title_block(ws, "⚙️ Load Test Configuration & Outcome", "Inputs, execution throughput, and overall SLA results")
    for r in range(4, ws.max_row + 1):
        cell_lbl = ws.cell(row=r, column=1)
        cell_val = ws.cell(row=r, column=2)
        if "SLA Validation Result" in str(cell_lbl.value):
            if "PASSED" in str(cell_val.value):
                cell_val.fill = FILL_PASS
                cell_val.font = FONT_PASS
            else:
                cell_val.fill = FILL_FAIL
                cell_val.font = FONT_FAIL
            cell_val.alignment = ALIGN_CENTER
    apply_auto_width_and_borders(ws)

    # Styling for All Results
    ws = wb["All Results"]
    style_header(ws)
    style_title_block(ws, "📝 Raw Transaction Log", "First 50,000 chronological requests generated by the virtual users load test")
    color_status_cells(ws, 7, "PASS", "FAIL")
    apply_auto_width_and_borders(ws)

    # Save styled workbook
    wb.save(output_excel)
    print(f"[SUCCESS] Styled Excel report generated at: {output_excel}")


if __name__ == "__main__":
    main()
