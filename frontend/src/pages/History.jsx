import React from 'react';
import HistoryHeader from '../components/history/HistoryHeader';
import HistorySummary from '../components/history/HistorySummary';
import HistoryList from '../components/history/HistoryList';
import { DEMO_HISTORY } from '../data/demoHistory';

/**
 * History page
 *
 * Displays wake-up history, dynamic summary metrics, and challenge logs.
 * In Phase 5, consumes isolated frontend demonstration data (DEMO_HISTORY).
 * Structured to seamlessly receive FastAPI data in Phase 6 without refactoring.
 */
export default function History() {
  // During Phase 5, records are sourced from isolated frontend demo data.
  // In Phase 6, this will be populated via FastAPI response hook/fetch.
  const records = DEMO_HISTORY;

  return (
    <div className="space-y-6 max-w-5xl mx-auto pb-12">
      <HistoryHeader />
      <HistorySummary records={records} />
      <HistoryList records={records} />
    </div>
  );
}
