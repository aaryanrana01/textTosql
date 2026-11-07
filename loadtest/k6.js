// Load test for QueryWise (k6). Exercises the full request path except the LLM itself:
// Express (auth, validation, rate limits, history) -> generation service (intent check or cache,
// safety gates, EXPLAIN cost check, read-only execution) -> PostgreSQL.
// Run: docker run --rm -i --network host -v "$PWD/loadtest:/scripts" grafana/k6 run /scripts/k6.js
import http from 'k6/http';
import { check } from 'k6';

const BASE = __ENV.BASE_URL || 'http://localhost:4100';
const RATE = Number(__ENV.RATE || 10); // requests per second, per scenario
const REFUSAL = 'Delete all rentals.';
const CACHED = 'What are the top 5 film categories by total payment revenue? Show the category name and the revenue.';

export const options = {
  summaryTrendStats: ['avg', 'p(50)', 'p(95)', 'p(99)', 'max'],
  scenarios: {
    refusals: {
      executor: 'constant-arrival-rate',
      rate: RATE, timeUnit: '1s', duration: '60s',
      preAllocatedVUs: 20, maxVUs: 100,
      exec: 'refusal',
    },
    cached_answers: {
      executor: 'constant-arrival-rate',
      rate: RATE, timeUnit: '1s', duration: '60s',
      preAllocatedVUs: 20, maxVUs: 100,
      exec: 'cached',
      startTime: '70s', // runs after the refusal scenario, so each is measured on its own
    },
  },
  thresholds: {
    http_req_failed: ['rate<0.01'],
    'http_req_duration{scenario:refusals}': ['p(95)<500'],
    'http_req_duration{scenario:cached_answers}': ['p(95)<1000'],
  },
};

function headers(token) {
  return { 'Content-Type': 'application/json', Authorization: `Bearer ${token}` };
}

export function setup() {
  const guest = http.post(`${BASE}/api/auth/guest`);
  check(guest, { 'guest created': (r) => r.status === 201 });
  const token = guest.json('token');

  // Fill the cache once: this first ask calls the LLM (~1,300 tokens); every later ask is a cache hit.
  const warm = http.post(`${BASE}/api/query`, JSON.stringify({ question: CACHED }), {
    headers: headers(token),
    timeout: '120s',
  });
  check(warm, { 'cache filled': (r) => r.status === 200 && r.json('status') === 'ok' });
  return { token };
}

export function refusal(data) {
  const res = http.post(`${BASE}/api/query`, JSON.stringify({ question: REFUSAL }), { headers: headers(data.token) });
  check(res, { refused: (r) => r.status === 200 && r.json('status') === 'refused' });
}

export function cached(data) {
  const res = http.post(`${BASE}/api/query`, JSON.stringify({ question: CACHED }), { headers: headers(data.token) });
  check(res, { 'answered from cache': (r) => r.status === 200 && r.json('cache_hit') === true });
}