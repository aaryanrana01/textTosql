import { useMutation } from '@tanstack/react-query';
import { useState } from 'react';
import { api } from '../api.js';

export default function Feedback({ id, initial }) {
  const [value, setValue] = useState(initial);

  const send = useMutation({
    mutationFn: (v) => api(`/history/${id}/feedback`, { method: 'POST', body: { value: v } }),
    onMutate: (v) => setValue(v), // update the UI immediately
    onError: () => setValue(initial), // roll back if saving failed
  });

  const button = (v, label, icon, selectedStyle) => {
    const selected = value === v;
    return (
      <button
        onClick={() => send.mutate(v)}
        aria-pressed={selected}
        aria-label={label}
        title={label}
        className={`rounded-lg border px-2.5 py-1 text-base transition ${
          selected ? selectedStyle : 'border-transparent opacity-50 grayscale hover:opacity-100 hover:grayscale-0'
        }`}
      >
        {icon}
      </button>
    );
  };

  return (
    <div className="flex items-center gap-1.5 text-xs text-slate-500">
      <span className="mr-1">{value == null ? 'Was this right?' : 'Thanks for the feedback'}</span>
      {button(1, 'Yes, this answer was right', '👍', 'border-emerald-300 bg-emerald-50')}
      {button(-1, 'No, this answer was wrong', '👎', 'border-red-300 bg-red-50')}
      {send.isError && <span className="text-red-600">Couldn't save</span>}
    </div>
  );
}
