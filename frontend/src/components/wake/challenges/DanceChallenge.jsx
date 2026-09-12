import React from 'react';

/**
 * DanceChallenge component
 * Frontend demo interface for the Dance movement verification challenge.
 *
 * @param {{
 *   onComplete: () => void
 * }} props
 */
export default function DanceChallenge({ onComplete }) {
  return (
    <div className="space-y-6 text-center">
      {/* Instructions */}
      <div className="space-y-1">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-purple-500/10 text-purple-400 border border-purple-500/20">
          <span>🕺 Dance Movement Challenge</span>
        </div>
        <h3 className="text-xl font-bold text-white tracking-tight">
          Perform Morning Movement Sequence
        </h3>
        <p className="text-xs text-slate-400 max-w-md mx-auto">
          Stand in clear view and replicate the rhythmic movement sequence to verify motor coordination.
        </p>
      </div>

      {/* Sensor / Camera Viewport Placeholder */}
      <div className="relative aspect-video max-w-md mx-auto rounded-2xl bg-slate-950 border-2 border-dashed border-slate-800 flex flex-col items-center justify-center p-6 overflow-hidden">
        {/* Animated Scanning Line */}
        <div className="absolute inset-x-0 top-0 h-0.5 bg-gradient-to-r from-transparent via-purple-400 to-transparent animate-pulse" />

        <div className="w-16 h-16 rounded-2xl bg-slate-900 border border-slate-800 flex items-center justify-center text-3xl mb-3 shadow-inner">
          🕺
        </div>

        <p className="text-sm font-semibold text-slate-200">
          Camera / Movement Sensor Feed
        </p>
        <p className="text-xs text-slate-400 mt-1 max-w-xs text-center">
          Real-time pose estimation and movement verification will be connected in Phase 6 backend integration.
        </p>

        <span className="mt-3 text-[11px] font-mono text-purple-400 px-2 py-0.5 rounded bg-purple-950/60 border border-purple-800/50">
          DEMO SIMULATION
        </span>
      </div>

      {/* Demo Action Button */}
      <div className="pt-2">
        <button
          type="button"
          onClick={onComplete}
          className="inline-flex items-center justify-center px-6 py-3 rounded-xl text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-500 shadow-lg shadow-indigo-600/30 transition-all cursor-pointer focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          <span>Complete Demo Challenge</span>
          <svg className="w-4 h-4 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
          </svg>
        </button>
      </div>
    </div>
  );
}
