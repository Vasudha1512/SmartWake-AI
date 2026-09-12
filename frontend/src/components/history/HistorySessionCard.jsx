import React from 'react';
import { CHALLENGE_META } from '../../data/demoHistory';

/**
 * HistorySessionCard component
 * Displays a single historical wake-up session with challenge results,
 * status badge, snooze count, duration, and ML difficulty indicator.
 *
 * @param {{
 *   session: {
 *     id: string | number,
 *     date: string,
 *     alarmTime: string,
 *     challengeType: 'dance' | 'math' | 'memory' | 'tongue_twister' | 'pushups' | string,
 *     status: 'completed' | 'failed' | string,
 *     snoozeCount: number,
 *     completionDurationSeconds: number,
 *     difficulty?: string
 *   }
 * }} props
 */
export default function HistorySessionCard({ session }) {
  const meta = CHALLENGE_META[session.challengeType] || {
    name: session.challengeType,
    icon: '⚡',
  };

  const isCompleted = session.status === 'completed';
  const isAdaptive = session.difficulty?.toLowerCase().includes('adaptive');

  return (
    <article
      aria-labelledby={`session-title-${session.id}`}
      className="p-5 rounded-2xl bg-white border border-slate-200 shadow-xs hover:border-slate-300 transition-colors space-y-4"
    >
      {/* Top Header Row */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-center gap-3">
          <div
            className="w-10 h-10 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-center text-xl shrink-0"
            aria-hidden="true"
          >
            {meta.icon}
          </div>
          <div>
            <h3
              id={`session-title-${session.id}`}
              className="text-sm font-semibold text-slate-900"
            >
              {meta.name} Challenge
            </h3>
            <p className="text-xs text-slate-500 font-medium">
              {session.date} &bull; Alarm at {session.alarmTime}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-2">
          {/* Difficulty Badge */}
          {session.difficulty && (
            <span
              className={`inline-flex items-center px-2.5 py-1 rounded-md text-xs font-medium border ${
                isAdaptive
                  ? 'bg-purple-50 text-purple-700 border-purple-200'
                  : 'bg-slate-100 text-slate-700 border-slate-200'
              }`}
              title={
                isAdaptive
                  ? 'ML-adaptive difficulty demo label'
                  : `Difficulty level: ${session.difficulty}`
              }
            >
              {session.difficulty}
              {isAdaptive && (
                <span className="ml-1 text-[10px] text-purple-500 font-normal">
                  (Demo ML)
                </span>
              )}
            </span>
          )}

          {/* Status Badge */}
          <span
            className={`inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-semibold border ${
              isCompleted
                ? 'bg-emerald-50 text-emerald-700 border-emerald-200'
                : 'bg-rose-50 text-rose-700 border-rose-200'
            }`}
          >
            {isCompleted ? (
              <>
                <svg
                  className="w-3.5 h-3.5 text-emerald-600"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2.5"
                    d="M5 13l4 4L19 7"
                  />
                </svg>
                <span>Completed</span>
              </>
            ) : (
              <>
                <svg
                  className="w-3.5 h-3.5 text-rose-600"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                  aria-hidden="true"
                >
                  <path
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    strokeWidth="2.5"
                    d="M6 18L18 6M6 6l12 12"
                  />
                </svg>
                <span>Failed</span>
              </>
            )}
          </span>
        </div>
      </div>

      {/* Metrics Row */}
      <div className="grid grid-cols-2 sm:grid-cols-3 gap-3 pt-3 border-t border-slate-100 text-xs">
        <div>
          <span className="text-slate-500 block">Snooze Count</span>
          <span className="font-semibold text-slate-900 mt-0.5 block">
            {session.snoozeCount === 0
              ? '0 snoozes'
              : session.snoozeCount === 1
              ? '1 snooze'
              : `${session.snoozeCount} snoozes`}
          </span>
        </div>

        <div>
          <span className="text-slate-500 block">Completion Duration</span>
          <span className="font-semibold text-slate-900 font-mono mt-0.5 block">
            {session.completionDurationSeconds != null
              ? `${session.completionDurationSeconds}s`
              : '—'}
          </span>
        </div>

        <div className="col-span-2 sm:col-span-1">
          <span className="text-slate-500 block">Alarm Time</span>
          <span className="font-semibold text-slate-900 mt-0.5 block">
            {session.alarmTime}
          </span>
        </div>
      </div>
    </article>
  );
}
