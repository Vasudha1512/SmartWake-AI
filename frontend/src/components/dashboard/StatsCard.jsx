import React from 'react';

/**
 * StatsCard component
 * Displays cognitive performance and wake session statistics.
 * Designed to accept real API statistics in Phase 6 while displaying
 * an authentic, honest empty state when no sessions have occurred.
 *
 * @param {{
 *   stats?: {
 *     totalWakeUps?: number,
 *     completed?: number,
 *     failed?: number,
 *     completionRate?: number,
 *     averageDurationSec?: number
 *   } | null
 * }} props
 */
export default function StatsCard({ stats = null }) {
  const hasData = stats && typeof stats.totalWakeUps === 'number' && stats.totalWakeUps > 0;

  const metrics = [
    {
      id: 'total',
      label: 'Total Wake-ups',
      value: hasData ? stats.totalWakeUps : '—',
      sublabel: 'Recorded sessions',
      icon: (
        <svg className="w-4 h-4 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      ),
    },
    {
      id: 'completed',
      label: 'Completed',
      value: hasData ? stats.completed : '—',
      sublabel: 'Verified challenges',
      icon: (
        <svg className="w-4 h-4 text-emerald-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
        </svg>
      ),
    },
    {
      id: 'rate',
      label: 'Completion Rate',
      value: hasData ? `${Math.round(stats.completionRate)}%` : '—',
      sublabel: 'First-attempt success',
      icon: (
        <svg className="w-4 h-4 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 7h8m0 0v8m0-8l-8 8-4-4-6 6" />
        </svg>
      ),
    },
    {
      id: 'avg_time',
      label: 'Avg Response Time',
      value: hasData ? `${stats.averageDurationSec}s` : '—',
      sublabel: 'Cognitive latency',
      icon: (
        <svg className="w-4 h-4 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
      ),
    },
  ];

  return (
    <section
      aria-labelledby="stats-heading"
      className="rounded-2xl bg-white border border-slate-200 p-6 shadow-xs space-y-4"
    >
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 id="stats-heading" className="text-base font-semibold text-slate-900">
            Wake-up Statistics
          </h2>
          <p className="text-xs text-slate-600 mt-0.5">
            ML-tracked cognitive resolution and alertness performance metrics.
          </p>
        </div>

        <span className="text-xs px-2.5 py-1 rounded-full bg-slate-100 text-slate-600 font-medium">
          {hasData ? 'Live Data' : 'No Data Yet'}
        </span>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        {metrics.map((metric) => (
          <div
            key={metric.id}
            className="p-4 rounded-xl bg-slate-50 border border-slate-200 flex flex-col justify-between"
          >
            <div className="flex items-center justify-between gap-2 mb-2">
              <span className="text-xs font-medium text-slate-600">{metric.label}</span>
              <div className="p-1.5 rounded-lg bg-white border border-slate-200 shadow-2xs">
                {metric.icon}
              </div>
            </div>
            <div className="text-2xl sm:text-3xl font-bold text-slate-900 tracking-tight font-mono">
              {metric.value}
            </div>
            <div className="text-[11px] text-slate-500 mt-1">
              {metric.sublabel}
            </div>
          </div>
        ))}
      </div>

      {!hasData && (
        <div className="p-3.5 rounded-xl bg-slate-50 border border-dashed border-slate-200 flex items-center gap-3 text-xs text-slate-600">
          <svg className="w-4 h-4 text-indigo-600 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
          <span>
            No wake-up data yet. Your cognitive response rates and duration statistics will compute automatically as sessions complete.
          </span>
        </div>
      )}
    </section>
  );
}
