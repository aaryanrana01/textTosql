import path from 'node:path';
import { fileURLToPath } from 'node:url';
import cors from 'cors';
import express from 'express';
import helmet from 'helmet';
import pinoHttp from 'pino-http';
import { config } from './config.js';
import { pool } from './db.js';
import { errorHandler, notFound } from './errors.js';
import { authRouter } from './routes/auth.js';
import { queryRouter } from './routes/queries.js';

// A free-tier generation service sleeps when idle. The hosting platform only finishes waking it for a request
// that WAITS until it is up; the quick health check below gives up after 3 seconds, too early to wake it.
// So when that check fails, one patient request is sent in the background (at most one at a time).
let wakeInFlight = null;

function wakeGenerationService() {
  if (wakeInFlight) return;
  wakeInFlight = fetch(`${config.GEN_SERVICE_URL}/health`, { signal: AbortSignal.timeout(180_000) })
    .catch(() => { /* still asleep or failing; the next health check will try again */ })
    .finally(() => { wakeInFlight = null; });
}

export function createApp() {
  const app = express();
  app.set('trust proxy', config.TRUST_PROXY); // 1 behind a hosting provider's proxy, so rate limits see real client IPs
  app.use(helmet());
  app.use(cors({ origin: config.CORS_ORIGIN }));
  app.use(express.json({ limit: '10kb' }));
  app.use(pinoHttp({ level: process.env.LOG_LEVEL ?? 'info', redact: ['req.headers.authorization'] }));

  // Liveness: answers only "is Express running?". The hosting platform checks this one, so a sleeping
  // generation service (free tier) never makes the platform think Express is broken and restart it.
  app.get('/api/live', (_req, res) => {
    res.json({ status: 'ok' });
  });

  // Full health: database and generation service. The page polls this while it shows "Waking up the demo…".
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
    if (!checks.generation_service) wakeGenerationService();
    const healthy = Object.values(checks).every(Boolean);
    res.status(healthy ? 200 : 503).json({ status: healthy ? 'ok' : 'degraded', ...checks });
  });

  app.use('/api/auth', authRouter);
  app.use('/api', queryRouter);

  if (config.SERVE_WEB) {
    // In deployment, Express also hands out the built React app: one address, no CORS.
    const webDist = fileURLToPath(new URL('../../web/dist', import.meta.url));
    app.use(express.static(webDist));
    // Any page address that isn't an API call gets index.html; React then shows the right page.
    app.get(/^\/(?!api(\/|$)).*/, (_req, res) => res.sendFile(path.join(webDist, 'index.html')));
  }

  app.use(notFound);
  app.use(errorHandler);
  return app;
}