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
});