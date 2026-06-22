/**
 * TripSync Backend – k6 Load Test
 * ─────────────────────────────────────────────────────────────────────────────
 * Tests all backend REST APIs with 100 Virtual Users for 1 minute.
 *
 * Endpoints under test:
 *   GET  /                            (health check)
 *   GET  /api/trips?userId=load_test
 *   GET  /api/safety?city=<city>
 *   GET  /api/weather?lat=<lat>&lon=<lon>
 *
 * Thresholds (SLA):
 *   http_req_failed  < 5 %
 *   http_req_duration p(95) < 1 500 ms
 *
 * Usage (local):
 *   BACKEND_URL=http://localhost:8000 k6 run --summary-export=k6-summary.json tests/load-test.js
 *
 * Usage (CI – set via env / secret):
 *   k6 run --vus 100 --duration 1m --summary-export=k6-summary.json tests/load-test.js
 */

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// ── Custom per-endpoint metrics (visible in summary and HTML report) ───────────
const errorRate        = new Rate('custom_errors');
const healthDuration   = new Trend('health_api_duration',   true);
const tripsDuration    = new Trend('trips_api_duration',    true);
const safetyDuration   = new Trend('safety_api_duration',   true);
const weatherDuration  = new Trend('weather_api_duration',  true);
const totalRequests    = new Counter('total_requests_sent');

// ── Test configuration ────────────────────────────────────────────────────────
export const options = {
  vus:      100,
  duration: '1m',

  thresholds: {
    // Core SLA thresholds
    http_req_failed:        ['rate<0.05'],     // < 5 % error rate
    http_req_duration:      ['p(95)<1500'],    // 95th-pct < 1.5 s

    // Per-endpoint thresholds
    health_api_duration:    ['p(95)<500'],     // health check tighter SLA
    trips_api_duration:     ['p(95)<1500'],
    weather_api_duration:   ['p(95)<2000'],    // weather calls external API

    // Custom error rate mirrors http_req_failed
    custom_errors:          ['rate<0.05'],
  },
};

// ── Resolve target URL ────────────────────────────────────────────────────────
const BASE_URL = __ENV.BACKEND_URL
  ? __ENV.BACKEND_URL.replace(/\/$/, '')   // strip trailing slash
  : 'http://localhost:8000';

const HEADERS = {
  'Accept':     'application/json',
  'User-Agent': 'k6-tripsync-load-test/2.0',
};

// Rotating test data to spread load realistically
const CITIES   = ['Paris', 'Tokyo', 'London', 'New York', 'Sydney', 'Mumbai', 'Dubai'];
const COORDS   = [
  { lat: 48.8566,  lon: 2.3522   },  // Paris
  { lat: 35.6762,  lon: 139.6503 },  // Tokyo
  { lat: 51.5074,  lon: -0.1278  },  // London
  { lat: 40.7128,  lon: -74.0060 },  // New York
  { lat: -33.8688, lon: 151.2093 },  // Sydney
];

// ── Validation helper ─────────────────────────────────────────────────────────
function validate(res, label, expectedCode = 200) {
  const passed = check(res, {
    [`[${label}] status ${expectedCode}`]:   (r) => r.status === expectedCode,
    [`[${label}] latency < 3s`]:             (r) => r.timings.duration < 3000,
    [`[${label}] body not empty`]:           (r) => r.body && r.body.length > 0,
  });
  errorRate.add(!passed);
  totalRequests.add(1);
  return passed;
}

// ── Default VU function ───────────────────────────────────────────────────────
export default function () {
  // Pick rotating test data for this iteration
  const vu      = __VU;
  const iter    = __ITER;
  const city    = CITIES[(vu + iter) % CITIES.length];
  const coord   = COORDS[(vu + iter) % COORDS.length];

  // ── Health API ─────────────────────────────────────────────────────────────
  group('Health API', () => {
    const res = http.get(`${BASE_URL}/`, { headers: HEADERS });
    validate(res, 'GET /');
    healthDuration.add(res.timings.duration);
  });

  sleep(0.3);

  // ── Trips API ──────────────────────────────────────────────────────────────
  group('Trips API', () => {
    const res = http.get(
      `${BASE_URL}/api/trips?userId=load_test_vu${vu}`,
      { headers: HEADERS }
    );
    validate(res, 'GET /api/trips');
    tripsDuration.add(res.timings.duration);
  });

  sleep(0.3);

  // ── Safety API ─────────────────────────────────────────────────────────────
  group('Safety API', () => {
    const res = http.get(
      `${BASE_URL}/api/safety?city=${encodeURIComponent(city)}`,
      { headers: HEADERS }
    );
    // Safety calls an external AI – accept 200 or 503 (service unavailable)
    check(res, {
      '[Safety API] status 200 or 503': (r) => r.status === 200 || r.status === 503,
      '[Safety API] latency < 5s':      (r) => r.timings.duration < 5000,
    });
    safetyDuration.add(res.timings.duration);
    totalRequests.add(1);
  });

  sleep(0.3);

  // ── Weather API ────────────────────────────────────────────────────────────
  group('Weather API', () => {
    const res = http.get(
      `${BASE_URL}/api/weather?lat=${coord.lat}&lon=${coord.lon}`,
      { headers: HEADERS }
    );
    validate(res, 'GET /api/weather');
    weatherDuration.add(res.timings.duration);
  });

  // Realistic think-time between full page iterations
  sleep(Math.random() * 1 + 0.5);  // 0.5 – 1.5 s
}

// ── Setup – runs once before VUs start ────────────────────────────────────────
export function setup() {
  console.log('╔══════════════════════════════════════════╗');
  console.log('║   TripSync Backend — k6 Load Test v2.0  ║');
  console.log('╚══════════════════════════════════════════╝');
  console.log(`🎯 Target  : ${BASE_URL}`);
  console.log(`👥 VUs     : ${options.vus}`);
  console.log(`⏱  Duration: ${options.duration}`);
  console.log('');

  const health = http.get(`${BASE_URL}/`, { headers: HEADERS });
  if (health.status === 200) {
    console.log(`✅ Pre-flight check PASSED (${health.timings.duration.toFixed(0)} ms)`);
  } else {
    console.warn(`⚠️  Pre-flight check returned HTTP ${health.status} — test continues.`);
  }

  return { baseUrl: BASE_URL, startTime: new Date().toISOString() };
}

// ── Teardown – runs once after all VUs finish ─────────────────────────────────
export function teardown(data) {
  console.log('');
  console.log(`✅ Load test complete — target was ${data.baseUrl}`);
  console.log(`   Started : ${data.startTime}`);
  console.log(`   Finished: ${new Date().toISOString()}`);
  console.log('   → Check k6-summary.json and load-test-report.html for full metrics.');
}
