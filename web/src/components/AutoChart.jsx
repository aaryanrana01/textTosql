import { Bar, BarChart, CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts';

const TIME_NAME = /(year|month|date|day|week|quarter)/i;
const ISO_DATE = /^\d{4}-\d{2}-\d{2}/;
const ID_NAME = /(^id$|_id$)/i;

/** Returns { type, x, y } column indexes, or null when a chart wouldn't help. */
export function chooseChart(columns, rows) {
  if (!columns || columns.length < 2 || rows.length < 2 || rows.length > 60) return null;
  const numeric = columns.map((_, i) => rows.every((r) => r[i] === null || typeof r[i] === 'number'));

  // A time column (by name or ISO date value) plus a number → line chart over time.
  const timeIdx = columns.findIndex(
    (c, i) => TIME_NAME.test(c) || (typeof rows[0][i] === 'string' && ISO_DATE.test(rows[0][i])),
  );
  if (timeIdx !== -1) {
    const y = numeric.findIndex((isNum, i) => isNum && i !== timeIdx);
    if (y !== -1) return { type: 'line', x: timeIdx, y };
  }

  // A label (text, or an id column such as store_id) plus a number → bar chart.
  let x = numeric.findIndex((isNum) => !isNum);
  if (x === -1) x = columns.findIndex((c) => ID_NAME.test(c));
  const y = numeric.findIndex((isNum, i) => isNum && i !== x);
  if (x !== -1 && y !== -1) return { type: 'bar', x, y };
  return null;
}

const formatNumber = (v) => (typeof v === 'number' ? v.toLocaleString(undefined, { maximumFractionDigits: 2 }) : v);
const formatLabel = (v) => (typeof v === 'string' && ISO_DATE.test(v) ? v.slice(0, 10) : v);
const tick = { fontSize: 12, fill: '#64748b' };

export default function AutoChart({ columns, rows }) {
  const spec = chooseChart(columns, rows);
  if (!spec) return null;

  const data = rows.map((r) => ({ x: r[spec.x], y: r[spec.y] }));
  if (spec.type === 'line') data.sort((a, b) => (a.x > b.x ? 1 : a.x < b.x ? -1 : 0));
  const yLabel = columns[spec.y];

  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4">
      <p className="mb-2 text-xs text-slate-500">{yLabel} by {columns[spec.x]}</p>
      <div className="h-64">
        <ResponsiveContainer width="100%" height="100%">
          {spec.type === 'line' ? (
            <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" />
              <XAxis dataKey="x" tick={tick} tickFormatter={formatLabel} />
              <YAxis tick={tick} tickFormatter={formatNumber} width={72} />
              <Tooltip formatter={(v) => [formatNumber(v), yLabel]} labelFormatter={formatLabel} />
              <Line type="monotone" dataKey="y" stroke="#4f46e5" strokeWidth={2} dot={false} />
            </LineChart>
          ) : (
            <BarChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="#e2e8f0" vertical={false} />
              <XAxis dataKey="x" tick={tick} />
              <YAxis tick={tick} tickFormatter={formatNumber} width={72} />
              <Tooltip formatter={(v) => [formatNumber(v), yLabel]} />
              <Bar dataKey="y" fill="#6366f1" radius={[4, 4, 0, 0]} />
            </BarChart>
          )}
        </ResponsiveContainer>
      </div>
    </div>
  );
}