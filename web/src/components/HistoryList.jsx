import { useQuery } from '@tanstack/react-query';
import { api } from '../api.js';

const STATUS = {
  ok: { dot: 'bg-emerald-500', label: 'Answered' },
  error: { dot: 'bg-red-500', label: 'Failed' },
  refused: { dot: 'bg-amber-500', label: 'Refused' },
};

export default function HistoryList({ selectedId, onSelect }) {
  const history = useQuery({ queryKey: ['history'], queryFn: () => api('/history?limit=50') });

  return (
    <nav aria-label="Question history" className="p-3">
      <h2 className="px-2 pb-2 text-xs font-medium uppercase tracking-wide text-slate-500">History</h2>
      {history.isLoading && <p className="px-2 text-sm text-slate-400">Loading…</p>}
      {history.error && <p className="px-2 text-sm text-red-600">{history.error.message}</p>}
      {history.data?.items.length === 0 && <p className="px-2 text-sm text-slate-400">Your questions will appear here.</p>}

      <ul className="space-y-1">
        {history.data?.items.map((item) => {
          const status = STATUS[item.status] ?? STATUS.error;
          return (
            <li key={item.id}>
              <button
                onClick={() => onSelect(item.id)}
                aria-current={item.id === selectedId ? 'true' : undefined}
                className={`flex w-full items-start gap-2 rounded-lg px-2 py-2 text-left text-sm hover:bg-slate-50 ${
                  item.id === selectedId ? 'bg-indigo-50' : ''
                }`}
              >
                <span className={`mt-1.5 h-2 w-2 shrink-0 rounded-full ${status.dot}`} aria-hidden="true" />
                <span className="min-w-0">
                  <span className="sr-only">{status.label}: </span>
                  <span className="line-clamp-2 block text-slate-800">{item.question}</span>
                  <span className="block text-xs text-slate-400">{new Date(item.created_at).toLocaleString()}</span>
                </span>
              </button>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}