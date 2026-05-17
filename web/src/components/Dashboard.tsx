// Dashboard: transcript list (newest-first as returned by the backend —
// no client re-sort) + a static budget pill from the user profile.

import { Link } from "react-router-dom";
import { useMe, useTranscripts } from "../hooks";
import BudgetPill from "./BudgetPill";

function Dashboard() {
  const { data: transcripts, isLoading, isError } = useTranscripts();
  const { data: me } = useMe();

  return (
    <main className="dashboard">
      <header className="dashboard-header">
        <h1>SSM Transcriber</h1>
        {me ? (
          <BudgetPill
            email={me.email}
            monthlyBudgetUsd={me.monthlyBudgetUsd}
          />
        ) : null}
      </header>

      {isLoading ? (
        <p>Loading…</p>
      ) : isError ? (
        <p>Could not load transcripts.</p>
      ) : !transcripts || transcripts.length === 0 ? (
        <p>No transcripts yet</p>
      ) : (
        <ul className="transcript-list">
          {transcripts.map((t) => (
            <li key={t.jobId}>
              <Link to={`/t/${encodeURIComponent(t.jobId)}`}>
                {t.jobId}
              </Link>
              {t.lastModified ? (
                <time dateTime={t.lastModified}> {t.lastModified}</time>
              ) : null}
            </li>
          ))}
        </ul>
      )}
    </main>
  );
}

export default Dashboard;
