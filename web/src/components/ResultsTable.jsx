const format = (v) =>
  v === null || v === undefined
    ? '—'
    : typeof v === 'number'
      ? v.toLocaleString(undefined, { maximumFractionDigits: 2 })
      : String(v);

export default function ResultsTable({ columns, rows, truncated }) {
  if (!columns?.length) return null;

  return (
    <div className="overflow-hidden rounded-xl border border-slate-200 bg-white">
      <div className="max-h-[28rem] overflow-auto">
        <table className="min-w-full text-sm">
          <thead className="sticky top-0 bg-slate-50 text-left text-xs uppercase tracking-wide text-slate-500">
            <tr>
              {columns.map((c, i) => (
                <th key={`${c}-${i}`} scope="col" className="whitespace-nowrap px-4 py-2 font-medium">{c}</th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {rows.map((row, i) => (
              <tr key={i} className="hover:bg-slate-50">
                {row.map((v, j) => (
                  <td key={j} className={`whitespace-nowrap px-4 py-2 ${typeof v === 'number' ? 'text-right tabular-nums' : ''}`}>
                    {format(v)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="border-t border-slate-100 px-4 py-2 text-xs text-slate-500">
        {rows.length} row{rows.length === 1 ? '' : 's'}
        {truncated && ' · showing the first 200 rows'}
      </div>
    </div>
  );
}