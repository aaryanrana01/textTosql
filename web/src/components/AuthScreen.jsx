import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '../api.js';

export default function AuthScreen({ onSignedIn }) {
  const [mode, setMode] = useState('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');

  const auth = useMutation({
    mutationFn: ({ path, body }) => api(path, { method: 'POST', body }),
    onSuccess: onSignedIn,
  });

  function submit(e) {
    e.preventDefault();
    auth.mutate({ path: `/auth/${mode}`, body: { email, password } });
  }

  function switchMode() {
    setMode((m) => (m === 'login' ? 'signup' : 'login'));
    auth.reset();
  }

  const input =
    'w-full rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm outline-none focus:border-indigo-500 focus:ring-2 focus:ring-indigo-100';

  return (
    <main className="grid min-h-screen place-items-center px-4">
      <div className="w-full max-w-sm">
        <h1 className="text-2xl font-semibold">Ask your data</h1>
        <p className="mt-2 text-sm text-slate-600">
          Ask questions about a DVD rental business in plain English. Every answer shows the SQL behind it.
        </p>

        <button
          onClick={() => auth.mutate({ path: '/auth/guest' })}
          disabled={auth.isPending}
          className="mt-6 w-full rounded-lg bg-indigo-600 px-4 py-2.5 font-medium text-white hover:bg-indigo-500 disabled:opacity-60"
        >
          Continue as guest
        </button>

        <div className="my-6 flex items-center gap-3 text-xs text-slate-400">
          <span className="h-px flex-1 bg-slate-200" />
          or
          <span className="h-px flex-1 bg-slate-200" />
        </div>

        <form onSubmit={submit} className="space-y-3">
          <input
            type="email" required autoComplete="email" placeholder="Email" aria-label="Email"
            value={email} onChange={(e) => setEmail(e.target.value)} className={input}
          />
          <input
            type="password" required minLength={mode === 'signup' ? 8 : 1}
            autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
            placeholder={mode === 'signup' ? 'Password (at least 8 characters)' : 'Password'} aria-label="Password"
            value={password} onChange={(e) => setPassword(e.target.value)} className={input}
          />
          <button
            type="submit" disabled={auth.isPending}
            className="w-full rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium hover:bg-slate-50 disabled:opacity-60"
          >
            {mode === 'login' ? 'Log in' : 'Create account'}
          </button>
        </form>

        {auth.error && <p role="alert" className="mt-3 text-sm text-red-600">{auth.error.message}</p>}

        <p className="mt-4 text-sm text-slate-600">
          {mode === 'login' ? 'No account? ' : 'Already have an account? '}
          <button onClick={switchMode} className="font-medium text-indigo-600 hover:underline">
            {mode === 'login' ? 'Sign up' : 'Log in'}
          </button>
        </p>
      </div>
    </main>
  );
}