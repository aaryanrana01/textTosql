import { fileURLToPath } from 'node:url';
import dotenv from 'dotenv';
import { z } from 'zod';

// One .env file at the repository root is shared with the Python service.
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
});

const parsed = Env.safeParse(process.env);
if (!parsed.success) {
  const problems = parsed.error.issues.map((i) => `${i.path.join('.')}: ${i.message}`).join('; ');
  console.error(`Invalid configuration: ${problems}`);
  process.exit(1);
}

export const config = parsed.data;