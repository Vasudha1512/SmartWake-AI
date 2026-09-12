import React from 'react';
import { Link } from 'react-router-dom';

/**
 * AlarmOverviewCard component
 * Provides a compact overview of alarm configuration and active state.
 *
 * @param {{
 *   activeCount?: number,
 *   upcomingTime?: string | null,
 *   challengeDomain?: string | null,
 *   difficultyMode?: string | null
 * }} props
 */
export default function AlarmOverviewCard({
  activeCount = 0,
  upcomingTime = null,
  challengeDomain = null,
  difficultyMode = null,
}) {
  const hasAlarms = activeCount > 0;

  return (
    <section
      aria-labelledby="alarm-overview-heading"
      className="rounded-2xl bg-slate-900/60 border border-slate-800 p-6 flex flex-col justify-between shadow-lg"
    >
      <div className="flex items-center justify-between gap-4 mb-4">
        <h2 id="alarm-overview-heading" className="text-base font-semibold text-white">
          Alarm Overview
        </h2>
        <span
          className={`text-xs px-2.5 py-0.5 rounded-full font-medium ${
            hasAlarms
              ? 'bg-indigo-950/80 text-indigo-400 border border-indigo-800/60'
              : 'bg-slate-800 text-slate-400'
          }`}
        >
          {activeCount} Active
        </span>
      </div>

      {!hasAlarms ? (
        <div className="py-4 space-y-3">
          <p className="text-sm font-medium text-slate-200">
            No active alarms
          </p>
          <p className="text-xs text-slate-400 leading-relaxed">
            Create your first SmartWake alarm to customize schedules, cognitive challenge domains, and adaptive difficulty.
          </p>
          <div className="pt-1">
            <Link
              to="/alarms"
              className="inline-flex items-center text-xs font-semibold text-indigo-400 hover:text-indigo-300 transition-colors"
            >
              Set up your first alarm &rarr;
            </Link>
          </div>
        </div>
      ) : (
        <div className="grid grid-cols-2 gap-4 py-2">
          <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/80">
            <span className="text-[11px] uppercase tracking-wider text-slate-400 block mb-1">
              Next Ring
            </span>
            <span className="text-base font-bold text-white block">
              {upcomingTime || '—'}
            </span>
          </div>

          <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/80">
            <span className="text-[11px] uppercase tracking-wider text-slate-400 block mb-1">
              Active Count
            </span>
            <span className="text-base font-bold text-white block">
              {activeCount}
            </span>
          </div>

          <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/80">
            <span className="text-[11px] uppercase tracking-wider text-slate-400 block mb-1">
              Challenge
            </span>
            <span className="text-sm font-semibold text-indigo-300 block truncate">
              {challengeDomain || 'Adaptive'}
            </span>
          </div>

          <div className="p-3 rounded-xl bg-slate-950/60 border border-slate-800/80">
            <span className="text-[11px] uppercase tracking-wider text-slate-400 block mb-1">
              Difficulty
            </span>
            <span className="text-sm font-semibold text-purple-300 block truncate">
              {difficultyMode || 'ML Optimized'}
            </span>
          </div>
        </div>
      )}

      <div className="pt-4 border-t border-slate-800/80 flex items-center justify-between text-xs">
        <span className="text-slate-500">FastAPI Alarm Registry</span>
        <Link
          to="/alarms"
          className="text-slate-400 hover:text-white transition-colors"
        >
          Manage All Alarms
        </Link>
      </div>
    </section>
  );
}
