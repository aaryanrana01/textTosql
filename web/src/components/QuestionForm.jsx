import { useState } from 'react';

const EXAMPLES = [
  'What are the top 5 film categories by total payment revenue?',
  'How many VIP customers do we have?',
  'What was the total payment revenue in each month of 2025?',
  'Which films have never been rented?',
  'Delete all rentals.',
];

export default function QuestionForm({ onAsk, pending }) {
  const [question, setQuestion] = useState('');
  const trimmed = question.trim();

  function submit(e) {
    e?.preventDefault();
    if (trimmed.length >= 3 && !pending) onAsk(trimmed);
  }

  return (
    <form onSubmit={submit} className="space-y-3">
      <div className="rounded-xl border border-slate-300 bg-white shadow-sm focus-within:border-indigo-500 focus-within:ring-2 focus-within:ring-indigo-100">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              submit();
            }
          }}
          rows={2}
          maxLength={500}
          placeholder="Ask a question about the rental business…"
          aria-label="Question"
          className="block w-full resize-none rounded-xl bg-transparent px-4 py-3 outline-none placeholder:text-slate-400"
        />
        <div className="flex items-center justify-between border-t border-slate-100 px-3 py-2">
          <span className="text-xs text-slate-400">{question.length}/500 · Enter to ask · Shift+Enter for a new line</span>
          <button
            type="submit"
            disabled={pending || trimmed.length < 3}
            className="rounded-lg bg-indigo-600 px-4 py-1.5 text-sm font-medium text-white hover:bg-indigo-500 disabled:opacity-50"
          >
            {pending ? 'Working…' : 'Ask'}
          </button>
        </div>
      </div>

      <div className="flex flex-wrap gap-2">
        {EXAMPLES.map((example) => (
          <button
            key={example}
            type="button"
            disabled={pending}
            onClick={() => {
              setQuestion(example);
              onAsk(example);
            }}
            className="rounded-full border border-slate-200 bg-white px-3 py-1 text-xs text-slate-600 hover:border-indigo-300 hover:text-indigo-700 disabled:opacity-50"
          >
            {example}
          </button>
        ))}
      </div>
    </form>
  );
}