import hljs from 'highlight.js/lib/core';
import sqlLanguage from 'highlight.js/lib/languages/sql';
import { useMemo, useState } from 'react';
import { format } from 'sql-formatter';

// Load only the SQL grammar, not all ~190 languages highlight.js supports.
hljs.registerLanguage('sql', sqlLanguage);

export default function SqlBlock({ sql }) {
  const [copied, setCopied] = useState(false);

  const html = useMemo(() => {
    let pretty = sql;
    try {
      pretty = format(sql, { language: 'postgresql', keywordCase: 'upper' });
    } catch {
      /* show the SQL exactly as generated if formatting fails */
    }
    // highlight.js escapes HTML characters in its input, so this output is safe to insert.
    return hljs.highlight(pretty, { language: 'sql' }).value;
  }, [sql]);

  async function copy() {
    try {
      await navigator.clipboard.writeText(sql);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch { /* clipboard unavailable */ }
  }

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      <div className="flex items-center justify-between border-b border-slate-100 px-4 py-2 text-xs text-slate-500">
        <span>Generated SQL</span>
        <button onClick={copy} className="rounded px-2 py-0.5 hover:bg-slate-100">{copied ? 'Copied' : 'Copy'}</button>
      </div>
      <pre className="overflow-x-auto p-4 text-sm leading-relaxed">
        <code className="hljs language-sql" dangerouslySetInnerHTML={{ __html: html }} />
      </pre>
    </div>
  );
}