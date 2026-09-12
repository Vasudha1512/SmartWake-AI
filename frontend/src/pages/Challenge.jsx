import React from 'react';
import { useLocation, Link } from 'react-router-dom';

/**
 * Challenge Page Placeholder
 * Reserved for Phase 5 — Step 4: Challenge Selection.
 * Receives the draft alarm configuration from Step 3.
 */
export default function Challenge() {
  const location = useLocation();
  const alarmDraft = location.state?.alarmDraft;

  return (
    <div className="space-y-6 max-w-2xl mx-auto">
      <div className="border-b border-slate-800 pb-4 flex items-center justify-between">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">
            Challenge Selection
          </h1>
          <p className="text-sm text-slate-400 mt-1">
            Configure your wake-up challenge domain and cognitive parameters.
          </p>
        </div>
        <Link
          to="/alarms"
          className="text-xs font-semibold text-indigo-400 hover:text-indigo-300 transition-colors"
        >
          &larr; Back to Alarm
        </Link>
      </div>

      <div className="p-8 rounded-2xl bg-slate-900/60 border border-dashed border-slate-700/80 text-center space-y-4">
        <div className="w-12 h-12 rounded-2xl bg-indigo-500/10 text-indigo-400 flex items-center justify-center mx-auto">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
          </svg>
        </div>
        <h2 className="text-lg font-medium text-white">Challenge Selection Placeholder</h2>
        <p className="text-sm text-slate-400 max-w-md mx-auto">
          This route is reserved for the Challenge Selection deliverable in Phase 5 Step 4.
          It will allow choosing between Math, Pattern, Memory, and Verbal challenges.
        </p>

        {alarmDraft && (
          <div className="p-4 rounded-xl bg-slate-950/70 border border-slate-800 text-left max-w-sm mx-auto space-y-1 text-xs">
            <span className="font-semibold text-slate-300 block mb-1">Configured Alarm from Step 3:</span>
            <div className="text-white font-mono">Time: {alarmDraft.time}</div>
            <div className="text-slate-400">Label: {alarmDraft.label}</div>
            <div className="text-slate-400">
              Schedule: {alarmDraft.selectedDays?.length > 0 ? alarmDraft.selectedDays.join(', ') : 'One-time'}
            </div>
          </div>
        )}

        <span className="inline-block px-3 py-1 text-xs font-semibold text-indigo-400 bg-indigo-950/60 border border-indigo-800/60 rounded-full">
          Scheduled for Phase 5 — Step 4
        </span>
      </div>
    </div>
  );
}
