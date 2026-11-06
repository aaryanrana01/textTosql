import pg from 'pg';
import { config } from './config.js';

// The API's own role: it can read and write users and query history, and nothing else.
export const pool = new pg.Pool({
  host: config.DB_HOST,
  port: config.DB_PORT,
  database: config.POSTGRES_DB,
  user: 'api_user',
  password: config.API_USER_PASSWORD,
  max: 10,
  // Hosted databases such as Neon accept only encrypted connections. rejectUnauthorized also checks the
  // database's certificate, so the API can never be tricked into talking to an impostor database.
  ssl: config.DB_SSL ? { rejectUnauthorized: true } : false,
});

// An idle connection can be closed by the database at any time (Neon does this when it scales to zero).
// Without this handler, that event would crash the whole API instead of just discarding the connection.
pool.on('error', (err) => {
  console.error('Idle database connection error:', err.message);
});