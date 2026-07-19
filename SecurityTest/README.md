# TripSync Backend — Security Test Module

## Overview

Production-ready **Static Application Security Testing (SAST)** for the TripSync FastAPI Python backend. Auto-detects the framework (FastAPI/Flask), discovers all API endpoints, and performs comprehensive security analysis.

## Structure

```
SecurityTest/
├── config/
│   └── security-rules.json         # Scanner rules, OWASP/CWE mappings
├── scripts/
│   ├── backendScanner.js           # Core SAST engine (10 analysis modules)
│   └── generateSecuritySuite.js    # Report orchestrator (XLSX + Markdown)
├── reports/
│   ├── findings.xlsx               # Excel workbook (4 sheets)
│   ├── endpoint-inventory.md       # Complete API endpoint inventory
│   ├── dependency-report.md        # Python dependency security
│   ├── security-review.md          # Detailed findings report
│   └── executive-summary.md        # Management summary
└── README.md
```

## Framework Detection

The scanner automatically detects:
- ✅ **FastAPI** — via `from fastapi import`, `FastAPI()`
- ✅ **Flask** — via `from flask import`, `Flask(__name__)`

**Detected in TripSync:** FastAPI

## Analysis Modules

| Module | Checks |
|--------|--------|
| **Authentication** | JWT verification, Firebase token, auth dependencies |
| **Authorization** | userId from request, ownership checks, privilege escalation |
| **CORS** | Wildcard origins, credentials+wildcard, method restrictions |
| **Injection** | SQL, command injection, path traversal, template injection |
| **Secrets** | Hardcoded API keys, passwords, tokens in source code |
| **Input Validation** | Pydantic models, dict type endpoints, file upload validation |
| **Rate Limiting** | slowapi presence, per-endpoint throttling |
| **Exception Handling** | Bare except, error details in response, global handler |
| **Firebase Admin** | SDK initialization, verify_id_token usage |
| **Logging** | OTP in logs, sensitive data, print() vs logging module |
| **Dependencies** | Version pins, known CVEs, missing security packages |

## Endpoint Discovery

Automatically discovers:
- HTTP Method (GET, POST, PUT, PATCH, DELETE)
- Route path
- Handler function name
- File location and line number
- Authentication dependency presence
- JWT verification presence
- Input validation (Pydantic models)
- Rate limiting decorators

## Running the Scanner

### Full Suite (Recommended)
```bash
# From backend directory
node SecurityTest/scripts/generateSecuritySuite.js
```

### Scanner Only
```bash
node SecurityTest/scripts/backendScanner.js
```

### Prerequisites
The scanners use Node.js. The `xlsx` package is auto-installed if needed.

## Output Reports

### `findings.xlsx`
| Sheet | Contents |
|-------|----------|
| Security Findings | All findings with ID, severity, CWE, OWASP |
| Endpoint Inventory | All API endpoints with security flags |
| Dependency Vulnerabilities | Package versions, CVEs |
| Risk Summary | Severity breakdown, endpoint stats, category analysis |

### `endpoint-inventory.md`
Complete API endpoint inventory with security coverage analysis.

### `dependency-report.md`
Python dependency security analysis with recommendations.

### `security-review.md`
Detailed findings report with evidence and remediation.

### `executive-summary.md`
Management-level risk summary and action plan.

## OWASP Top 10 Coverage

| ID | Category | Covered |
|----|----------|---------|
| A01 | Broken Access Control | ✅ |
| A02 | Cryptographic Failures | ✅ |
| A03 | Injection | ✅ |
| A04 | Insecure Design | ✅ |
| A05 | Security Misconfiguration | ✅ |
| A06 | Vulnerable Components | ✅ |
| A07 | Auth Failures | ✅ |
| A09 | Logging Failures | ✅ |

## CI/CD Integration

```yaml
# .github/workflows/security.yml
- name: Run Backend Security Scan
  run: node backend/SecurityTest/scripts/generateSecuritySuite.js
  
- name: Upload Reports
  uses: actions/upload-artifact@v3
  with:
    name: backend-security-reports
    path: backend/SecurityTest/reports/
```

## Isolation

This module is **completely isolated** from the backend application:
- No Python dependencies required
- No modifications to application code
- Read-only analysis of source files
- Self-contained Node.js implementation
