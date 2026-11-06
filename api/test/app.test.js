import request from 'supertest';
import { afterAll, describe, expect, it, vi } from 'vitest';
import { createApp } from '../src/app.js';
import { pool } from '../src/db.js';
import { HttpError } from '../src/errors.js';
import { askGenService } from '../src/genService.js';

// Replace the Python service with a controllable fake: no LLM tokens, same result every run.
vi.mock('../src/genService.js', () => ({ askGenService: vi.fn() }));

const app = createApp();
const uniqueEmail = () => `test-${Date.now()}-${Math.random().toString(36).slice(2, 8)}@example.com`;
const PASSWORD = 'correct-horse-battery';

const ANSWER = {
  sql: 'SELECT count(*) FROM film', columns: ['count'], rows: [[1000]], row_count: 1, truncated: false,
  refused: false, refusal_category: null, refusal_reason: null, error: null, error_stage: null,
  attempts: 1, terms_used: [], schema_tables: ['film'], latency_ms: 5, usage: { prompt_tokens: 10, completion_tokens: 2 },
};

async function guestAuth() {
  const res = await request(app).post('/api/auth/guest');
  return { Authorization: `Bearer ${res.body.token}` };
}

afterAll(async () => {
  await pool.end();
});

describe('authentication', () => {
  it('creates a guest session with a JWT', async () => {
    const res = await request(app).post('/api/auth/guest');
    expect(res.status).toBe(201);
    expect(res.body.token).toMatch(/^eyJ/);
    expect(res.body.user.guest).toBe(true);
  });

  it('rejects a weak password and names the field', async () => {
    const res = await request(app).post('/api/auth/signup').send({ email: uniqueEmail(), password: 'short' });
    expect(res.status).toBe(400);
    expect(res.body.details[0].field).toBe('password');
  });

  it('signs up, refuses a duplicate, and logs in case-insensitively', async () => {
    const email = uniqueEmail();
    expect((await request(app).post('/api/auth/signup').send({ email, password: PASSWORD })).status).toBe(201);
    expect((await request(app).post('/api/auth/signup').send({ email, password: PASSWORD })).status).toBe(409);
    const login = await request(app).post('/api/auth/login').send({ email: email.toUpperCase(), password: PASSWORD });
    expect(login.status).toBe(200);
    expect(login.body.user.guest).toBe(false);
  });

  it('gives the same answer for a wrong password and an unknown email', async () => {
    const email = uniqueEmail();
    await request(app).post('/api/auth/signup').send({ email, password: PASSWORD });
    const wrong = await request(app).post('/api/auth/login').send({ email, password: 'wrong-password' });
    const unknown = await request(app).post('/api/auth/login').send({ email: uniqueEmail(), password: 'wrong-password' });
    expect(wrong.status).toBe(401);
    expect(unknown.status).toBe(401);
    expect(wrong.body.error).toBe(unknown.body.error); // no hint about which emails exist
  });
});

describe('questions and history', () => {
  it('requires a token', async () => {
    const res = await request(app).post('/api/query').send({ question: 'How many films are there?' });
    expect(res.status).toBe(401);
  });

  it('validates the question before calling the engine', async () => {
    askGenService.mockClear();
    const res = await request(app).post('/api/query').set(await guestAuth()).send({ question: 'hi' });
    expect(res.status).toBe(400);
    expect(askGenService).not.toHaveBeenCalled();
  });

  it('answers, stores history, and keeps each user\'s history private', async () => {
    askGenService.mockResolvedValueOnce(ANSWER);
    const auth = await guestAuth();
    const asked = await request(app).post('/api/query').set(auth).send({ question: 'How many films are there?' });
    expect(asked.status).toBe(200);
    expect(asked.body.status).toBe('ok');
    expect(asked.body.rows).toEqual([[1000]]);

    const history = await request(app).get('/api/history').set(auth);
    expect(history.body.items.map((i) => i.id)).toContain(asked.body.id);

    const detail = await request(app).get(`/api/history/${asked.body.id}`).set(auth);
    expect(detail.body.sql).toBe(ANSWER.sql);
    expect(detail.body.rows).toEqual([[1000]]);

    const someoneElse = await request(app).get(`/api/history/${asked.body.id}`).set(await guestAuth());
    expect(someoneElse.status).toBe(404); // 404, not 403: doesn't even confirm the query exists
  });

  it('stores refusals with their category', async () => {
    askGenService.mockResolvedValueOnce({
      ...ANSWER, sql: '', columns: [], rows: [], row_count: 0, attempts: 0,
      refused: true, refusal_category: 'modifies_data', refusal_reason: 'This assistant only reads data.',
    });
    const auth = await guestAuth();
    const asked = await request(app).post('/api/query').set(auth).send({ question: 'Delete all rentals.' });
    expect(asked.body.status).toBe('refused');
    const detail = await request(app).get(`/api/history/${asked.body.id}`).set(auth);
    expect(detail.body.refusal_category).toBe('modifies_data');
  });

  it('records feedback and validates its value', async () => {
    askGenService.mockResolvedValueOnce(ANSWER);
    const auth = await guestAuth();
    const asked = await request(app).post('/api/query').set(auth).send({ question: 'How many films are there?' });
    const ok = await request(app).post(`/api/history/${asked.body.id}/feedback`).set(auth).send({ value: 1 });
    expect(ok.status).toBe(204);
    const bad = await request(app).post(`/api/history/${asked.body.id}/feedback`).set(auth).send({ value: 5 });
    expect(bad.status).toBe(400);
    const detail = await request(app).get(`/api/history/${asked.body.id}`).set(auth);
    expect(detail.body.feedback).toBe(1);
  });

  it('passes the engine\'s daily-limit error through as 429', async () => {
    askGenService.mockRejectedValueOnce(new HttpError(429, 'The daily demo limit has been reached.'));
    const res = await request(app).post('/api/query').set(await guestAuth()).send({ question: 'How many films are there?' });
    expect(res.status).toBe(429);
    expect(res.body.error).toMatch(/daily demo limit/);
  });

  it('limits questions per user', async () => {
    askGenService.mockResolvedValue(ANSWER);
    const auth = await guestAuth();
    for (let i = 0; i < 3; i++) {
      expect((await request(app).post('/api/query').set(auth).send({ question: 'How many films are there?' })).status).toBe(200);
    }
    const fourth = await request(app).post('/api/query').set(auth).send({ question: 'How many films are there?' });
    expect(fourth.status).toBe(429); // the test configuration allows 3 per hour
  });
});