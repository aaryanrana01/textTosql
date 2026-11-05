import AutoChart from './AutoChart.jsx';
import Feedback from './Feedback.jsx';
import ResultsTable from './ResultsTable.jsx';
import SqlBlock from './SqlBlock.jsx';

const REFUSAL_TITLES = {
  modifies_data: 'This assistant only reads data',
  not_in_data: "That information isn't in this database",
  prediction: "Predictions aren't possible from historical data",
  off_topic: "That isn't a question about this database",
  unclear: "That question couldn't be turned into a query",
};

function Refusal({ category, reason }) {
  return (
    <div className="rounded-xl border border-amber-200 bg-amber-50 p-4">
      <p className="text-sm font-medium text-amber-900">{REFUSAL_TITLES[category] ?? "Can't answer this one"}</p>
      {reason && <p className="mt-1 text-sm text-amber-800">{reason}</p>}
    </div>
  );
}

function Failure({ stage, error, sql }) {
  const blocked = stage === 'validation' || stage === 'cost';
  return (
    <div className="space-y-3">
      <div className="rounded-xl border border-red-200 bg-red-50 p-4">
        <p className="text-sm font-medium text-red-900">
          {blocked ? 'Blocked by a safety check' : "The query couldn't be run"}
        </p>
        <p className="mt-1 break-words font-mono text-xs text-red-800">{error}</p>
      </div>
      {sql && <SqlBlock sql={sql} />}
    </div>
  );
}

function Meta({ result }) {
  const parts = [];
  if (result.latency_ms != null) parts.push(`${(result.latency_ms / 1000).toFixed(1)} s`);
  if (result.attempts > 1) parts.push(`self-corrected after ${result.attempts} attempts`);
  const tokens = (result.usage?.prompt_tokens ?? 0) + (result.usage?.completion_tokens ?? 0);
  if (tokens) parts.push(`${tokens.toLocaleString()} tokens`);

  return (
    <div className="flex flex-wrap items-center gap-2 text-xs text-slate-500">
      {parts.length > 0 && <span>{parts.join(' · ')}</span>}
      {result.terms_used?.map((term) => (
        <span key={term} className="rounded-full bg-indigo-50 px-2 py-0.5 text-indigo-700">definition: {term}</span>
      ))}
    </div>
  );
}

export default function ResultView({ result }) {
  const refused = result.refused ?? result.status === 'refused';

  return (
    <section aria-label="Answer" className="space-y-4">
      <h2 className="text-lg font-medium">{result.question}</h2>

      {refused ? (
        <Refusal category={result.refusal_category} reason={result.refusal_reason} />
      ) : result.error ? (
        <Failure stage={result.error_stage} error={result.error} sql={result.sql} />
      ) : (
        <>
          <SqlBlock sql={result.sql} />
          <AutoChart columns={result.columns} rows={result.rows} />
          <ResultsTable columns={result.columns} rows={result.rows} truncated={result.truncated} />
        </>
      )}

      <div className="flex flex-wrap items-center justify-between gap-3">
        <Meta result={result} />
        {result.id != null && <Feedback key={result.id} id={result.id} initial={result.feedback ?? null} />}
      </div>
    </section>
  );
}