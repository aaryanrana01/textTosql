import { config } from './config.js';
import { HttpError } from './errors.js';

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
  } catch {
    throw new HttpError(503, 'the query service is unavailable');
  }
  const body = await response.json().catch(() => ({}));
  if (response.status === 429) throw new HttpError(429, body.detail ?? 'the service is busy; try again shortly');
  if (!response.ok) throw new HttpError(502, 'the query service failed to answer');
  return body;
}