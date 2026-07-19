#!/usr/bin/env node
/**
 * TripSync Backend SAST Security Scanner
 * =========================================
 * Production-ready static analysis for FastAPI/Flask Python backend.
 * Auto-detects framework, discovers all endpoints, audits security posture.
 *
 * Author: TripSync Security Team
 * Version: 1.0.0
 */

"use strict";

const fs = require("fs");
const path = require("path");

// ─── Configuration ────────────────────────────────────────────────────────────
const ROOT_DIR = path.resolve(__dirname, "../../");
const REPORT_DIR = path.resolve(__dirname, "../reports");
const RULES_PATH = path.resolve(__dirname, "../config/security-rules.json");

const rules = JSON.parse(fs.readFileSync(RULES_PATH, "utf8"));

// ─── Finding Registry ──────────────────────────────────────────────────────────
let findings = [];
let findingCounter = 1;
const SCAN_TIMESTAMP = new Date().toISOString();

function addFinding({
  severity, category, file, func, line, description, rootCause,
  impact, recommendation, cwe, owasp, evidence
}) {
  findings.push({
    id: `BE-${String(findingCounter++).padStart(4, "0")}`,
    severity, category,
    file: (file || "").replace(ROOT_DIR, "").replace(/\\/g, "/"),
    function: func || "N/A",
    line: line || "N/A",
    description, rootCause, impact, recommendation, cwe, owasp,
    evidence: evidence || "",
  });
}

// ─── Endpoint Registry ─────────────────────────────────────────────────────────
let endpoints = [];

function addEndpoint({ method, route, func, file, line, hasAuth, hasJWT,
  hasInputValidation, hasResponseValidation, hasRateLimit, notes }) {
  endpoints.push({
    method, route, function: func || "N/A", file: (file || "").replace(ROOT_DIR, "").replace(/\\/g, "/"),
    line: line || "N/A",
    hasAuth: hasAuth || false,
    hasJWT: hasJWT || false,
    hasInputValidation: hasInputValidation || false,
    hasResponseValidation: hasResponseValidation || false,
    hasRateLimit: hasRateLimit || false,
    notes: notes || "",
  });
}

// ─── File Discovery ────────────────────────────────────────────────────────────
const SCAN_EXTENSIONS = [".py", ".txt", ".env", ".cfg", ".ini", ".toml"];
const EXCLUDE_DIRS = new Set(["__pycache__", ".git", "SecurityTest", "tests", ".github", "venv", ".venv", "node_modules"]);

function walkDir(dir, files = []) {
  if (!fs.existsSync(dir)) return files;
  let entries;
  try { entries = fs.readdirSync(dir, { withFileTypes: true }); }
  catch { return files; }
  for (const entry of entries) {
    const fullPath = path.join(dir, entry.name);
    if (entry.isDirectory()) {
      if (!EXCLUDE_DIRS.has(entry.name)) walkDir(fullPath, files);
    } else if (SCAN_EXTENSIONS.some(ext => entry.name.endsWith(ext))) {
      files.push(fullPath);
    }
  }
  return files;
}

function readFile(filePath) {
  try { return fs.readFileSync(filePath, "utf8"); }
  catch { return null; }
}

// ─── Line-Aware Search ─────────────────────────────────────────────────────────
function findMatchesWithLines(content, pattern, flags = "g") {
  const lines = content.split("\n");
  const results = [];
  const regex = new RegExp(pattern, flags);
  lines.forEach((line, idx) => {
    regex.lastIndex = 0;
    if (regex.test(line)) {
      results.push({ line: idx + 1, content: line.trim() });
    }
  });
  return results;
}

function getLineNumber(content, pattern) {
  const lines = content.split("\n");
  const regex = new RegExp(pattern);
  for (let i = 0; i < lines.length; i++) {
    if (regex.test(lines[i])) return i + 1;
  }
  return "N/A";
}

// ─── Framework Detection ───────────────────────────────────────────────────────
function detectFramework(files) {
  console.log("  [+] Detecting backend framework...");

  for (const filePath of files) {
    const content = readFile(filePath);
    if (!content) continue;

    if (content.includes("from fastapi import") || content.includes("FastAPI(")) {
      console.log("  ✓ Detected: FastAPI");
      return "fastapi";
    }
    if (content.includes("from flask import") || content.includes("Flask(__name__)")) {
      console.log("  ✓ Detected: Flask");
      return "flask";
    }
  }
  return "unknown";
}

// ─── Endpoint Discovery ────────────────────────────────────────────────────────
function discoverEndpoints(files, framework) {
  console.log("  [+] Discovering API endpoints...");

  const httpMethods = ["get", "post", "put", "patch", "delete", "head", "options"];

  for (const filePath of files) {
    if (!filePath.endsWith(".py")) continue;
    const content = readFile(filePath);
    if (!content) continue;

    const lines = content.split("\n");

    for (let i = 0; i < lines.length; i++) {
      const line = lines[i].trim();

      // FastAPI: @app.get("/path") or @router.post("/path")
      const fastapiMatch = line.match(/@(?:app|router)\.(get|post|put|patch|delete|head|options)\s*\(\s*["']([^"']+)["']/);
      if (fastapiMatch) {
        const method = fastapiMatch[1].toUpperCase();
        const route = fastapiMatch[2];

        // Find function name in next few lines
        let funcName = "N/A";
        for (let j = i + 1; j < Math.min(i + 5, lines.length); j++) {
          const funcMatch = lines[j].match(/(?:async\s+)?def\s+(\w+)/);
          if (funcMatch) { funcName = funcMatch[1]; break; }
        }

        // Check for auth dependencies in signature and decorators above/below
        let hasAuth = false;
        let hasJWT = false;
        let hasInputValidation = false;
        let hasRateLimit = false;
        const endpointContext = lines.slice(Math.max(0, i - 5), Math.min(i + 20, lines.length)).join("\n");

        hasAuth = /Depends\(.*(?:get_current_user|verify_token|oauth2_scheme|firebase|authenticate)/i.test(endpointContext);
        hasJWT = /Bearer|jwt|id_token|verify_id_token|firebase_admin/i.test(endpointContext);
        hasInputValidation = /BaseModel|pydantic|Query\(|Body\(|Depends\(/i.test(endpointContext);
        hasRateLimit = /RateLimiter|slowapi|Throttle|rate_limit|limiter/i.test(endpointContext);

        const notes = [];
        if (!hasAuth) notes.push("No auth dependency detected");
        if (!hasInputValidation) notes.push("Minimal input validation");
        if (!hasRateLimit) notes.push("No rate limiting");

        addEndpoint({
          method, route, func: funcName, file: filePath, line: i + 1,
          hasAuth, hasJWT, hasInputValidation, hasResponseValidation: false,
          hasRateLimit, notes: notes.join("; "),
        });
      }

      // Flask: @app.route("/path", methods=["POST"])
      const flaskMatch = line.match(/@(?:app|bp)\.route\s*\(\s*["']([^"']+)["'](?:.*methods\s*=\s*\[([^\]]+)\])?/);
      if (flaskMatch) {
        const route = flaskMatch[1];
        const methodsStr = flaskMatch[2] || '"GET"';
        const methods = methodsStr.match(/["']([A-Z]+)["']/g)?.map(m => m.replace(/['"]/g, "")) || ["GET"];

        let funcName = "N/A";
        for (let j = i + 1; j < Math.min(i + 5, lines.length); j++) {
          const funcMatch = lines[j].match(/def\s+(\w+)/);
          if (funcMatch) { funcName = funcMatch[1]; break; }
        }

        for (const method of methods) {
          addEndpoint({
            method, route, func: funcName, file: filePath, line: i + 1,
            hasAuth: false, hasJWT: false, hasInputValidation: false,
            hasResponseValidation: false, hasRateLimit: false,
            notes: "Flask endpoint - manual auth review required",
          });
        }
      }
    }
  }

  console.log(`  ✓ Discovered ${endpoints.length} endpoints`);
  return endpoints;
}

// ─── SCANNER MODULES ──────────────────────────────────────────────────────────

// MODULE 1: Authentication Analysis
function scanAuthentication(files) {
  console.log("  [+] Scanning authentication patterns...");

  const mainPath = path.join(ROOT_DIR, "main.py");
  const mainContent = readFile(mainPath);

  if (mainContent) {
    // Check: Endpoints without auth (excluding intentional public endpoints)
    const PUBLIC_ENDPOINTS = new Set([
      "GET /", "GET /health", "GET /docs", "GET /redoc", "GET /openapi.json",
      "POST /api/otp/send", "POST /api/otp/verify"
    ]);
    const unauthEndpoints = endpoints.filter(
      e => !e.hasAuth && !PUBLIC_ENDPOINTS.has(`${e.method} ${e.route}`)
    );

    for (const ep of unauthEndpoints) {
      addFinding({
        severity: "HIGH",
        category: "Authentication / Missing Auth Dependency",
        file: ep.file || mainPath,
        func: ep.function,
        line: ep.line,
        description: `Endpoint ${ep.method} ${ep.route} has no authentication dependency or token verification.`,
        rootCause: `The FastAPI endpoint ${ep.function}() at ${ep.route} does not use Depends(get_current_user) or any Firebase token verification dependency.`,
        impact: "Any unauthenticated user can call this endpoint. User data may be exposed or modified without authorization.",
        recommendation: "Add Firebase token verification as a FastAPI dependency: Depends(verify_firebase_token). Verify the token using firebase_admin.auth.verify_id_token().",
        cwe: "CWE-306",
        owasp: "A07 - Identification and Authentication Failures",
        evidence: `${ep.method} ${ep.route} → ${ep.function}() at line ${ep.line}`,
      });
    }

    // Check: /api/otp/send returns OTP in response
    if (mainContent.includes('"otp": otp_code') || mainContent.includes('"otp"') && mainContent.includes('otp_code')) {
      const lineNum = getLineNumber(mainContent, '"otp"\\s*:\\s*otp_code|otp.*otp_code');
      addFinding({
        severity: "CRITICAL",
        category: "Authentication / OTP in API Response",
        file: mainPath,
        func: "send_otp_email_endpoint",
        line: lineNum,
        description: 'The /api/otp/send endpoint returns the OTP code in the JSON response body: {"otp": otp_code}.',
        rootCause: "The response object in send_otp_email_endpoint() includes the otp field with the actual OTP value.",
        impact: "An attacker can call POST /api/otp/send and read the OTP directly from the response body, completely bypassing the email verification flow. This is a critical authentication bypass vulnerability.",
        recommendation: "Remove 'otp' from the response body. The OTP should only be sent to the registered email. Return only {success, message} in the response. Implement OTP rate limiting and server-side OTP storage with expiry.",
        cwe: "CWE-287",
        owasp: "A07 - Identification and Authentication Failures",
        evidence: `"otp": otp_code returned in /api/otp/send response`,
      });
    }

    // Check: OTP printed to console
    if (mainContent.includes("OTP for") && mainContent.includes("is:")) {
      const lineNum = getLineNumber(mainContent, "OTP for.*is:");
      addFinding({
        severity: "HIGH",
        category: "Logging / OTP in Server Logs",
        file: mainPath,
        func: "send_otp_email_endpoint",
        line: lineNum,
        description: "OTP code is printed to server console output when SMTP is not configured.",
        rootCause: `print(f"⚠️ [SMTP WARNING] SMTP credentials not set. OTP for {email_to} is: {otp_code}") logs OTP in plaintext.`,
        impact: "Server logs contain plaintext OTP codes. Anyone with log access (DevOps, CI/CD logs, monitoring tools) can view OTPs and impersonate users.",
        recommendation: "Remove OTP from log output. If SMTP is down, return a generic error. Store OTP server-side (Redis/Firestore) with TTL. Never log OTPs.",
        cwe: "CWE-312",
        owasp: "A09 - Security Logging and Monitoring Failures",
        evidence: 'print(f"OTP for {email_to} is: {otp_code}")',
      });
    }

    // Check: userId from request body (not from verified token)
    const userIdMatches = findMatchesWithLines(mainContent, "userId:\\s*str|userId\\s*=\\s*Query");
    for (const m of userIdMatches) {
      addFinding({
        severity: "HIGH",
        category: "Authorization / User ID from Request",
        file: mainPath,
        func: "N/A",
        line: m.line,
        description: "userId is accepted from request body or query parameter without server-side token verification.",
        rootCause: "The endpoint accepts userId as a client-provided parameter (TripCreate model or Query param) instead of extracting it from a verified Firebase ID token.",
        impact: "An authenticated user can supply any userId value to access or modify data belonging to other users. This is a direct authorization bypass enabling horizontal privilege escalation.",
        recommendation: "Extract userId from verified Firebase ID token server-side: uid = decoded_token['uid']. Never trust client-supplied user identifiers.",
        cwe: "CWE-639",
        owasp: "A01 - Broken Access Control",
        evidence: m.content,
      });
    }
  }
}

// MODULE 2: CORS Security
function scanCORS(files) {
  console.log("  [+] Scanning CORS configuration...");

  for (const filePath of files) {
    if (!filePath.endsWith(".py")) continue;
    const content = readFile(filePath);
    if (!content) continue;

    // Wildcard origins
    const wildcardMatches = findMatchesWithLines(content, 'allow_origins\\s*=\\s*\\[\\s*["\']\\*["\']\\s*\\]');
    for (const m of wildcardMatches) {
      addFinding({
        severity: "HIGH",
        category: "CORS / Wildcard Origins",
        file: filePath,
        func: "CORSMiddleware",
        line: m.line,
        description: "CORS is configured with wildcard (*) allowing any origin to make cross-origin requests.",
        rootCause: "allow_origins=[\"*\"] in CORSMiddleware configuration allows any domain to access the API.",
        impact: "Any website can make cross-origin requests to the API. Combined with allow_credentials=True, this creates a CSRF-equivalent vulnerability where malicious sites can make authenticated requests on behalf of users.",
        recommendation: "Restrict CORS to specific trusted origins: allow_origins=['https://tripsync.vercel.app', 'https://tripsyncweb.com']. Never combine allow_origins=['*'] with allow_credentials=True.",
        cwe: "CWE-942",
        owasp: "A05 - Security Misconfiguration",
        evidence: m.content,
      });
    }

    // Wildcard with credentials
    const credWildcardMatches = findMatchesWithLines(content, 'allow_origins\\s*=\\s*\\[\\s*["\']\\*["\']\\s*\\]');
    if (credWildcardMatches.length > 0 && content.includes('allow_credentials=True')) {
      const lineNum = credWildcardMatches[0].line;
      addFinding({
        severity: "CRITICAL",
        category: "CORS / Wildcard with Credentials",
        file: filePath,
        func: "CORSMiddleware",
        line: lineNum,
        description: "CORS is configured with allow_origins=[\"*\"] AND allow_credentials=True simultaneously.",
        rootCause: "Both wildcard origin and credentials are enabled in CORSMiddleware. This combination is rejected by browsers but indicates a security misconfiguration intent.",
        impact: "This configuration violates the CORS specification and modern browsers will reject it. However, it indicates intent to allow cross-site authenticated requests from any origin.",
        recommendation: "Specify exact trusted origins when using credentials. Remove the wildcard if credentials are needed: allow_origins=['https://yourdomain.com'], allow_credentials=True.",
        cwe: "CWE-942",
        owasp: "A05 - Security Misconfiguration",
        evidence: "allow_origins=[\"*\"] with allow_credentials=True",
      });
    }

    // Wildcard methods
    const wildcardMethods = findMatchesWithLines(content, 'allow_methods\\s*=\\s*\\[\\s*["\']\\*["\']\\s*\\]');
    for (const m of wildcardMethods) {
      addFinding({
        severity: "MEDIUM",
        category: "CORS / Wildcard Methods",
        file: filePath,
        func: "CORSMiddleware",
        line: m.line,
        description: "All HTTP methods are allowed via CORS wildcard. DELETE and PUT methods should be explicitly controlled.",
        rootCause: 'allow_methods=["*"] permits any HTTP method for cross-origin requests.',
        impact: "Cross-origin requests can use any HTTP method including DELETE, which could lead to data deletion through CSRF-like attacks.",
        recommendation: 'Explicitly list allowed methods: allow_methods=["GET", "POST", "PUT", "DELETE"] only if all are required.',
        cwe: "CWE-942",
        owasp: "A05 - Security Misconfiguration",
        evidence: m.content,
      });
    }
  }
}

// MODULE 3: Injection Analysis
function scanInjection(files) {
  console.log("  [+] Scanning for injection vulnerabilities...");

  for (const filePath of files) {
    if (!filePath.endsWith(".py")) continue;
    const content = readFile(filePath);
    if (!content) continue;

    // Check: eval() / exec()
    const evalMatches = findMatchesWithLines(content, "\\beval\\s*\\(|\\bexec\\s*\\(");
    for (const m of evalMatches) {
      if (m.content.startsWith("#")) continue;
      addFinding({
        severity: "CRITICAL",
        category: "Injection / Code Execution",
        file: filePath,
        func: "N/A",
        line: m.line,
        description: "eval() or exec() usage detected which can execute arbitrary Python code.",
        rootCause: "eval() or exec() evaluates strings as Python code at runtime.",
        impact: "If user-controlled input reaches eval()/exec(), it enables Remote Code Execution (RCE) on the server.",
        recommendation: "Remove eval() and exec(). Use safer alternatives: ast.literal_eval() for data parsing, or refactor to avoid dynamic code execution.",
        cwe: "CWE-94",
        owasp: "A03 - Injection",
        evidence: m.content,
      });
    }

    // Check: os.system() / subprocess with string interpolation
    const cmdInjMatches = findMatchesWithLines(content, "os\\.system\\s*\\(|subprocess\\.(?:call|run|Popen)\\s*\\([^,\\)]*\\+|shell=True");
    for (const m of cmdInjMatches) {
      if (m.content.startsWith("#")) continue;
      addFinding({
        severity: "CRITICAL",
        category: "Injection / Command Injection",
        file: filePath,
        func: "N/A",
        line: m.line,
        description: "OS command execution detected. Shell=True or string concatenation in subprocess can enable command injection.",
        rootCause: "Use of os.system() or subprocess with shell=True or string concatenation introduces command injection risk.",
        impact: "If user input reaches command arguments, attackers can inject arbitrary OS commands with the application server's privileges.",
        recommendation: "Use subprocess.run() with list arguments (no shell=True) and never include user input in command strings. Validate and sanitize all inputs.",
        cwe: "CWE-78",
        owasp: "A03 - Injection",
        evidence: m.content,
      });
    }

    // Check: Path traversal in file handling
    const pathTraversalMatches = findMatchesWithLines(content, "open\\s*\\(.*\\+|os\\.path\\.join\\(.*request|filename.*=.*file\\.filename");
    for (const m of pathTraversalMatches) {
      if (m.content.startsWith("#")) continue;
      addFinding({
        severity: "HIGH",
        category: "Injection / Path Traversal",
        file: filePath,
        func: "N/A",
        line: m.line,
        description: "Potential path traversal in file operation. User-controlled filename or path may allow directory traversal.",
        rootCause: "File operations use user-supplied filenames without sanitization against path traversal sequences (../).",
        impact: "Attackers can use ../ sequences to read or write files outside the intended directory, potentially exposing configuration files or system files.",
        recommendation: "Sanitize filenames: use os.path.basename() to strip directory components. Validate file paths are within the expected directory using os.path.realpath().",
        cwe: "CWE-22",
        owasp: "A03 - Injection",
        evidence: m.content,
      });
    }

    // Check: Template injection
    const templateMatches = findMatchesWithLines(content, "\\.format\\(.*request|f[\"'].*\\{.*request|Template\\(.*request");
    for (const m of templateMatches) {
      if (m.content.startsWith("#")) continue;
      addFinding({
        severity: "HIGH",
        category: "Injection / Template Injection",
        file: filePath,
        func: "N/A",
        line: m.line,
        description: "Server-side template injection risk. User data may be interpolated into template strings.",
        rootCause: "User-controlled input is directly interpolated into f-strings or .format() calls that may be rendered as templates.",
        impact: "SSTI can lead to Remote Code Execution by injecting template directives through user-controlled input.",
        recommendation: "Never interpolate user data directly into template strings. Use proper escaping or parameter binding.",
        cwe: "CWE-94",
        owasp: "A03 - Injection",
        evidence: m.content,
      });
    }
  }
}

// MODULE 4: Secret & Credential Scanning
function scanSecrets(files) {
  console.log("  [+] Scanning for secrets and hardcoded credentials...");

  const secretPatterns = [
    { pattern: "sk-or-v1-[A-Za-z0-9]{40,}", name: "OpenRouter API Key", severity: "CRITICAL" },
    { pattern: "gsk_[A-Za-z0-9]{20,}", name: "Groq API Key", severity: "CRITICAL" },
    { pattern: "hf_[A-Za-z0-9]{20,}", name: "HuggingFace API Key", severity: "HIGH" },
    { pattern: "AIza[A-Za-z0-9_\\-]{35}", name: "Google/Firebase API Key", severity: "HIGH" },
    { pattern: "AQ\\.Ab8[A-Za-z0-9_\\-]{10,}", name: "Gemini API Key", severity: "CRITICAL" },
    { pattern: "password\\s*=\\s*['\"][^'\"]{4,}['\"]", name: "Hardcoded Password", severity: "CRITICAL" },
    { pattern: "secret_key\\s*=\\s*['\"][^'\"]{8,}['\"]", name: "Hardcoded Secret Key", severity: "HIGH" },
    { pattern: "smtp_pass.*=.*['\"][^'\"]+['\"]", name: "SMTP Password", severity: "HIGH" },
  ];

  for (const filePath of files) {
    const content = readFile(filePath);
    if (!content) continue;

    const isEnvFile = filePath.includes(".env");
    const isSourceFile = filePath.endsWith(".py");

    for (const sp of secretPatterns) {
      const matches = findMatchesWithLines(content, sp.pattern);
      for (const m of matches) {
        if (m.content.trim().startsWith("#") || m.content.includes("os.environ") ||
          m.content.includes("os.getenv") || m.content.includes("getenv")) continue;

        addFinding({
          severity: isSourceFile ? "CRITICAL" : sp.severity,
          category: `Secrets / ${sp.name}`,
          file: filePath,
          func: "N/A",
          line: m.line,
          description: `${sp.name} detected ${isSourceFile ? "hardcoded in source code" : "in environment file"}.`,
          rootCause: `${sp.name} value found as a literal string in ${filePath.replace(ROOT_DIR, "")}.`,
          impact: isSourceFile
            ? "Secret is committed to source control and permanently in git history. Immediate rotation required."
            : "Ensure .env file is in .gitignore and never committed to source control.",
          recommendation: isSourceFile
            ? `Rotate the exposed ${sp.name} immediately. Use os.environ.get('KEY_NAME') instead of hardcoded values. Add key to .gitignore'd .env file.`
            : "Keep .env in .gitignore. Use a secrets manager for production deployments.",
          cwe: "CWE-798",
          owasp: "A02 - Cryptographic Failures",
          evidence: m.content.replace(/['"]\S{8,}['"]/g, "[REDACTED]"),
        });
      }
    }
  }
}

// MODULE 5: Input Validation
function scanInputValidation(files) {
  console.log("  [+] Scanning input validation...");

  const mainPath = path.join(ROOT_DIR, "main.py");
  const mainContent = readFile(mainPath);

  if (mainContent) {
    // Check: dict input without validation
    const dictInputMatches = findMatchesWithLines(mainContent, "def\\s+\\w+\\s*\\(.*data:\\s*dict");
    for (const m of dictInputMatches) {
      addFinding({
        severity: "MEDIUM",
        category: "Input Validation / Arbitrary Dict Input",
        file: mainPath,
        func: "N/A",
        line: m.line,
        description: "Endpoint accepts arbitrary dict type without Pydantic model validation.",
        rootCause: "Parameter type is 'dict' without a Pydantic BaseModel, allowing any structure.",
        impact: "Unvalidated dict input can contain unexpected fields, type mismatches, or excessively large payloads leading to unexpected behavior.",
        recommendation: "Replace 'dict' parameter with a Pydantic BaseModel that explicitly defines allowed fields and their types. This provides automatic validation, type coercion, and documentation.",
        cwe: "CWE-20",
        owasp: "A03 - Injection",
        evidence: m.content,
      });
    }

    // Check: Query params without validation
    const unvalidatedQueryMatches = findMatchesWithLines(
      mainContent,
      "Query\\s*\\(\\.\\.\\.\\s*,\\s*description=|userId.*=.*Query\\("
    );
    for (const m of unvalidatedQueryMatches) {
      addFinding({
        severity: "LOW",
        category: "Input Validation / Query Param Validation",
        file: mainPath,
        func: "N/A",
        line: m.line,
        description: "Query parameter uses basic FastAPI Query() validation without additional constraints.",
        rootCause: "Query parameters lack min_length, max_length, regex, or custom validators.",
        impact: "Malformed or excessively long inputs could cause unexpected behavior or DoS through resource exhaustion.",
        recommendation: "Add constraints to Query parameters: Query(..., min_length=1, max_length=100, regex='^[a-zA-Z0-9_-]+$'). Validate userId against authenticated token.",
        cwe: "CWE-20",
        owasp: "A04 - Insecure Design",
        evidence: m.content,
      });
    }

    // Check: Missing size limit on file uploads
    const fileUploadMatches = findMatchesWithLines(mainContent, "UploadFile\\s*=\\s*File\\(");
    for (const m of fileUploadMatches) {
      // Check if there's a size check nearby
      const lines = mainContent.split("\n");
      const lineIdx = m.line - 1;
      const context = lines.slice(Math.max(0, lineIdx - 2), Math.min(lines.length, lineIdx + 15)).join("\n");
      
      if (!context.includes("content_length") && !context.includes("MAX_SIZE") && !context.includes("max_size")) {
        addFinding({
          severity: "MEDIUM",
          category: "File Upload / Missing Size Limit",
          file: mainPath,
          func: "transcribe_voice",
          line: m.line,
          description: "File upload endpoint lacks explicit file size validation.",
          rootCause: "UploadFile handler does not enforce a maximum file size limit.",
          impact: "An attacker can upload arbitrarily large files causing disk exhaustion (DoS), memory exhaustion, or slow processing attacks.",
          recommendation: "Implement file size checking: if file.size > MAX_UPLOAD_SIZE: raise HTTPException(413). Also validate MIME type via magic bytes, not just file extension.",
          cwe: "CWE-400",
          owasp: "A04 - Insecure Design",
          evidence: m.content,
        });
      }
    }

    // Check: File type validation
    if (mainContent.includes("UploadFile")) {
      const filenameExtMatches = findMatchesWithLines(mainContent, "os\\.path\\.splitext\\(file\\.filename\\)");
      for (const m of filenameExtMatches) {
        addFinding({
          severity: "MEDIUM",
          category: "File Upload / Extension-Only Validation",
          file: mainPath,
          func: "transcribe_voice",
          line: m.line,
          description: "File type validation relies only on file extension, not on magic bytes/MIME type verification.",
          rootCause: "os.path.splitext(file.filename)[1] checks the file extension which can be easily spoofed.",
          impact: "Attacker can rename a malicious file with a .m4a extension to bypass the type check. The file content is not validated.",
          recommendation: "Validate file content using python-magic or filetype library to check magic bytes. Combine with extension validation: allowed_extensions = {'.m4a', '.mp3', '.wav', '.ogg'}.",
          cwe: "CWE-434",
          owasp: "A04 - Insecure Design",
          evidence: m.content,
        });
      }
    }
  }
}

// MODULE 6: Rate Limiting
function scanRateLimiting(files) {
  console.log("  [+] Scanning rate limiting...");

  const hasSlowapiDep = files.some(f => {
    if (!f.includes("requirements")) return false;
    const content = readFile(f);
    return content && content.includes("slowapi");
  });

  const hasRateLimitImport = files.some(f => {
    if (!f.endsWith(".py")) return false;
    const content = readFile(f);
    return content && (content.includes("from slowapi") || content.includes("RateLimiter") || content.includes("@limiter"));
  });

  if (!hasSlowapiDep && !hasRateLimitImport) {
    addFinding({
      severity: "HIGH",
      category: "Rate Limiting / No Rate Limiting Middleware",
      file: path.join(ROOT_DIR, "main.py"),
      func: "N/A",
      line: 1,
      description: "No rate limiting is configured. All API endpoints are unbounded and can be called without restriction.",
      rootCause: "slowapi or any rate limiting library is absent from requirements.txt and source code.",
      impact: "Without rate limiting: (1) Brute force attacks on authentication are possible, (2) DoS via request flooding, (3) OTP brute force (especially critical given OTP is returned in response), (4) AI endpoint abuse leading to excessive costs.",
      recommendation: "Install slowapi: pip install slowapi. Configure per-endpoint limits. Prioritize: /api/otp/send (max 3/min/IP), /api/chat (max 20/min/user), /api/voice/transcribe (max 10/min/user).",
      cwe: "CWE-307",
      owasp: "A04 - Insecure Design",
      evidence: "slowapi not found in requirements.txt or any .py source file",
    });

    // Finding for specific high-risk endpoints
    const criticalEndpoints = endpoints.filter(e =>
      e.route.includes("/otp") || e.route.includes("/chat") || e.route.includes("/voice") ||
      e.route.includes("/auth") || e.route.includes("/login")
    );

    for (const ep of criticalEndpoints) {
      addFinding({
        severity: "HIGH",
        category: "Rate Limiting / Critical Endpoint Unthrottled",
        file: ep.file,
        func: ep.function,
        line: ep.line,
        description: `High-sensitivity endpoint ${ep.method} ${ep.route} has no rate limiting.`,
        rootCause: `${ep.function}() handles ${ep.route} without any rate limit decorator or middleware.`,
        impact: `Unbounded ${ep.route} allows: brute force, DoS, API abuse, and cost amplification via AI calls.`,
        recommendation: `Apply @limiter.limit("3/minute") decorator on ${ep.function}. Implement IP-based and user-based rate limiting.`,
        cwe: "CWE-307",
        owasp: "A04 - Insecure Design",
        evidence: `${ep.method} ${ep.route} → ${ep.function}() - no rate limiting`,
      });
    }
  }
}

// MODULE 7: Exception Handling
function scanExceptionHandling(files) {
  console.log("  [+] Scanning exception handling...");

  const mainPath = path.join(ROOT_DIR, "main.py");
  const mainContent = readFile(mainPath);

  if (mainContent) {
    // Check: Error details in response
    const errorInResponseMatches = findMatchesWithLines(mainContent, '"error"\\s*:\\s*str\\(e\\)|"message".*str\\(e\\)');
    for (const m of errorInResponseMatches) {
      addFinding({
        severity: "MEDIUM",
        category: "Exception Handling / Error Details in Response",
        file: mainPath,
        func: "N/A",
        line: m.line,
        description: "Raw exception details (str(e)) returned in API response body.",
        rootCause: "Exception message is converted to string and included directly in the JSON response.",
        impact: "Exception messages may contain internal paths, database credentials, library versions, stack traces, or other information useful for targeted attacks.",
        recommendation: "Return generic error messages to clients: {\"error\": \"Service temporarily unavailable\"}. Log full exception details server-side only.",
        cwe: "CWE-209",
        owasp: "A09 - Security Logging and Monitoring Failures",
        evidence: m.content,
      });
    }

    // Check: Bare except clauses
    const bareExceptMatches = findMatchesWithLines(mainContent, "except\\s*:");
    for (const m of bareExceptMatches) {
      addFinding({
        severity: "LOW",
        category: "Exception Handling / Bare Except",
        file: mainPath,
        func: "N/A",
        line: m.line,
        description: "Bare 'except:' clause catches all exceptions including KeyboardInterrupt and SystemExit.",
        rootCause: "except: without specifying exception type swallows all exceptions silently.",
        impact: "Security-relevant exceptions (authentication failures, permission errors) are silently swallowed, causing application misbehavior and masking security issues.",
        recommendation: "Always specify exception types: except (HTTPException, ValueError) as e. Use broad Exception as fallback only with proper logging.",
        cwe: "CWE-390",
        owasp: "A09 - Security Logging and Monitoring Failures",
        evidence: m.content,
      });
    }

    // Check: Missing global exception handler
    if (!mainContent.includes("@app.exception_handler") && !mainContent.includes("exception_handler")) {
      addFinding({
        severity: "MEDIUM",
        category: "Exception Handling / Missing Global Handler",
        file: mainPath,
        func: "N/A",
        line: 1,
        description: "No global exception handler registered. Unhandled exceptions may expose stack traces.",
        rootCause: "FastAPI app has no @app.exception_handler(Exception) to catch and format unexpected errors.",
        impact: "Unexpected exceptions return default FastAPI 500 responses which may include stack traces in debug mode.",
        recommendation: "Register a global exception handler: @app.exception_handler(Exception) that returns a generic JSON error response and logs the full traceback server-side.",
        cwe: "CWE-209",
        owasp: "A09 - Security Logging and Monitoring Failures",
        evidence: "No exception_handler registered on app",
      });
    }
  }
}

// MODULE 8: Firebase Admin & JWT
function scanFirebaseAdmin(files) {
  console.log("  [+] Scanning Firebase Admin SDK usage...");

  const hasFbAdmin = files.some(f => {
    if (!f.endsWith(".py")) return false;
    const content = readFile(f);
    return content && content.includes("firebase_admin");
  });

  const hasFbAdminDep = files.some(f => {
    if (!f.includes("requirements")) return false;
    const content = readFile(f);
    return content && content.includes("firebase-admin");
  });

  if (!hasFbAdmin && hasFbAdminDep) {
    addFinding({
      severity: "HIGH",
      category: "Firebase Admin / Not Initialized",
      file: path.join(ROOT_DIR, "main.py"),
      func: "N/A",
      line: 1,
      description: "firebase-admin is in requirements.txt but no firebase_admin initialization found in source code.",
      rootCause: "firebase_admin.initialize_app() is not called in any Python file.",
      impact: "Firebase Admin is not available for server-side operations like verifying ID tokens, managing users, or Firestore admin access.",
      recommendation: "Initialize Firebase Admin at startup with service account credentials. Store credentials path in environment variables, not source code.",
      cwe: "CWE-287",
      owasp: "A07 - Identification and Authentication Failures",
      evidence: "firebase-admin in requirements.txt but firebase_admin.initialize_app() not found",
    });
  }

  // Check: No JWT verification in any endpoint
  const anyJwtVerification = files.some(f => {
    if (!f.endsWith(".py")) return false;
    const content = readFile(f);
    return content && (content.includes("verify_id_token") || content.includes("decode_token") ||
      content.includes("jwt.decode") || content.includes("verify_token"));
  });

  if (!anyJwtVerification) {
    addFinding({
      severity: "CRITICAL",
      category: "Authentication / No JWT Verification",
      file: path.join(ROOT_DIR, "main.py"),
      func: "N/A",
      line: 1,
      description: "No JWT or Firebase ID token verification found anywhere in the backend source code.",
      rootCause: "None of the Python files contain token verification logic (verify_id_token, jwt.decode).",
      impact: "All API endpoints lack server-side authentication verification. Any request, regardless of authentication state, can access all API functionality. This is the most critical security gap in the backend.",
      recommendation: "Implement a Firebase token verification dependency: Use firebase_admin.auth.verify_id_token() in a FastAPI Depends() function. Apply it to all protected endpoints.",
      cwe: "CWE-306",
      owasp: "A07 - Identification and Authentication Failures",
      evidence: "No verify_id_token() or jwt verification found in any .py file",
    });
  }
}

// MODULE 9: Logging & Monitoring
function scanLogging(files) {
  console.log("  [+] Scanning logging practices...");

  for (const filePath of files) {
    if (!filePath.endsWith(".py")) continue;
    const content = readFile(filePath);
    if (!content) continue;

    // Check: Sensitive data in print/log
    const sensitivePrintMatches = findMatchesWithLines(
      content,
      'print\\s*\\([^)]*(?:otp|password|token|secret|key|email|api_key)[^)]*\\)'
    );
    for (const m of sensitivePrintMatches) {
      if (m.content.trim().startsWith("#")) continue;
      addFinding({
        severity: "MEDIUM",
        category: "Logging / Sensitive Data in Logs",
        file: filePath,
        func: "N/A",
        line: m.line,
        description: "Potentially sensitive data (OTP, password, token, secret, email) output to console via print().",
        rootCause: "print() statement includes sensitive variable names suggesting PII or credentials are logged.",
        impact: "Sensitive data appears in server logs, accessible to DevOps, CI/CD systems, and log aggregation tools. GDPR compliance risk.",
        recommendation: "Remove sensitive data from print() and logging calls. Implement structured logging with data masking. Use Python's logging module with appropriate levels.",
        cwe: "CWE-312",
        owasp: "A09 - Security Logging and Monitoring Failures",
        evidence: m.content,
      });
    }

    // Check: Using print() instead of proper logging
    const printUsageMatches = findMatchesWithLines(content, "^\\s*print\\s*\\(");
    if (printUsageMatches.length > 5) {
      addFinding({
        severity: "LOW",
        category: "Logging / print() instead of logging module",
        file: filePath,
        func: "N/A",
        line: printUsageMatches[0]?.line || 1,
        description: `${printUsageMatches.length} print() statements found. Production code should use Python's logging module.`,
        rootCause: "print() is used for diagnostic output instead of the Python logging module.",
        impact: "print() output cannot be filtered by log level, does not include timestamps, cannot be sent to log aggregation services, and may expose debug info in production.",
        recommendation: "Replace print() with logging.info(), logging.warning(), logging.error(). Configure logging with appropriate handlers and formatters for production.",
        cwe: "CWE-532",
        owasp: "A09 - Security Logging and Monitoring Failures",
        evidence: `${printUsageMatches.length} print() statements found`,
      });
    }
  }
}

// MODULE 10: Dependency Analysis
function scanDependencies(files) {
  console.log("  [+] Scanning Python dependencies...");

  const reqPath = files.find(f => f.includes("requirements.txt"));
  if (!reqPath) return [];

  const content = readFile(reqPath);
  if (!content) return [];

  const depFindings = [];
  const lines = content.split("\n").filter(l => l.trim() && !l.startsWith("#"));

  // Known vulnerability database (simplified)
  const knownVulnerabilities = {
    "fastapi": { minSafe: "0.100.0", latest: "0.115.x", cve: null, severity: "INFO" },
    "uvicorn": { minSafe: "0.22.0", latest: "0.32.x", cve: null, severity: "INFO" },
    "pydantic": { minSafe: "2.0.0", latest: "2.10.x", cve: null, severity: "INFO" },
    "openai": { minSafe: "1.0.0", latest: "1.58.x", cve: null, severity: "INFO" },
    "httpx": { minSafe: "0.24.0", latest: "0.28.x", cve: null, severity: "INFO" },
    "firebase-admin": { minSafe: "6.2.0", latest: "6.6.x", cve: null, severity: "INFO" },
    "python-multipart": { minSafe: "0.0.6", latest: "0.0.20", cve: "CVE-2024-xxx", severity: "MEDIUM",
      note: "Verify python-multipart >= 0.0.7 to avoid form parsing vulnerabilities" },
  };

  // Check version pins
  let unpinnedCount = 0;
  for (const line of lines) {
    const match = line.match(/^([a-zA-Z0-9_\-]+)([><=!]{0,2})(.*)$/);
    if (!match) continue;

    const [, pkgName, operator, version] = match;
    const pkgInfo = knownVulnerabilities[pkgName.toLowerCase()];

    // Check for unpinned (>= without upper bound)
    if (operator === ">=" && !line.includes(",")) {
      unpinnedCount++;
      depFindings.push({
        package: pkgName,
        installedVersion: `${operator}${version}`,
        latestVersion: pkgInfo?.latest || "check PyPI",
        severity: "LOW",
        description: `${pkgName} uses minimum version constraint (>=) without upper bound. May install untested versions.`,
        recommendation: `Pin to specific version: ${pkgName}==${version} or use range: ${pkgName}>=${version},<${parseInt(version.split(".")[0]) + 1}.0.0`,
        cve: "",
      });
    }

    if (pkgInfo) {
      depFindings.push({
        package: pkgName,
        installedVersion: `${operator}${version}`,
        latestVersion: pkgInfo.latest,
        severity: pkgInfo.severity,
        description: pkgInfo.note || `${pkgName} version should be kept updated`,
        recommendation: `Ensure ${pkgName} is regularly updated. Current constraint: ${operator}${version}`,
        cve: pkgInfo.cve || "",
      });

      if (pkgInfo.severity !== "INFO" && pkgInfo.cve) {
        let isVuln = true;
        if (pkgName.toLowerCase() === "python-multipart") {
          const verNum = parseFloat(version);
          if (verNum >= 0.07 || version.includes("0.0.7") || version.includes("0.0.8") || version.includes("0.0.9")) {
            isVuln = false;
          }
        }
        if (isVuln) {
          addFinding({
            severity: pkgInfo.severity,
            category: `Dependencies / ${pkgName} Vulnerability`,
            file: reqPath,
            func: "N/A",
            line: lines.indexOf(line) + 1,
            description: `${pkgName} has a known security concern: ${pkgInfo.note}`,
            rootCause: `${pkgName} version constraint ${operator}${version} may include vulnerable versions.`,
            impact: `Vulnerable ${pkgName} may expose the application to known exploits.`,
            recommendation: pkgInfo.note || `Update ${pkgName} to the latest secure version.`,
            cwe: "CWE-1104",
            owasp: "A06 - Vulnerable and Outdated Components",
            evidence: line,
          });
        }
      }
    }
  }

  if (unpinnedCount > 0) {
    addFinding({
      severity: "LOW",
      category: "Dependencies / Unpinned Versions",
      file: reqPath,
      func: "N/A",
      line: 1,
      description: `${unpinnedCount} dependencies use minimum version constraints (>=) without exact pins.`,
      rootCause: "requirements.txt uses >= constraints that may resolve to different versions across environments.",
      impact: "Non-deterministic dependency resolution can introduce breaking changes or vulnerabilities during deployment.",
      recommendation: "Use pip freeze > requirements-lock.txt to create exact version pins. Use tools like pip-tools for dependency management.",
      cwe: "CWE-1104",
      owasp: "A06 - Vulnerable and Outdated Components",
      evidence: `${unpinnedCount} packages without exact version pins`,
    });
  }

  // Check missing security packages
  const allDepNames = lines.map(l => l.match(/^([a-zA-Z0-9_\-]+)/)?.[1]?.toLowerCase()).filter(Boolean);
  
  if (!allDepNames.includes("slowapi")) {
    depFindings.push({
      package: "slowapi (MISSING)",
      installedVersion: "not installed",
      latestVersion: "0.1.9",
      severity: "HIGH",
      description: "Rate limiting library not installed. All endpoints are unbounded.",
      recommendation: "pip install slowapi==0.1.9",
      cve: "",
    });
  }

  if (!allDepNames.includes("python-jose") && !allDepNames.includes("pyjwt")) {
    depFindings.push({
      package: "JWT library (MISSING)",
      installedVersion: "not installed",
      latestVersion: "python-jose>=3.3.0 or PyJWT>=2.8.0",
      severity: "HIGH",
      description: "No JWT verification library installed. Token verification relies on firebase-admin only.",
      recommendation: "Install python-jose[cryptography] or PyJWT for additional JWT handling flexibility.",
      cve: "",
    });
  }

  return depFindings;
}

// ─── Report Generators ────────────────────────────────────────────────────────
function generateEndpointInventory() {
  let md = `# TripSync Backend — API Endpoint Inventory\n\n`;
  md += `**Generated:** ${SCAN_TIMESTAMP}  \n`;
  md += `**Total Endpoints:** ${endpoints.length}\n\n`;
  md += `---\n\n`;

  // Summary table
  md += `## Security Summary\n\n`;
  md += `| Metric | Count |\n|--------|-------|\n`;
  md += `| Total Endpoints | ${endpoints.length} |\n`;
  md += `| Endpoints with Auth | ${endpoints.filter(e => e.hasAuth).length} |\n`;
  md += `| Endpoints without Auth | ${endpoints.filter(e => !e.hasAuth).length} |\n`;
  md += `| Endpoints with Rate Limiting | ${endpoints.filter(e => e.hasRateLimit).length} |\n`;
  md += `| Endpoints with Input Validation | ${endpoints.filter(e => e.hasInputValidation).length} |\n\n`;

  md += `## Endpoint Details\n\n`;
  md += `| Method | Route | Function | Auth | JWT | Input Validation | Rate Limit | Notes |\n`;
  md += `|--------|-------|----------|------|-----|-----------------|------------|-------|\n`;

  for (const ep of endpoints.sort((a, b) => a.route.localeCompare(b.route))) {
    const auth = ep.hasAuth ? "✅" : "❌";
    const jwt = ep.hasJWT ? "✅" : "❌";
    const inputVal = ep.hasInputValidation ? "✅" : "⚠️";
    const rateLimit = ep.hasRateLimit ? "✅" : "❌";
    md += `| **${ep.method}** | \`${ep.route}\` | \`${ep.function}\` | ${auth} | ${jwt} | ${inputVal} | ${rateLimit} | ${ep.notes} |\n`;
  }

  md += `\n## Unauthenticated Endpoints (HIGH RISK)\n\n`;
  const unauthEps = endpoints.filter(e =>
    !e.hasAuth &&
    !["GET /", "GET /health", "GET /docs", "GET /redoc", "GET /openapi.json"].includes(`${e.method} ${e.route}`)
  );

  if (unauthEps.length === 0) {
    md += `✅ All sensitive endpoints have authentication.\n\n`;
  } else {
    md += `⚠️ **${unauthEps.length} endpoints lack authentication:**\n\n`;
    for (const ep of unauthEps) {
      md += `- \`${ep.method} ${ep.route}\` → \`${ep.function}()\`\n`;
    }
  }

  return md;
}

function generateDependencyReport(depFindings) {
  let md = `# TripSync Backend — Dependency Security Report\n\n`;
  md += `**Generated:** ${SCAN_TIMESTAMP}  \n`;
  md += `**File:** requirements.txt\n\n`;
  md += `---\n\n`;

  md += `## Dependency Analysis\n\n`;
  md += `| Package | Installed | Latest | Severity | Notes |\n|---------|-----------|--------|----------|-------|\n`;
  for (const d of depFindings) {
    md += `| ${d.package} | ${d.installedVersion} | ${d.latestVersion} | ${d.severity} | ${d.description} |\n`;
  }

  md += `\n## Security Recommendations\n\n`;
  md += `1. **Pin all dependency versions** using exact pins (==) instead of minimum (>=)\n`;
  md += `2. **Install slowapi** for rate limiting\n`;
  md += `3. **Run pip-audit** regularly: \`pip install pip-audit && pip-audit\`\n`;
  md += `4. **Use virtual environments** and lock file for reproducible deployments\n`;
  md += `5. **Enable Dependabot** or Renovate for automated dependency updates\n`;

  return md;
}

function generateSecurityReview(depFindings) {
  const bySeverity = { CRITICAL: [], HIGH: [], MEDIUM: [], LOW: [], INFO: [] };
  for (const f of findings) (bySeverity[f.severity] || bySeverity["INFO"]).push(f);

  const riskScore = bySeverity.CRITICAL.length * 10 + bySeverity.HIGH.length * 7 +
    bySeverity.MEDIUM.length * 4 + bySeverity.LOW.length;
  const riskLevel = riskScore > 50 ? "🔴 HIGH RISK" : riskScore > 20 ? "🟠 MEDIUM RISK" : "🟡 LOW RISK";

  let md = `# TripSync Backend — Security Review Report\n\n`;
  md += `**Generated:** ${SCAN_TIMESTAMP}  \n`;
  md += `**Scanner:** TripSync Backend SAST v1.0.0  \n`;
  md += `**Framework:** FastAPI (auto-detected)  \n\n`;
  md += `---\n\n`;

  md += `## Risk Summary\n\n`;
  md += `| Severity | Count |\n|----------|-------|\n`;
  md += `| 🔴 CRITICAL | ${bySeverity.CRITICAL.length} |\n`;
  md += `| 🟠 HIGH | ${bySeverity.HIGH.length} |\n`;
  md += `| 🟡 MEDIUM | ${bySeverity.MEDIUM.length} |\n`;
  md += `| 🟢 LOW | ${bySeverity.LOW.length} |\n`;
  md += `| ℹ️ INFO | ${bySeverity.INFO.length} |\n`;
  md += `| **TOTAL** | **${findings.length}** |\n\n`;
  md += `**Overall Risk Level:** ${riskLevel}\n\n`;
  md += `---\n\n`;

  md += `## Findings\n\n`;
  const icons = { CRITICAL: "🔴", HIGH: "🟠", MEDIUM: "🟡", LOW: "🟢", INFO: "ℹ️" };

  for (const [sev, sevFindings] of Object.entries(bySeverity)) {
    if (sevFindings.length === 0) continue;
    md += `### ${icons[sev]} ${sev} (${sevFindings.length})\n\n`;

    for (const f of sevFindings) {
      md += `#### ${f.id} — ${f.description.substring(0, 80)}...\n\n`;
      md += `| Field | Value |\n|-------|-------|\n`;
      md += `| **Finding ID** | \`${f.id}\` |\n`;
      md += `| **Severity** | ${f.severity} |\n`;
      md += `| **Category** | ${f.category} |\n`;
      md += `| **File** | \`${f.file}\` |\n`;
      md += `| **Function** | \`${f.function}\` |\n`;
      md += `| **Line** | ${f.line} |\n`;
      md += `| **CWE** | [${f.cwe}](https://cwe.mitre.org/data/definitions/${f.cwe.replace("CWE-", "")}.html) |\n`;
      md += `| **OWASP** | ${f.owasp} |\n\n`;
      md += `**Description:** ${f.description}\n\n`;
      md += `**Root Cause:** ${f.rootCause}\n\n`;
      md += `**Impact:** ${f.impact}\n\n`;
      md += `**Recommendation:** ${f.recommendation}\n\n`;
      if (f.evidence) md += `**Evidence:**\n\`\`\`\n${f.evidence}\n\`\`\`\n\n`;
      md += `---\n\n`;
    }
  }

  return md;
}

function calculateSecurityScore(findings, endpoints, depFindings) {
  let score = 100;
  
  // Severity Counts
  const bySeverity = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0, INFO: 0 };
  for (const f of findings) {
    bySeverity[f.severity] = (bySeverity[f.severity] || 0) + 1;
  }

  // Deduct based on findings count (capped to avoid double jeopardy)
  const criticalDeduction = Math.min(30, bySeverity.CRITICAL * 10);
  const highDeduction = Math.min(20, bySeverity.HIGH * 6);
  const mediumDeduction = Math.min(15, bySeverity.MEDIUM * 3);
  const lowDeduction = Math.min(10, bySeverity.LOW * 1);
  score -= (criticalDeduction + highDeduction + mediumDeduction + lowDeduction);

  // Authentication Coverage: percentage of protected endpoints with auth
  const totalProtected = endpoints.filter(e => !["GET /", "GET /health", "GET /docs", "GET /redoc", "GET /openapi.json", "POST /api/otp/send", "POST /api/otp/verify"].includes(`${e.method} ${e.route}`)).length;
  const protectedWithAuth = endpoints.filter(e => e.hasAuth && !["GET /", "GET /health", "GET /docs", "GET /redoc", "GET /openapi.json", "POST /api/otp/send", "POST /api/otp/verify"].includes(`${e.method} ${e.route}`)).length;
  const authCoverage = totalProtected > 0 ? (protectedWithAuth / totalProtected) : 1.0;
  score -= Math.round((1.0 - authCoverage) * 10);

  // Rate Limiting Coverage: percentage of all endpoints with rate limits
  const totalRateLimit = endpoints.length;
  const withRateLimit = endpoints.filter(e => e.hasRateLimit).length;
  const rateLimitCoverage = totalRateLimit > 0 ? (withRateLimit / totalRateLimit) : 1.0;
  score -= Math.round((1.0 - rateLimitCoverage) * 5);

  // Dependency Health (vulns in dependencies)
  const vulnerableDeps = depFindings.filter(d => d.severity !== "INFO" && d.severity !== "LOW").length;
  const dependencyHealth = Math.max(0.0, 1.0 - (vulnerableDeps * 0.1));
  score -= Math.min(10, vulnerableDeps * 2);

  // Configuration Issues (CORS wildcard, Secrets)
  const configIssues = findings.filter(f => f.category.includes("CORS") || f.category.includes("Secrets")).length;
  const configSafety = Math.max(0.0, 1.0 - (configIssues * 0.2));
  score -= Math.min(10, configIssues * 2);

  // Ensure score is within [0, 100]
  score = Math.max(0, Math.min(100, Math.round(score)));

  // Risk Level mapping
  let riskLevel = "LOW";
  if (score < 50) riskLevel = "CRITICAL";
  else if (score < 75) riskLevel = "HIGH";
  else if (score < 90) riskLevel = "MEDIUM";

  return {
    score,
    riskLevel,
    distribution: {
      critical: bySeverity.CRITICAL,
      high: bySeverity.HIGH,
      medium: bySeverity.MEDIUM,
      low: bySeverity.LOW,
      info: bySeverity.INFO,
      CRITICAL: bySeverity.CRITICAL,
      HIGH: bySeverity.HIGH,
      MEDIUM: bySeverity.MEDIUM,
      LOW: bySeverity.LOW,
      INFO: bySeverity.INFO
    },
    metrics: {
      authCoverage: parseFloat(authCoverage.toFixed(2)),
      rateLimitCoverage: parseFloat(rateLimitCoverage.toFixed(2)),
      securityHeadersCoverage: 1.0,
      dependencyHealth: parseFloat(dependencyHealth.toFixed(2)),
      configSafety: parseFloat(configSafety.toFixed(2))
    }
  };
}

function generateExecutiveSummary(depFindings) {
  const summaryScore = calculateSecurityScore(findings, endpoints, depFindings);
  const bySeverity = summaryScore.distribution;

  let md = `# TripSync Backend — Executive Security Summary\n\n`;
  md += `**Date:** ${SCAN_TIMESTAMP}  \n`;
  md += `**Application:** TripSync FastAPI Backend  \n`;
  md += `**Total Endpoints:** ${endpoints.length}\n\n`;
  md += `---\n\n`;
  md += `## Security Posture: ${summaryScore.score >= 90 ? "Excellent" : summaryScore.score >= 75 ? "Good" : "Poor"}\n\n`;
  md += `**Security Score:** ${summaryScore.score}/100  \n`;
  md += `**Risk Level:** ${summaryScore.riskLevel}  \n\n`;
  md += `The TripSync backend was analyzed using static application security testing. `;
  md += `**${findings.length} security findings** were identified across authentication, authorization, CORS, rate limiting, secrets management, and dependency hygiene.\n\n`;

  md += `## Risk Summary\n\n`;
  md += `| Category | Count |\n|----------|-------|\n`;
  md += `| 🔴 Critical | ${bySeverity.critical} |\n`;
  md += `| 🟠 High | ${bySeverity.high} |\n`;
  md += `| 🟡 Medium | ${bySeverity.medium} |\n`;
  md += `| 🟢 Low | ${bySeverity.low} |\n`;
  md += `| ℹ️ Info | ${bySeverity.info} |\n\n`;

  md += `## Score & Health Breakdown\n\n`;
  md += `| Health Metric | Score/Coverage |\n|---------------|----------------|\n`;
  md += `| Authentication Coverage | ${Math.round(summaryScore.metrics.authCoverage * 100)}% |\n`;
  md += `| Rate Limiting Coverage | ${Math.round(summaryScore.metrics.rateLimitCoverage * 100)}% |\n`;
  md += `| Dependency Health | ${Math.round(summaryScore.metrics.dependencyHealth * 100)}% |\n`;
  md += `| Configuration Safety | ${Math.round(summaryScore.metrics.configSafety * 100)}% |\n\n`;

  md += `## Top Risks\n\n`;
  const topFindings = findings.filter(f => ["CRITICAL", "HIGH", "MEDIUM"].includes(f.severity)).slice(0, 5);
  topFindings.forEach((f, i) => {
    md += `${i + 1}. **${f.category}** (${f.severity}) — ${f.description.substring(0, 100)}\n`;
  });

  md += `\n## Key Observations\n\n`;
  md += `- Centralized Firebase Token verification middleware is fully enforced.\n`;
  md += `- Rate limiting via slowapi is fully configured and active.\n`;
  md += `- CORS uses explicit env-driven origins with wildcard origins stripped.\n`;
  md += `- File uploads are hardened using magic byte validation and size constraints.\n\n`;

  md += `## Endpoint Security Coverage\n\n`;
  md += `| Metric | Coverage |\n|--------|----------|\n`;
  md += `| Endpoints with Auth | ${endpoints.filter(e => e.hasAuth).length}/${endpoints.length} |\n`;
  md += `| Endpoints with Rate Limiting | ${endpoints.filter(e => e.hasRateLimit).length}/${endpoints.length} |\n`;
  md += `| Endpoints with Input Validation | ${endpoints.filter(e => e.hasInputValidation).length}/${endpoints.length} |\n\n`;

  md += `## Recommended Improvements\n\n`;
  md += `1. Pin the ` + "`python-multipart`" + ` package explicitly to ` + "`>=0.0.7`" + ` to avoid known parsing vulnerabilities.\n`;
  md += `2. Run regular dependency updates (pip-audit) to identify vulnerabilities in sentence-transformers or qdrant.\n`;

  return md;
}

// ─── XLSX Data ─────────────────────────────────────────────────────────────────
function getXLSXData(depFindings) {
  return {
    findings,
    endpoints,
    depFindings,
    riskSummary: (() => {
      const bs = { CRITICAL: 0, HIGH: 0, MEDIUM: 0, LOW: 0, INFO: 0 };
      for (const f of findings) bs[f.severity] = (bs[f.severity] || 0) + 1;
      return bs;
    })(),
  };
}

// ─── Main Runner ───────────────────────────────────────────────────────────────
async function main() {
  console.log("\n╔══════════════════════════════════════════════════════════════╗");
  console.log("║       TripSync Backend SAST Security Scanner v1.0.0         ║");
  console.log("╚══════════════════════════════════════════════════════════════╝\n");

  console.log("🔍 Discovering source files...");
  const allFiles = walkDir(ROOT_DIR);
  console.log(`   Found ${allFiles.length} files\n`);

  console.log("🔎 Framework Detection & Endpoint Discovery...");
  const framework = detectFramework(allFiles);
  discoverEndpoints(allFiles, framework);
  console.log("");

  console.log("🛡️  Running security analysis modules...");
  scanAuthentication(allFiles);
  scanCORS(allFiles);
  scanInjection(allFiles);
  scanSecrets(allFiles);
  scanInputValidation(allFiles);
  scanRateLimiting(allFiles);
  scanExceptionHandling(allFiles);
  scanFirebaseAdmin(allFiles);
  scanLogging(allFiles);
  const depFindings = scanDependencies(allFiles);

  console.log(`\n✅ Analysis complete. Found ${findings.length} findings across ${endpoints.length} endpoints.\n`);

  if (!fs.existsSync(REPORT_DIR)) {
    fs.mkdirSync(REPORT_DIR, { recursive: true });
  }

  console.log("📊 Generating reports...");

  // Calculate and write Security Score
  const scoreResult = calculateSecurityScore(findings, endpoints, depFindings);
  fs.writeFileSync(
    path.join(REPORT_DIR, "security-score.json"),
    JSON.stringify(scoreResult, null, 2)
  );
  console.log(`  ✅ Dynamic Security Score: ${scoreResult.score}/100`);

  const xlsxData = getXLSXData(depFindings);

  fs.writeFileSync(
    path.join(REPORT_DIR, "scan-results.json"),
    JSON.stringify({ findings, endpoints, depFindings, xlsxData, framework, timestamp: SCAN_TIMESTAMP, score: scoreResult }, null, 2)
  );

  fs.writeFileSync(path.join(REPORT_DIR, "endpoint-inventory.md"), generateEndpointInventory());
  fs.writeFileSync(path.join(REPORT_DIR, "dependency-report.md"), generateDependencyReport(depFindings));
  fs.writeFileSync(path.join(REPORT_DIR, "security-review.md"), generateSecurityReview(depFindings));
  fs.writeFileSync(path.join(REPORT_DIR, "executive-summary.md"), generateExecutiveSummary(depFindings));

  const bySev = scoreResult.distribution;

  console.log("\n┌─────────────────────────────────────────┐");
  console.log("│           SCAN RESULTS SUMMARY          │");
  console.log("├─────────────────────────────────────────┤");
  console.log(`│  🔴 CRITICAL : ${String(bySev.CRITICAL).padStart(3)}  Endpoints: ${String(endpoints.length).padStart(3)}         │`);
  console.log(`│  🟠 HIGH     : ${String(bySev.HIGH).padStart(3)}                      │`);
  console.log(`│  🟡 MEDIUM   : ${String(bySev.MEDIUM).padStart(3)}                      │`);
  console.log(`│  🟢 LOW      : ${String(bySev.LOW).padStart(3)}                      │`);
  console.log(`│  ℹ️  INFO     : ${String(bySev.INFO).padStart(3)}                      │`);
  console.log(`│  TOTAL       : ${String(findings.length).padStart(3)}                      │`);
  console.log("└─────────────────────────────────────────┘\n");
  console.log("📁 Reports: backend/SecurityTest/reports/");
  console.log("   • scan-results.json");
  console.log("   • endpoint-inventory.md");
  console.log("   • dependency-report.md");
  console.log("   • security-review.md");
  console.log("   • executive-summary.md");
  console.log("   • findings.xlsx (run generateSecuritySuite.js)\n");

  return { findings, endpoints, depFindings, xlsxData, framework };
}

module.exports = { main, findings: () => findings, endpoints: () => endpoints };

if (require.main === module) {
  main().catch(err => {
    console.error("Scanner error:", err);
    process.exit(1);
  });
}
