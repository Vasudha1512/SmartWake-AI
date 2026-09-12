import React from 'react';
import HistorySummaryCard from './HistorySummaryCard';
import { calculateHistorySummary } from '../../data/demoHistory';

/**
 * HistorySummary component
 * Calculates and displays dynamic summary metrics from history records.
 *
 * @param {{
 *   records: Array<{
 *     status: 'completed' | 'failed',
 *     snoozeCount?: number
 *   }>
 * }} props
 */
export default function HistorySummary({ records = [] }) {
  const summary = calculateHistorySummary(records);

  const metrics = [
    {
      id: 'total',
      label: 'Total Wake-ups',
      value: summary.totalWakeUps,
      sublabel: 'Recorded alarm sessions',
      icon: (
        <svg className="w-4 h-4 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <circle cx="12" cy="13" r="8" strokeWidth="2"></circle>
          <path d="M12 9v4l2 2" strokeWidth="2" strokeLinecap="round"></path>
          <path d="M5 3 2 6" strokeWidth="2" strokeLinecap="round"></path>
          <path d="m22 6-3-3" strokeWidth="2" strokeLinecap="round"></path>
        </svg>
      ),
    },
    {
      id: 'successful',
      label: 'Successful',
      value: summary.successful,
      sublabel: 'Verified alertness',
      icon: (
        <svg className="w-4 h-4 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      ),
    },
    {
      id: 'failed',
      label: 'Failed',
      value: summary.failed,
      sublabel: 'Incomplete challenges',
      icon: (
        <svg className="w-4 h-4 text-rose-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <circle cx="12" cy="12" r="10" strokeWidth="2"></circle>
          <path d="M15 9l-6 6M9 9l6 6" strokeWidth="2" strokeLinecap="round"></path>
        </svg>
      ),
    },
    {
      id: 'avg-snooze',
      label: 'Average Snoozes',
      value: summary.averageSnoozes,
      sublabel: 'Snoozes per session',
      icon: (
        <svg className="w-4 h-4 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      ),
    },
  ];

  return (
    <section aria-labelledby="history-summary-heading" className="space-y-3">
      <h2 id="history-summary-heading" className="sr-only">
        Wake History Summary Metrics
      </h2>
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {metrics.map((metric) => (
          <HistorySummaryCard
            key={metric.id}
            label={metric.label}
            value={metric.value}
            sublabel={metric.sublabel}
            icon={metric.icon}
          />
        ))}
      </div>
    </section>
  );
}
