import cors from 'cors';
import express from 'express';
import helmet from 'helmet';
import pinoHttp from 'pino-http';
import { config } from './config.js';
import { pool } from './db.js';
import { errorHandler, notFound } from './errors.js';
import { authRouter } from './routes/auth.js';
import { queryRouter } from './routes/queries.js';

export function createApp() {
  const app = express();
  app.set('trust proxy', config.TRUST_PROXY); // set to 1 behind a hosting provider's proxy, so rate limits see real client IPs
  app.use(helmet());
  app.use(cors({ origin: config.CORS_ORIGIN }));
  app.use(express.json({ limit: '10kb' }));
  app.use(pinoHttp({ level: process.env.LOG_LEVEL ?? 'info', redact: ['req.headers.authorization'] }));

  app.get('/api/health', async (_req, res) => {
    const checks = { database: false, generation_service: false };
    try {
      await pool.query('SELECT 1');
      checks.database = true;
    } catch { /* reported as false */ }
    try {
      const r = await fetch(`${config.GEN_SERVICE_URL}/health`, { signal: AbortSignal.timeout(3000) });
      checks.generation_service = r.ok;
    } catch { /* reported as false */ }
    const healthy = Object.values(checks).every(Boolean);
    res.status(healthy ? 200 : 503).json({ status: healthy ? 'ok' : 'degraded', ...checks });
  });

  app.use('/api/auth', authRouter);
  app.use('/api', queryRouter);
  app.use(notFound);
  app.use(errorHandler);
  return app;
}