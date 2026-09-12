import React from 'react';

export default function Wake() {
  return (
    <div className="space-y-6">
      <div className="border-b border-slate-800 pb-4">
        <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">Active Wake Session</h1>
        <p className="text-sm text-slate-400 mt-1">
          Cognitive wake screen, alarm ringing, challenge execution, and snooze controls.
        </p>
      </div>

      <div className="p-8 rounded-2xl bg-slate-900/60 border border-dashed border-slate-700/80 text-center space-y-4">
        <div className="w-12 h-12 rounded-2xl bg-amber-500/10 text-amber-400 flex items-center justify-center mx-auto">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
          </svg>
        </div>
        <h2 className="text-lg font-medium text-white">Wake Screen &amp; Snooze Placeholder</h2>
        <p className="text-sm text-slate-400 max-w-md mx-auto">
          This route is reserved for the Wake Screen &amp; Snooze UI deliverables in Phase 5 Steps 5 and 6.
          It will host full-screen alarm ringing, GenAI challenge rendering, cognitive response inputs, and snooze flows.
        </p>
        <span className="inline-block px-3 py-1 text-xs font-semibold text-amber-400 bg-amber-950/60 border border-amber-800/60 rounded-full">
          Scheduled for Phase 5 — Steps 5 &amp; 6
        </span>
      </div>
    </div>
  );
}
