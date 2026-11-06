import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '../api.js';
import HistoryList from './HistoryList.jsx';
import QuestionForm from './QuestionForm.jsx';
import ResultView from './ResultView.jsx';

function Thinking({ engineReady }) {
  return (
    <div role="status" className="flex items-center gap-3 rounded-xl border border-slate-200 bg-white p-4 text-sm text-slate-600">
      <span className="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-indigo-200 border-t-indigo-600" />
      {engineReady
        ? 'Finding the right tables, writing SQL and running safety checks…'
        : 'Waking up the query engine first, then writing your SQL… this can take about a minute.'}
    </div>
  );
}

function WakingUp() {
  return (
    <div role="status" className="flex items-start gap-3 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
      <span className="mt-0.5 h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-amber-200 border-t-amber-600" />
      <span>
        <strong className="font-medium">Waking up the demo…</strong> This free-tier server sleeps when nobody is using
        it, so the first start takes about a minute. You can type your question in the meantime.
      </span>
    </div>
  );
}

export default function Workspace({ user, onSignOut }) {
  const queryClient = useQueryClient();
  const [selectedId, setSelectedId] = useState(null);

  // Asks the API whether the query engine is awake. The request itself also wakes a sleeping engine,
  // so it starts loading the moment the page opens instead of when the first question arrives.
  // It re-checks every 5 seconds until the engine is ready, and again when the tab regains focus later.
  const health = useQuery({
    queryKey: ['health'],
    queryFn: () => api('/health'),
    retry: false,
    staleTime: 5 * 60_000,
    refetchOnWindowFocus: true,
    refetchInterval: (query) =>
      query.state.status === 'success' && query.state.data?.generation_service ? false : 5000,
  });
  const engineReady = health.isSuccess && health.data?.generation_service === true;

  const ask = useMutation({
    mutationFn: (question) => api('/query', { method: 'POST', body: { question } }),
    onSuccess: (result) => {
      queryClient.setQueryData(['query', result.id], result); // show the full answer without refetching
      queryClient.invalidateQueries({ queryKey: ['history'] });
      // An answer arrived, so the engine is clearly awake.
      queryClient.setQueryData(['health'], { status: 'ok', database: true, generation_service: true });
      setSelectedId(result.id);
    },
  });

  const selected = useQuery({
    queryKey: ['query', selectedId],
    queryFn: () => api(`/history/${selectedId}`),
    enabled: selectedId != null,
    staleTime: Infinity, // a saved answer never changes, so it never needs re-fetching
  });

  function openFromHistory(id) {
    ask.reset();
    setSelectedId(id);
  }

  return (
    <div className="flex h-screen flex-col">
      <header className="flex items-center justify-between border-b border-slate-200 bg-white px-4 py-3">
        <span className="font-semibold">Ask your data</span>
        <div className="flex items-center gap-3 text-sm text-slate-600">
          <span>{user.guest ? 'Guest' : user.email}</span>
          <button onClick={onSignOut} className="rounded-md px-2 py-1 hover:bg-slate-100">Sign out</button>
        </div>
      </header>

      <div className="flex min-h-0 flex-1">
        <aside className="hidden w-72 shrink-0 overflow-y-auto border-r border-slate-200 bg-white md:block">
          <HistoryList selectedId={selectedId} onSelect={openFromHistory} />
        </aside>

        <main className="min-w-0 flex-1 overflow-y-auto p-4 md:p-8">
          <div className="mx-auto max-w-4xl space-y-6">
            <QuestionForm onAsk={(q) => ask.mutate(q)} pending={ask.isPending} />

            {health.isFetched && !engineReady && !ask.isPending && <WakingUp />}
            {ask.isPending && <Thinking engineReady={engineReady} />}
            {ask.error && (
              <div role="alert" className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-800">
                {ask.error.message}
              </div>
            )}
            {!ask.isPending && !ask.error && selected.isLoading && <p className="text-sm text-slate-500">Loading…</p>}
            {!ask.isPending && !ask.error && selected.data && <ResultView result={selected.data} />}
            {!ask.isPending && !ask.error && selectedId == null && (
              <p className="pt-8 text-center text-sm text-slate-500">
                Ask a question, or try one of the examples above.
              </p>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}