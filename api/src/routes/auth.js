import { Router } from 'express';
import { rateLimit } from 'express-rate-limit';
import { checkPassword, DUMMY_HASH, hashPassword, requireAuth, signToken } from '../auth.js';
import { pool } from '../db.js';
import { HttpError } from '../errors.js';
import { LoginBody, SignupBody } from '../schemas.js';

export const authRouter = Router();

// Per-IP limit on account endpoints: slows down password guessing and mass account creation.
const authLimiter = rateLimit({
  windowMs: 15 * 60 * 1000,
  limit: 20,
  standardHeaders: 'draft-7',
  legacyHeaders: false,
  message: { error: 'too many attempts; try again later' },
});

const publicUser = (u) => ({ id: Number(u.id), email: u.email, guest: u.is_guest });

authRouter.post('/signup', authLimiter, async (req, res) => {
  const { email, password } = SignupBody.parse(req.body);
  const passwordHash = await hashPassword(password);
  try {
    const { rows } = await pool.query(
      'INSERT INTO app.users (email, password_hash) VALUES ($1, $2) RETURNING id, email, is_guest',
      [email, passwordHash],
    );
    res.status(201).json({ token: signToken(rows[0]), user: publicUser(rows[0]) });
  } catch (err) {
    if (err.code === '23505') throw new HttpError(409, 'an account with this email already exists');
    throw err;
  }
});

authRouter.post('/login', authLimiter, async (req, res) => {
  const { email, password } = LoginBody.parse(req.body);
  const { rows } = await pool.query(
    'SELECT id, email, is_guest, password_hash FROM app.users WHERE email = $1 AND NOT is_guest',
    [email],
  );
  const user = rows[0];
  // Always run bcrypt, even for unknown emails, so response time doesn't reveal which emails are registered.
  const valid = await checkPassword(password, user?.password_hash ?? DUMMY_HASH);
  if (!user || !valid) throw new HttpError(401, 'invalid email or password');
  res.json({ token: signToken(user), user: publicUser(user) });
});

authRouter.post('/guest', authLimiter, async (_req, res) => {
  const { rows } = await pool.query(
    'INSERT INTO app.users (is_guest) VALUES (true) RETURNING id, email, is_guest',
  );
  res.status(201).json({ token: signToken(rows[0]), user: publicUser(rows[0]) });
});

authRouter.get('/me', requireAuth, async (req, res) => {
  const { rows } = await pool.query('SELECT id, email, is_guest FROM app.users WHERE id = $1', [req.user.id]);
  if (!rows[0]) throw new HttpError(401, 'account no longer exists');
  res.json({ user: publicUser(rows[0]) });
});