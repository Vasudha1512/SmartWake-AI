import React from 'react';
import { Link } from 'react-router-dom';

/**
 * NextAlarmCard component
 * Displays prominent next upcoming alarm or an accessible empty state
 * when no alarm has been scheduled yet.
 *
 * @param {{
 *   alarm?: {
 *     time: string,
 *     label?: string,
 *     challengeType?: string,
 *     difficulty?: string,
 *     days?: string,
 *     enabled?: boolean
 *   } | null
 * }} props
 */
export default function NextAlarmCard({ alarm = null }) {
  if (!alarm) {
    return (
      <section
        aria-labelledby="next-alarm-heading"
        className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-slate-900/90 to-slate-900/50 border border-slate-800 p-6 sm:p-8 flex flex-col justify-between shadow-xl"
      >
        <div className="flex items-center justify-between gap-4 mb-4">
          <div className="flex items-center gap-2">
            <span className="p-2 rounded-xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <circle cx="12" cy="13" r="8" strokeWidth="2"></circle>
                <path d="M12 9v4l2 2" strokeWidth="2" strokeLinecap="round"></path>
                <path d="M5 3 2 6" strokeWidth="2" strokeLinecap="round"></path>
                <path d="m22 6-3-3" strokeWidth="2" strokeLinecap="round"></path>
              </svg>
            </span>
            <h2 id="next-alarm-heading" className="text-base font-semibold text-white">
              Next Alarm
            </h2>
          </div>
          <span className="text-xs px-2.5 py-1 rounded-full bg-slate-800 text-slate-400 font-medium">
            Inactive
          </span>
        </div>

        <div className="my-6 text-center sm:text-left space-y-2">
          <p className="text-2xl sm:text-3xl font-bold text-white tracking-tight">
            No alarm configured yet
          </p>
          <p className="text-sm text-slate-400 max-w-md">
            Configure your first SmartWake alarm to awaken with adaptive GenAI challenges tailored to your cognitive profile.
          </p>
        </div>

        <div className="pt-2 flex flex-wrap items-center gap-3">
          <Link
            to="/alarms"
            className="inline-flex items-center justify-center px-4 py-2.5 rounded-xl text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-500 shadow-md shadow-indigo-600/20 transition-colors focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" />
            </svg>
            Create Alarm
          </Link>
          <span className="text-xs text-slate-500">
            Supports Math, Logic, and Multi-domain challenges
          </span>
        </div>
      </section>
    );
  }

  return (
    <section
      aria-labelledby="next-alarm-heading"
      className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-indigo-950/40 via-slate-900 to-slate-900 border border-slate-800 p-6 sm:p-8 flex flex-col justify-between shadow-xl"
    >
      <div className="flex items-center justify-between gap-4">
        <div className="flex items-center gap-2">
          <span className="p-2 rounded-xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <circle cx="12" cy="13" r="8" strokeWidth="2"></circle>
              <path d="M12 9v4l2 2" strokeWidth="2" strokeLinecap="round"></path>
            </svg>
          </span>
          <h2 id="next-alarm-heading" className="text-base font-semibold text-white">
            Next Alarm
          </h2>
        </div>
        <span className="text-xs px-2.5 py-1 rounded-full bg-emerald-950/60 text-emerald-400 border border-emerald-800/40 font-medium">
          Scheduled
        </span>
      </div>

      <div className="my-6">
        <div className="text-4xl sm:text-5xl font-extrabold text-white tracking-tight">
          {alarm.time}
        </div>
        <div className="flex flex-wrap items-center gap-2 mt-3">
          {alarm.challengeType && (
            <span className="px-2.5 py-1 rounded-lg text-xs font-medium bg-slate-800 text-indigo-300 border border-slate-700">
              {alarm.challengeType}
            </span>
          )}
          {alarm.difficulty && (
            <span className="px-2.5 py-1 rounded-lg text-xs font-medium bg-slate-800 text-purple-300 border border-slate-700">
              {alarm.difficulty}
            </span>
          )}
          {alarm.days && (
            <span className="px-2.5 py-1 rounded-lg text-xs font-medium bg-slate-800 text-slate-300 border border-slate-700">
              {alarm.days}
            </span>
          )}
        </div>
      </div>

      <div className="pt-2 flex items-center justify-between border-t border-slate-800/60">
        <span className="text-xs text-slate-400">
          {alarm.label || 'Standard Wake Schedule'}
        </span>
        <Link
          to="/alarms"
          className="text-sm font-medium text-indigo-400 hover:text-indigo-300 transition-colors"
        >
          Edit Alarm &rarr;
        </Link>
      </div>
    </section>
  );
}
