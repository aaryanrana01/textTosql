import { createApp } from './app.js';
import { config } from './config.js';
import { pool } from './db.js';

const app = createApp();
const server = app.listen(config.API_PORT, () => {
  console.log(`API listening on http://localhost:${config.API_PORT}`);
});

// Graceful shutdown: stop accepting new requests, let in-flight ones finish, then close the database pool.
for (const signal of ['SIGINT', 'SIGTERM']) {
  process.on(signal, () => server.close(() => pool.end().then(() => process.exit(0))));
}