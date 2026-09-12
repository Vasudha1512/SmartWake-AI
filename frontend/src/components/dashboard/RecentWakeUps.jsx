import React from 'react';
import { Link } from 'react-router-dom';

/**
 * RecentWakeUps component
 * Presents the user's latest wake session logs and cognitive challenge attempts.
 * Designed around FastAPI's WakeSession & Challenge schemas.
 * Displays an authentic empty state when no historical sessions exist.
 *
 * @param {{
 *   sessions?: Array<{
 *     id: string | number,
 *     timestamp: string,
 *     challengeType: string,
 *     difficulty: string,
 *     status: 'completed' | 'failed' | 'snoozed',
 *     durationSec: number
 *   }>
 * }} props
 */
export default function RecentWakeUps({ sessions = [] }) {
  const hasSessions = Array.isArray(sessions) && sessions.length > 0;

  return (
    <section
      aria-labelledby="recent-wakeups-heading"
      className="rounded-2xl bg-white border border-slate-200 p-6 shadow-xs space-y-4"
    >
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 id="recent-wakeups-heading" className="text-base font-semibold text-slate-900">
            Recent Wake-ups
          </h2>
          <p className="text-xs text-slate-600 mt-0.5">
            Historical log of recent wake sessions, challenge difficulties, and response times.
          </p>
        </div>

        <Link
          to="/history"
          className="text-xs font-semibold text-indigo-600 hover:text-indigo-700 transition-colors"
        >
          View History &rarr;
        </Link>
      </div>

      {!hasSessions ? (
        <div className="py-10 text-center space-y-3 rounded-xl bg-slate-50 border border-dashed border-slate-200 p-6">
          <div className="w-10 h-10 rounded-xl bg-white border border-slate-200 text-slate-500 flex items-center justify-center mx-auto shadow-2xs">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div className="space-y-1">
            <p className="text-sm font-semibold text-slate-900">
              No wake-up sessions yet
            </p>
            <p className="text-xs text-slate-600 max-w-sm mx-auto">
              Your completed wake-ups, challenge scores, and ML difficulty adaptations will appear here after alarms trigger.
            </p>
          </div>
          <div className="pt-2">
            <Link
              to="/history"
              className="inline-flex items-center justify-center px-3.5 py-1.5 rounded-lg text-xs font-medium text-slate-700 bg-white hover:bg-slate-50 transition-colors border border-slate-300 shadow-2xs"
            >
              Check History Archive
            </Link>
          </div>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-slate-200 text-slate-500">
              <tr>
                <th scope="col" className="pb-3 font-medium">Date &amp; Time</th>
                <th scope="col" className="pb-3 font-medium">Challenge</th>
                <th scope="col" className="pb-3 font-medium">Difficulty</th>
                <th scope="col" className="pb-3 font-medium">Status</th>
                <th scope="col" className="pb-3 font-medium text-right">Duration</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {sessions.map((session) => (
                <tr key={session.id} className="hover:bg-slate-50 transition-colors">
                  <td className="py-3 font-medium text-slate-900">{session.timestamp}</td>
                  <td className="py-3 text-indigo-700">{session.challengeType}</td>
                  <td className="py-3 text-purple-700">{session.difficulty}</td>
                  <td className="py-3">
                    <span
                      className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold ${
                        session.status === 'completed'
                          ? 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                          : session.status === 'snoozed'
                          ? 'bg-amber-50 text-amber-700 border border-amber-200'
                          : 'bg-rose-50 text-rose-700 border border-rose-200'
                      }`}
                    >
                      {session.status}
                    </span>
                  </td>
                  <td className="py-3 text-right text-slate-600 font-mono">
                    {`${session.durationSec}s`}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
