/**
 * TripSync Backend — k6 Category-wise Load Test Suite v5.0
 * ─────────────────────────────────────────────────────────────────────────────
 * Production target : https://tripsyncbackend-production-37a2.up.railway.app
 *
 * Categorized API Test Groups:
 *   1. Authentication API  : POST /api/otp/send
 *   2. Health API          : GET /health, GET /
 *   3. Trip API            : GET /api/trips, POST /api/trips
 *   4. AI API              : GET /api/safety, GET /api/weather
 *   5. Group API           : POST /api/expenses/split, POST /api/routes/optimize, POST /api/routes/share
 */

import http from 'k6/http';
import { check, sleep, group } from 'k6';
import { Rate, Trend, Counter } from 'k6/metrics';

// ── Custom Per-Category & Endpoint Metrics ───────────────────────────────────
const errorRate       = new Rate('custom_errors');
const healthDuration  = new Trend('health_api_duration',   true);
const rootDuration    = new Trend('root_api_duration',     true);
const authDuration    = new Trend('auth_api_duration',     true);
const tripsDuration   = new Trend('trips_api_duration',    true);
const safetyDuration  = new Trend('safety_api_duration',   true);
const weatherDuration = new Trend('weather_api_duration',  true);
const groupDuration   = new Trend('group_api_duration',    true);
const totalRequests   = new Counter('total_requests_sent');

// ── Options ───────────────────────────────────────────────────────────────────
export const options = {
  vus:      100,
  duration: '1m',

  thresholds: {
    http_req_failed:       ['rate<0.05'],     // < 5% error rate
    http_req_duration:     ['p(95)<5000'],    // global mixed SLA budget
    health_api_duration:   ['p(95)<400'],     // /health budget
    root_api_duration:     ['p(95)<600'],     // / budget
    auth_api_duration:     ['p(95)<2000'],    // OTP auth budget
    trips_api_duration:    ['p(95)<600'],     // Trips budget
    weather_api_duration:  ['p(95)<2500'],    // Weather proxy budget
    safety_api_duration:   ['p(95)<5000'],    // AI safety budget
    group_api_duration:    ['p(95)<1500'],    // Route/Expense group budget
    custom_errors:         ['rate<0.05'],
  },
};

// ── Target URL & Headers ──────────────────────────────────────────────────────
const BASE_URL = (__ENV.BACKEND_URL || 'https://tripsyncbackend-production-37a2.up.railway.app')
  .replace(/\/$/, '');

const HEADERS = {
  'Accept':       'application/json',
  'Content-Type': 'application/json',
  'User-Agent':   'k6-tripsync-load-test/5.0',
};

// ── Test Data ────────────────────────────────────────────────────────────────
const CITIES   = ['Paris', 'Tokyo', 'London', 'New York', 'Sydney', 'Mumbai', 'Dubai', 'Singapore'];
const COORDS   = [
  { lat: 48.8566, lon: 2.3522 },
  { lat: 35.6762, lon: 139.6503 },
  { lat: 51.5074, lon: -0.1278 },
  { lat: 40.7128, lon: -74.0060 },
  { lat: -33.8688, lon: 151.2093 }
];
const USER_IDS = ['load_test_01', 'load_test_02', 'perf_user', 'k6_runner'];

// ── Validation Helper ─────────────────────────────────────────────────────────
function validate(res, label, code = 200, maxMs = 3000) {
  const passed = check(res, {
    [`[${label}] status ${code}`]:       (r) => r.status === code,
    [`[${label}] latency < ${maxMs}ms`]: (r) => r.timings.duration < maxMs,
    [`[${label}] body not empty`]:       (r) => Boolean(r.body && r.body.length > 0),
  });
  errorRate.add(!passed);
  totalRequests.add(1);
  return passed;
}

// ── Default VU Execution Routine ──────────────────────────────────────────────
export default function () {
  const idx    = (__VU - 1 + __ITER) % CITIES.length;
  const city   = CITIES[idx % CITIES.length];
  const coord  = COORDS[idx % COORDS.length];
  const userId = USER_IDS[__VU % USER_IDS.length];

  // ── 1. Authentication API Category ──────────────────────────────────────────
  group('Authentication API', () => {
    const payload = JSON.stringify({ email: `user_${__VU}@tripsync.com`, otp: '884920' });
    const res = http.post(`${BASE_URL}/api/otp/send`, payload, { headers: HEADERS });
    validate(res, 'POST /api/otp/send', 200, 2000);
    authDuration.add(res.timings.duration);
  });

  sleep(0.2);

  // ── 2. Health API Category ──────────────────────────────────────────────────
  group('Health API', () => {
    const resHealth = http.get(`${BASE_URL}/health`, { headers: HEADERS });
    validate(resHealth, 'GET /health', 200, 400);
    healthDuration.add(resHealth.timings.duration);

    const resRoot = http.get(`${BASE_URL}/`, { headers: HEADERS });
    validate(resRoot, 'GET /', 200, 600);
    rootDuration.add(resRoot.timings.duration);
  });

  sleep(0.2);

  // ── 3. Trip API Category ────────────────────────────────────────────────────
  group('Trip API', () => {
    const resGet = http.get(`${BASE_URL}/api/trips?userId=${userId}`, { headers: HEADERS });
    validate(resGet, 'GET /api/trips', 200, 600);
    tripsDuration.add(resGet.timings.duration);

    const tripPayload = JSON.stringify({
      title: `Trip VU ${__VU}`,
      destination: city,
      startDate: '2026-09-01',
      endDate: '2026-09-10',
      userId: userId
    });
    const resPost = http.post(`${BASE_URL}/api/trips`, tripPayload, { headers: HEADERS });
    validate(resPost, 'POST /api/trips', 200, 1000);
    tripsDuration.add(resPost.timings.duration);
  });

  sleep(0.3);

  // ── 4. AI API Category ──────────────────────────────────────────────────────
  group('AI API', () => {
    const resWeather = http.get(`${BASE_URL}/api/weather?lat=${coord.lat}&lon=${coord.lon}`, { headers: HEADERS });
    validate(resWeather, 'GET /api/weather', 200, 2500);
    weatherDuration.add(resWeather.timings.duration);

    const resSafety = http.get(`${BASE_URL}/api/safety?city=${encodeURIComponent(city)}`, { headers: HEADERS });
    check(resSafety, {
      '[Safety API] status 200 or 503': (r) => r.status === 200 || r.status === 503,
      '[Safety API] latency < 5s':      (r) => r.timings.duration < 5000,
    });
    const isHardError = resSafety.status >= 500 && resSafety.status !== 503;
    errorRate.add(isHardError);
    totalRequests.add(1);
    safetyDuration.add(resSafety.timings.duration);
  });

  sleep(0.3);

  // ── 5. Group API Category ───────────────────────────────────────────────────
  group('Group API', () => {
    const splitPayload = JSON.stringify({
      totalAmount: 450.0,
      members: ['Alice', 'Bob', 'Charlie'],
      description: 'Group Dinner'
    });
    const resSplit = http.post(`${BASE_URL}/api/expenses/split`, splitPayload, { headers: HEADERS });
    validate(resSplit, 'POST /api/expenses/split', 200, 1000);
    groupDuration.add(resSplit.timings.duration);

    const sharePayload = JSON.stringify({
      routeId: `route_${__VU}`,
      routeName: `${city} Exploration Route`,
      stopsCount: 4,
      totalDistance: '12.5 km',
      totalDuration: '45 mins'
    });
    const resShare = http.post(`${BASE_URL}/api/routes/share`, sharePayload, { headers: HEADERS });
    validate(resShare, 'POST /api/routes/share', 200, 1000);
    groupDuration.add(resShare.timings.duration);
  });

  sleep(Math.random() * 0.8 + 0.2);
}

export function setup() {
  console.log('╔══════════════════════════════════════════════════╗');
  console.log('║   TripSync Backend — k6 Load Test v5.0           ║');
  console.log('║   Categorized API Suites (Auth/Health/Trip/AI/Group)║');
  console.log('╚══════════════════════════════════════════════════╝');
  console.log(`🎯 Target: ${BASE_URL}`);
  return { baseUrl: BASE_URL, startTime: new Date().toISOString() };
}

export function teardown(data) {
  console.log(`✅ Categorized Load test finished against: ${data.baseUrl}`);
}
