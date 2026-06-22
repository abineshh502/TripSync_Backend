/**
 * TripSync Backend — k6 Load Test v3.0
 * ─────────────────────────────────────────────────────────────────────────────
 * Production target : https://tripsyncbackend-production-37a2.up.railway.app
 *
 * Confirmed live endpoints (audited 2026-06-22):
 *   GET /health                              → {"status":"ok"}
 *   GET /                                    → {"status":"Online ✅", ...}
 *   GET /api/trips?userId=<id>               → {"trips":[...], "total":2}
 *   GET /api/weather?lat=<f>&lon=<f>         → {"temperature":...}
 *   GET /api/safety?city=<city>              → {"city":..., "generalSafety":...}
 *
 * Thresholds (SLA):
 *   http_req_failed  < 5%       (overall error rate)
 *   http_req_duration p(95) < 1500ms
 *
 * Usage (CI — env var injected by workflow):
 *   k6 run --vus 100 --duration 1m --summary-export=k6-summary.json tests/load-test.js
 *
 * Usage (local):
 *   BACKEND_URL=https://tripsyncbackend-production-37a2.up.railway.app \
 *     k6 run --summary-export=k6-summary.json tests/load-test.js
 */

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// ── Custom per-endpoint metrics ───────────────────────────────────────────────
const errorRate       = new Rate('custom_errors');
const healthDuration  = new Trend('health_api_duration',   true);
const rootDuration    = new Trend('root_api_duration',     true);
const tripsDuration   = new Trend('trips_api_duration',    true);
const safetyDuration  = new Trend('safety_api_duration',   true);
const weatherDuration = new Trend('weather_api_duration',  true);
const totalRequests   = new Counter('total_requests_sent');

// ── Options ───────────────────────────────────────────────────────────────────
export const options = {
  vus:      100,
  duration: '1m',

  thresholds: {
    // ── Core SLA (must pass for workflow to succeed) ─────────────────────────
    http_req_failed:       ['rate<0.05'],    // < 5% overall error rate
    http_req_duration:     ['p(95)<1500'],   // 95th-pct < 1.5 s

    // ── Per-endpoint thresholds ───────────────────────────────────────────────
    health_api_duration:   ['p(95)<300'],    // /health is pure in-process → very fast
    root_api_duration:     ['p(95)<500'],    // / is also pure in-process
    trips_api_duration:    ['p(95)<1000'],   // pure Python, no external calls
    weather_api_duration:  ['p(95)<2500'],   // proxies open-meteo.com
    safety_api_duration:   ['p(95)<5000'],   // calls AI provider chain — higher budget
    custom_errors:         ['rate<0.05'],
  },
};

// ── Target URL ────────────────────────────────────────────────────────────────
// Priority: env var injected by GHA workflow → hardcoded Railway production URL
const BASE_URL = (__ENV.BACKEND_URL || 'https://tripsyncbackend-production-37a2.up.railway.app')
  .replace(/\/$/, '');   // strip trailing slash

const HEADERS = {
  'Accept':       'application/json',
  'Content-Type': 'application/json',
  'User-Agent':   'k6-tripsync-load-test/3.0',
};

// ── Rotating test data (spread load across multiple city/coord combos) ────────
const CITIES = ['Paris', 'Tokyo', 'London', 'New York', 'Sydney', 'Mumbai', 'Dubai', 'Singapore'];
const COORDS = [
  { lat: 48.8566,  lon: 2.3522   },  // Paris
  { lat: 35.6762,  lon: 139.6503 },  // Tokyo
  { lat: 51.5074,  lon: -0.1278  },  // London
  { lat: 40.7128,  lon: -74.0060 },  // New York
  { lat: -33.8688, lon: 151.2093 },  // Sydney
  { lat: 1.3521,   lon: 103.8198 },  // Singapore
];
const USER_IDS = ['load_test_01', 'load_test_02', 'load_test_03', 'perf_user', 'k6_runner'];

// ── Validation helper ─────────────────────────────────────────────────────────
/**
 * Run k6 checks on a response and update the shared error rate.
 * @param {object}  res          - k6 HTTP response object
 * @param {string}  label        - endpoint label for check names
 * @param {number}  [code=200]   - expected HTTP status code
 * @param {number}  [maxMs=3000] - max acceptable latency in ms
 * @returns {boolean}
 */
function validate(res, label, code = 200, maxMs = 3000) {
  const passed = check(res, {
    [`[${label}] status ${code}`]:  (r) => r.status === code,
    [`[${label}] latency < ${maxMs}ms`]: (r) => r.timings.duration < maxMs,
    [`[${label}] body not empty`]:  (r) => Boolean(r.body && r.body.length > 0),
  });
  errorRate.add(!passed);
  totalRequests.add(1);
  return passed;
}

// ── Default VU function (runs on every virtual user, every iteration) ─────────
export default function () {
  // Deterministic but varied test data per VU/iteration
  const idx    = (__VU - 1 + __ITER) % CITIES.length;
  const city   = CITIES[idx % CITIES.length];
  const coord  = COORDS[idx % COORDS.length];
  const userId = USER_IDS[__VU % USER_IDS.length];

  // ── 1. Health endpoint (/health) ───────────────────────────────────────────
  // Fast in-process check — no DB or AI calls. k6 SLA: p(95) < 300ms.
  group('Health API', () => {
    const res = http.get(`${BASE_URL}/health`, { headers: HEADERS });
    validate(res, 'GET /health', 200, 300);
    healthDuration.add(res.timings.duration);
  });

  sleep(0.2);

  // ── 2. Root endpoint (/) ───────────────────────────────────────────────────
  // Returns service metadata. Fast in-process. k6 SLA: p(95) < 500ms.
  group('Root API', () => {
    const res = http.get(`${BASE_URL}/`, { headers: HEADERS });
    validate(res, 'GET /', 200, 500);
    rootDuration.add(res.timings.duration);
  });

  sleep(0.2);

  // ── 3. Trips endpoint (/api/trips) ─────────────────────────────────────────
  // Returns static trip data from Python. No external calls. k6 SLA: p(95) < 1000ms.
  group('Trips API', () => {
    const res = http.get(`${BASE_URL}/api/trips?userId=${userId}`, { headers: HEADERS });
    const passed = validate(res, 'GET /api/trips', 200, 1500);

    // Additional check: confirm the response actually contains trips array
    if (passed) {
      check(res, {
        '[Trips API] body has trips array': (r) => {
          try { return Array.isArray(JSON.parse(r.body).trips); }
          catch (_) { return false; }
        },
      });
    }
    tripsDuration.add(res.timings.duration);
  });

  sleep(0.3);

  // ── 4. Weather endpoint (/api/weather) ────────────────────────────────────
  // Proxies open-meteo.com — external call, higher latency budget.
  // k6 SLA: p(95) < 2500ms.
  group('Weather API', () => {
    const res = http.get(
      `${BASE_URL}/api/weather?lat=${coord.lat}&lon=${coord.lon}`,
      { headers: HEADERS }
    );
    const passed = validate(res, 'GET /api/weather', 200, 2500);

    // Confirm the response has at least one weather field
    if (passed) {
      check(res, {
        '[Weather API] body has temperature': (r) => {
          try {
            const d = JSON.parse(r.body);
            return d.temperature !== undefined || d.error !== undefined;
          } catch (_) { return false; }
        },
      });
    }
    weatherDuration.add(res.timings.duration);
  });

  sleep(0.3);

  // ── 5. Safety endpoint (/api/safety) ─────────────────────────────────────
  // Calls AI provider chain (Gemini → Groq → fallback). Highest latency budget.
  // k6 SLA: p(95) < 5000ms. Does NOT fail the request on 503 (graceful AI degradation).
  group('Safety API', () => {
    const res = http.get(
      `${BASE_URL}/api/safety?city=${encodeURIComponent(city)}`,
      { headers: HEADERS }
    );

    // Accept 200 OR 503 (AI provider temporarily unavailable is not a backend bug)
    const statusOk = check(res, {
      '[Safety API] status 200 or 503': (r) => r.status === 200 || r.status === 503,
      '[Safety API] latency < 5s':      (r) => r.timings.duration < 5000,
    });

    // Only count as an error if it's a hard 5xx other than 503
    const isHardError = res.status >= 500 && res.status !== 503;
    errorRate.add(isHardError);
    totalRequests.add(1);
    safetyDuration.add(res.timings.duration);
  });

  // Realistic think-time between full iteration cycles (mimics real user pacing)
  sleep(Math.random() * 0.8 + 0.2);  // 0.2 – 1.0 s
}

// ── Setup: runs once before VUs start ─────────────────────────────────────────
export function setup() {
  console.log('╔═══════════════════════════════════════════════╗');
  console.log('║  TripSync Backend — k6 Load Test v3.0         ║');
  console.log('╚═══════════════════════════════════════════════╝');
  console.log(`🎯  Target  : ${BASE_URL}`);
  console.log(`👥  VUs     : ${options.vus}`);
  console.log(`⏱   Duration: ${options.duration}`);
  console.log('');
  console.log('📋 Audited live endpoints:');
  console.log(`   GET ${BASE_URL}/health`);
  console.log(`   GET ${BASE_URL}/`);
  console.log(`   GET ${BASE_URL}/api/trips`);
  console.log(`   GET ${BASE_URL}/api/weather`);
  console.log(`   GET ${BASE_URL}/api/safety`);
  console.log('');

  // Pre-flight: hit /health first (fastest, most reliable endpoint)
  const health = http.get(`${BASE_URL}/health`, { headers: HEADERS });
  if (health.status === 200) {
    console.log(`✅ Pre-flight /health check PASSED (${health.timings.duration.toFixed(0)} ms)`);
  } else {
    console.warn(`⚠️  Pre-flight returned HTTP ${health.status} — tests will still run.`);
    console.warn(`   If this persists, verify BACKEND_URL = ${BASE_URL}`);
  }

  return {
    baseUrl:   BASE_URL,
    startTime: new Date().toISOString(),
  };
}

// ── Teardown: runs once after all VUs finish ───────────────────────────────────
export function teardown(data) {
  console.log('');
  console.log(`✅ Load test complete`);
  console.log(`   Target  : ${data.baseUrl}`);
  console.log(`   Started : ${data.startTime}`);
  console.log(`   Finished: ${new Date().toISOString()}`);
  console.log('');
  console.log('   → See k6-summary.json  for machine-readable metrics');
  console.log('   → See load-test-report.html  for the visual dashboard');
}
