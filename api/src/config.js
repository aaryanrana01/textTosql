import { fileURLToPath } from 'node:url';
import dotenv from 'dotenv';
import { z } from 'zod';

// One .env file at the repository root is shared with the Python service.
// On a hosting platform there is no .env file; settings come from the platform's environment instead.
dotenv.config({ path: fileURLToPath(new URL('../../.env', import.meta.url)), quiet: true });

const Env = z.object({
  API_PORT: z.coerce.number().int().positive().default(4000),
  DB_HOST: z.string().default('localhost'),
  DB_PORT: z.coerce.number().int().positive().default(5432),
  POSTGRES_DB: z.string().min(1),
  API_USER_PASSWORD: z.string().min(1),
  JWT_SECRET: z.string().min(32, 'JWT_SECRET must be at least 32 characters'),
  GEN_SERVICE_URL: z.string().url().default('http://localhost:8000'),
  INTERNAL_API_TOKEN: z.string().default(''),
  CORS_ORIGIN: z.string().default('http://localhost:5173'),
  QUERY_RATE_LIMIT_PER_HOUR: z.coerce.number().int().positive().default(20),
  TRUST_PROXY: z.coerce.number().int().min(0).default(0),
  // "true" on hosted databases such as Neon, which accept only encrypted connections
  DB_SSL: z.enum(['true', 'false']).default('false').transform((v) => v === 'true'),
  // "true" in deployment: Express also hands out the built React app from web/dist
  SERVE_WEB: z.enum(['true', 'false']).default('false').transform((v) => v === 'true'),
});

// Hosting platforms such as Render tell the app which port (door number) to use through PORT.
const parsed = Env.safeParse({ ...process.env, API_PORT: process.env.API_PORT ?? process.env.PORT });
if (!parsed.success) {
  const problems = parsed.error.issues.map((i) => `${i.path.join('.')}: ${i.message}`).join('; ');
  console.error(`Invalid configuration: ${problems}`);
  process.exit(1);
}

export const config = parsed.data;