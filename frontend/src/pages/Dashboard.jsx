import React from 'react';

export default function Dashboard() {
  return (
    <div className="space-y-6">
      <div className="border-b border-slate-800 pb-4">
        <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">Dashboard</h1>
        <p className="text-sm text-slate-400 mt-1">
          SmartWake AI central monitoring and overview hub.
        </p>
      </div>

      <div className="p-8 rounded-2xl bg-slate-900/60 border border-dashed border-slate-700/80 text-center space-y-4">
        <div className="w-12 h-12 rounded-2xl bg-indigo-500/10 text-indigo-400 flex items-center justify-center mx-auto">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2V6zM14 6a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2V6zM4 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2H6a2 2 0 01-2-2v-2zM14 16a2 2 0 012-2h2a2 2 0 012 2v2a2 2 0 01-2 2h-2a2 2 0 01-2-2v-2z" />
          </svg>
        </div>
        <h2 className="text-lg font-medium text-white">Dashboard Placeholder</h2>
        <p className="text-sm text-slate-400 max-w-md mx-auto">
          This route is reserved for the full Dashboard deliverable in Phase 5 Step 2.
          It will display active alarms, upcoming wake sessions, cognitive performance summaries, and recent activity.
        </p>
        <span className="inline-block px-3 py-1 text-xs font-semibold text-indigo-400 bg-indigo-950/60 border border-indigo-800/60 rounded-full">
          Scheduled for Phase 5 — Step 2
        </span>
      </div>
    </div>
  );
}
