import React from 'react';
import HistorySessionCard from './HistorySessionCard';
import HistoryEmptyState from './HistoryEmptyState';

/**
 * HistoryList component
 *
 * Renders the collection of historical wake sessions or displays
 * the empty state if no records are provided.
 *
 * Does NOT contain any developer toggles or demo switches.
 *
 * @param {{
 *   records?: Array<any>
 * }} props
 */
export default function HistoryList({ records = [] }) {
  if (!records || records.length === 0) {
    return <HistoryEmptyState />;
  }

  return (
    <section aria-labelledby="history-list-heading" className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 id="history-list-heading" className="text-base font-semibold text-slate-900">
          Wake Sessions ({records.length})
        </h2>
        <span className="text-xs text-slate-500 font-medium">
          Showing latest records
        </span>
      </div>

      <div className="space-y-3">
        {records.map((session) => (
          <HistorySessionCard key={session.id} session={session} />
        ))}
      </div>
    </section>
  );
}
