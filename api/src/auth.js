import bcrypt from 'bcryptjs';
import jwt from 'jsonwebtoken';
import { config } from './config.js';
import { HttpError } from './errors.js';

const BCRYPT_COST = 12;

// Used when an email isn't registered, so login takes the same time either way (see routes/auth.js).
export const DUMMY_HASH = bcrypt.hashSync('not-a-real-password', BCRYPT_COST);

export const hashPassword = (password) => bcrypt.hash(password, BCRYPT_COST);
export const checkPassword = (password, hash) => bcrypt.compare(password, hash);

export function signToken(user) {
  return jwt.sign({ sub: String(user.id), guest: user.is_guest }, config.JWT_SECRET, {
    algorithm: 'HS256',
    expiresIn: user.is_guest ? '1d' : '7d',
  });
}

export function requireAuth(req, _res, next) {
  const [scheme, token] = (req.get('authorization') ?? '').split(' ');
  if (scheme !== 'Bearer' || !token) throw new HttpError(401, 'missing or malformed token');
  try {
    const payload = jwt.verify(token, config.JWT_SECRET, { algorithms: ['HS256'] });
    req.user = { id: Number(payload.sub), guest: Boolean(payload.guest) };
  } catch {
    throw new HttpError(401, 'invalid or expired token');
  }
  next();
}