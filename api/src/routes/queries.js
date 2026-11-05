import { Router } from 'express';
import { rateLimit } from 'express-rate-limit';
import { requireAuth } from '../auth.js';
import { config } from '../config.js';
import { pool } from '../db.js';
import { HttpError } from '../errors.js';
import { askGenService } from '../genService.js';
import { FeedbackBody, HistoryQuery, IdParam, QueryBody } from '../schemas.js';

export const queryRouter = Router();
queryRouter.use(requireAuth);

// Per-user limit on questions, because every answered question spends LLM tokens.
const questionLimiter = rateLimit({
  windowMs: 60 * 60 * 1000,
  limit: config.QUERY_RATE_LIMIT_PER_HOUR,
  keyGenerator: (req) => `user:${req.user.id}`,
  standardHeaders: 'draft-7',
  legacyHeaders: false,
  message: { error: `limit of ${config.QUERY_RATE_LIMIT_PER_HOUR} questions per hour reached; try again later` },
});

// Only the fields the frontend needs leave the API.
function toPublicResult(r) {
  return {
    sql: r.sql ?? '',
    columns: r.columns ?? [],
    rows: r.rows ?? [],
    row_count: r.row_count ?? 0,
    truncated: r.truncated ?? false,
    refused: r.refused ?? false,
    refusal_category: r.refusal_category ?? null,
    refusal_reason: r.refusal_reason ?? null,
    error: r.error ?? null,
    error_stage: r.error_stage ?? null,
    attempts: r.attempts ?? 0,
    terms_used: r.terms_used ?? [],
    schema_tables: r.schema_tables ?? [],
    latency_ms: r.latency_ms ?? null,
    usage: r.usage ?? {},
  };
}

queryRouter.post('/query', questionLimiter, async (req, res) => {
  const { question } = QueryBody.parse(req.body);
  const result = toPublicResult(await askGenService(question));
  const status = result.refused ? 'refused' : result.error ? 'error' : 'ok';

  const { rows } = await pool.query(
    `INSERT INTO app.queries
       (user_id, question, sql, status, refusal_reason, error, result_columns, result_rows, row_count, truncated, latency_ms)
     VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb, $8::jsonb, $9, $10, $11)
     RETURNING id, created_at`,
    [
      req.user.id, question, result.sql || null, status, result.refusal_reason, result.error,
      JSON.stringify(result.columns), JSON.stringify(result.rows), result.row_count, result.truncated, result.latency_ms,
    ],
  );

  res.json({ id: Number(rows[0].id), created_at: rows[0].created_at, question, status, ...result });
});

queryRouter.get('/history', async (req, res) => {
  const { limit } = HistoryQuery.parse(req.query);
  const { rows } = await pool.query(
    `SELECT id, question, status, row_count, feedback, created_at
     FROM app.queries WHERE user_id = $1 ORDER BY created_at DESC LIMIT $2`,
    [req.user.id, limit],
  );
  res.json({ items: rows.map((r) => ({ ...r, id: Number(r.id) })) });
});

queryRouter.get('/history/:id', async (req, res) => {
  const { id } = IdParam.parse(req.params);
  const { rows } = await pool.query(
    `SELECT id, question, sql, status, refusal_reason, error, result_columns AS columns, result_rows AS rows,
            row_count, truncated, latency_ms, feedback, created_at
     FROM app.queries WHERE id = $1 AND user_id = $2`,
    [id, req.user.id],
  );
  if (!rows[0]) throw new HttpError(404, 'query not found');
  res.json({ ...rows[0], id: Number(rows[0].id) });
});

queryRouter.post('/history/:id/feedback', async (req, res) => {
  const { id } = IdParam.parse(req.params);
  const { value } = FeedbackBody.parse(req.body);
  const { rowCount } = await pool.query(
    'UPDATE app.queries SET feedback = $1 WHERE id = $2 AND user_id = $3',
    [value, id, req.user.id],
  );
  if (!rowCount) throw new HttpError(404, 'query not found');
  res.status(204).end();
});