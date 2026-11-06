import { config } from './config.js';
import { HttpError } from './errors.js';

const WAKING_UP =
  'The query engine is waking up (free hosting sleeps when idle). Please try again in about a minute.';

export async function askGenService(question) {
  let response;
  try {
    response = await fetch(`${config.GEN_SERVICE_URL}/generate`, {
      method: 'POST',
      headers: {
        'content-type': 'application/json',
        ...(config.INTERNAL_API_TOKEN && { 'x-internal-token': config.INTERNAL_API_TOKEN }),
      },
      body: JSON.stringify({ question }),
      // Up to 3 LLM attempts can run inside one request, so allow generous time.
      signal: AbortSignal.timeout(120_000),
    });
  } catch (err) {
    // Running out of time almost always means the engine was asleep and is still starting up.
    if (err?.name === 'TimeoutError') throw new HttpError(503, WAKING_UP);
    throw new HttpError(503, 'the query service is unavailable');
  }

  const body = await response.json().catch(() => ({}));
  if (response.status === 429) throw new HttpError(429, body.detail ?? 'the service is busy; try again shortly');

  // The generation service's own errors are JSON with a "detail" field. A 502/503/504 WITHOUT one comes from
  // the hosting platform itself, which answers that way while a sleeping service is still starting.
  if ([502, 503, 504].includes(response.status) && body.detail === undefined) {
    throw new HttpError(503, WAKING_UP);
  }
  if (response.status === 504) throw new HttpError(504, 'the AI model took too long to answer; please try again');
  if (!response.ok) throw new HttpError(502, 'the query service failed to answer');
  return body;
}