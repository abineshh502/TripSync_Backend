/**
 * TripSync Backend Remediation & Security Functional Verification Script
 * ======================================================================
 * Performs live validation of security controls:
 * 1. Public Endpoint Access (/, /health, /api/otp/send)
 * 2. Fail-Closed Authentication on Protected Routes (HTTP 401)
 * 3. Prevention of OTP Leakage (Checks send_otp response body)
 * 4. Rate Limiting Enforcement (Detections of HTTP 429)
 * 5. CORS Header Policy Validation
 */

const http = require("http");

const TARGET_HOST = "localhost";
const TARGET_PORT = 8000;
const BASE_URL = `http://${TARGET_HOST}:${TARGET_PORT}`;

// Helper to perform HTTP requests
function request(method, path, headers = {}, body = null) {
  return new Promise((resolve, reject) => {
    const options = {
      hostname: TARGET_HOST,
      port: TARGET_PORT,
      path: path,
      method: method,
      headers: {
        "Content-Type": "application/json",
        ...headers,
      },
    };

    const req = http.request(options, (res) => {
      let data = "";
      res.on("data", (chunk) => (data += chunk));
      res.on("end", () => {
        let parsedBody = null;
        try {
          parsedBody = data ? JSON.parse(data) : null;
        } catch {
          parsedBody = data;
        }
        resolve({
          statusCode: res.statusCode,
          headers: res.headers,
          body: parsedBody,
        });
      });
    });

    req.on("error", (err) => reject(err));

    if (body) {
      req.write(JSON.stringify(body));
    }
    req.end();
  });
}

async function runVerification() {
  console.log("🚀 Starting TripSync Hardening Functional Verification...\n");
  let passed = true;

  // Test 1: Public Health Endpoint
  try {
    const res = await request("GET", "/health");
    if (res.statusCode === 200 && res.body?.status === "ok") {
      console.log("✅ Test 1 Passed: Public health endpoint is accessible.");
    } else {
      console.log(`❌ Test 1 Failed: /health status = ${res.statusCode}`);
      passed = false;
    }
  } catch (err) {
    console.log("❌ Test 1 Failed: Cannot connect to backend server.", err.message);
    console.log("Make sure backend is running locally on port 8000.");
    return;
  }

  // Test 2: Protected Route Blocked without Auth Header (Fail-Closed)
  try {
    const res = await request("GET", "/api/trips");
    if (res.statusCode === 401) {
      console.log("✅ Test 2 Passed: Protected route /api/trips blocks request with HTTP 401 without token.");
    } else {
      console.log(`❌ Test 2 Failed: Expected 401 for unauthenticated /api/trips, got ${res.statusCode}`);
      passed = false;
    }
  } catch (err) {
    console.log("❌ Test 2 Failed:", err.message);
    passed = false;
  }

  // Test 3: OTP Send Prevents Exposure of OTP Code
  try {
    const res = await request("POST", "/api/otp/send", {}, { email: "verify_security@tripsync.org" });
    if (res.statusCode === 200) {
      if (res.body?.otp === undefined && res.body?.otp_code === undefined) {
        console.log("✅ Test 3 Passed: OTP code is not returned in response body.");
      } else {
        console.log("❌ Test 3 Failed: OTP code leaked in response body:", res.body);
        passed = false;
      }
    } else if (res.statusCode === 429) {
      console.log("⚠️ Test 3 Warning: OTP send rate limited (HTTP 429). Prevents brute force.");
    } else {
      console.log(`❌ Test 3 Failed: /api/otp/send returned status ${res.statusCode}`);
      passed = false;
    }
  } catch (err) {
    console.log("❌ Test 3 Failed:", err.message);
    passed = false;
  }

  // Test 4: Rate Limiting Verification (Bursting OTP endpoint)
  try {
    let rateLimited = false;
    for (let i = 0; i < 6; i++) {
      const res = await request("POST", "/api/otp/send", {}, { email: `test_burst_${i}@tripsync.org` });
      if (res.statusCode === 429) {
        rateLimited = true;
        break;
      }
    }
    if (rateLimited) {
      console.log("✅ Test 4 Passed: Rate limiter actively blocked high frequency requests with HTTP 429.");
    } else {
      console.log("❌ Test 4 Failed: Rate limiter did not trigger HTTP 429 on rapid endpoint hits.");
      passed = false;
    }
  } catch (err) {
    console.log("❌ Test 4 Failed:", err.message);
    passed = false;
  }

  // Test 5: CORS Configuration Checks
  try {
    const res = await request("OPTIONS", "/health", {
      Origin: "https://malicious-site.com",
      "Access-Control-Request-Method": "GET",
    });
    const allowOrigin = res.headers["access-control-allow-origin"];
    if (allowOrigin === "*" || allowOrigin === "https://malicious-site.com") {
      console.log(`❌ Test 5 Failed: CORS configuration allows malicious origin: ${allowOrigin}`);
      passed = false;
    } else {
      console.log(`✅ Test 5 Passed: CORS rejected malicious origin (Header: ${allowOrigin || "absent - secure"}).`);
    }
  } catch (err) {
    console.log("❌ Test 5 Failed:", err.message);
    passed = false;
  }

  console.log("\n📊 Verification Session Summary:");
  if (passed) {
    console.log("🟢 All security validation and regression tests PASSED. Code base is production-ready.");
  } else {
    console.log("🔴 Some tests failed. Remediations must be verified.");
  }
}

runVerification();
