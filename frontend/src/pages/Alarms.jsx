import React from 'react';

export default function Alarms() {
  return (
    <div className="space-y-6">
      <div className="border-b border-slate-800 pb-4">
        <h1 className="text-2xl sm:text-3xl font-bold text-white tracking-tight">Alarms</h1>
        <p className="text-sm text-slate-400 mt-1">
          Alarm configuration, scheduling, and challenge assignment.
        </p>
      </div>

      <div className="p-8 rounded-2xl bg-slate-900/60 border border-dashed border-slate-700/80 text-center space-y-4">
        <div className="w-12 h-12 rounded-2xl bg-indigo-500/10 text-indigo-400 flex items-center justify-center mx-auto">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </div>
        <h2 className="text-lg font-medium text-white">Alarm Management Placeholder</h2>
        <p className="text-sm text-slate-400 max-w-md mx-auto">
          This route is reserved for Alarm Creation and Management in Phase 5 Step 3.
          It will allow users to create, enable/disable, schedule alarms, and configure challenge preferences.
        </p>
        <span className="inline-block px-3 py-1 text-xs font-semibold text-indigo-400 bg-indigo-950/60 border border-indigo-800/60 rounded-full">
          Scheduled for Phase 5 — Step 3
        </span>
      </div>
    </div>
  );
}
