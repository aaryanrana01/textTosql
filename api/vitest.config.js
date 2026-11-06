import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    env: { QUERY_RATE_LIMIT_PER_HOUR: '3', LOG_LEVEL: 'silent' },
    fileParallelism: false,
  },
});
