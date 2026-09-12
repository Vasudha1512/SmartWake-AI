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
      className="rounded-2xl bg-slate-900/60 border border-slate-800 p-6 shadow-lg space-y-4"
    >
      <div className="flex items-center justify-between gap-4">
        <div>
          <h2 id="recent-wakeups-heading" className="text-base font-semibold text-white">
            Recent Wake-ups
          </h2>
          <p className="text-xs text-slate-400 mt-0.5">
            Historical log of recent wake sessions, challenge difficulties, and response times.
          </p>
        </div>

        <Link
          to="/history"
          className="text-xs font-semibold text-indigo-400 hover:text-indigo-300 transition-colors"
        >
          View History &rarr;
        </Link>
      </div>

      {!hasSessions ? (
        <div className="py-10 text-center space-y-3 rounded-xl bg-slate-950/40 border border-dashed border-slate-800/80 p-6">
          <div className="w-10 h-10 rounded-xl bg-slate-900 border border-slate-800 text-slate-400 flex items-center justify-center mx-auto">
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
            </svg>
          </div>
          <div className="space-y-1">
            <p className="text-sm font-semibold text-white">
              No wake-up sessions yet
            </p>
            <p className="text-xs text-slate-400 max-w-sm mx-auto">
              Your completed wake-ups, challenge scores, and ML difficulty adaptations will appear here after alarms trigger.
            </p>
          </div>
          <div className="pt-2">
            <Link
              to="/history"
              className="inline-flex items-center justify-center px-3.5 py-1.5 rounded-lg text-xs font-medium text-slate-300 bg-slate-800 hover:bg-slate-700 hover:text-white transition-colors border border-slate-700"
            >
              Check History Archive
            </Link>
          </div>
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs">
            <thead className="border-b border-slate-800 text-slate-400">
              <tr>
                <th scope="col" className="pb-3 font-medium">Date &amp; Time</th>
                <th scope="col" className="pb-3 font-medium">Challenge</th>
                <th scope="col" className="pb-3 font-medium">Difficulty</th>
                <th scope="col" className="pb-3 font-medium">Status</th>
                <th scope="col" className="pb-3 font-medium text-right">Duration</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-800/60">
              {sessions.map((session) => (
                <tr key={session.id} className="hover:bg-slate-800/30 transition-colors">
                  <td className="py-3 font-medium text-white">{session.timestamp}</td>
                  <td className="py-3 text-indigo-300">{session.challengeType}</td>
                  <td className="py-3 text-purple-300">{session.difficulty}</td>
                  <td className="py-3">
                    <span
                      className={`inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold ${
                        session.status === 'completed'
                          ? 'bg-emerald-950 text-emerald-400 border border-emerald-800/50'
                          : session.status === 'snoozed'
                          ? 'bg-amber-950 text-amber-400 border border-amber-800/50'
                          : 'bg-rose-950 text-rose-400 border border-rose-800/50'
                      }`}
                    >
                      {session.status}
                    </span>
                  </td>
                  <td className="py-3 text-right text-slate-300 font-mono">
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
