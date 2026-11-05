import { z } from 'zod';

const email = z.string().trim().toLowerCase().email().max(254);

export const SignupBody = z.object({
  email,
  password: z.string().min(8, 'password must be at least 8 characters').max(128),
});
export const LoginBody = z.object({ email, password: z.string().min(1).max(128) });
export const QueryBody = z.object({ question: z.string().trim().min(3).max(500) });
export const FeedbackBody = z.object({ value: z.union([z.literal(1), z.literal(-1)]) });
export const HistoryQuery = z.object({ limit: z.coerce.number().int().min(1).max(100).default(20) });
export const IdParam = z.object({ id: z.coerce.number().int().positive() });