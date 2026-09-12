import React, { useState } from 'react';

/**
 * PushupChallenge component
 * Frontend demo interface for physical motor activation / push-ups.
 *
 * @param {{
 *   onComplete: () => void,
 *   onFail?: () => void
 * }} props
 */
export default function PushupChallenge({ onComplete, onFail }) {
  const [reps, setReps] = useState(0);
  const [error, setError] = useState(null);

  const TARGET_REPS = 5;

  const handleIncrement = () => {
    setReps((prev) => prev + 1);
    if (error) setError(null);
  };

  const handleDecrement = () => {
    setReps((prev) => Math.max(0, prev - 1));
    if (error) setError(null);
  };

  const handleVerify = (e) => {
    e.preventDefault();

    if (reps >= TARGET_REPS) {
      setError(null);
      onComplete();
    } else {
      setError(`Target is ${TARGET_REPS} push-ups (completed: ${reps}). Keep going!`);
      if (onFail) onFail();
    }
  };

  return (
    <div className="space-y-6 max-w-md mx-auto text-center">
      {/* Instructions */}
      <div className="space-y-1">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-amber-500/10 text-amber-400 border border-amber-500/20">
          <span>💪 Push-ups Physical Challenge</span>
        </div>
        <h3 className="text-xl font-bold text-white tracking-tight">
          {`Complete ${TARGET_REPS} Push-ups`}
        </h3>
        <p className="text-xs text-slate-400">
          Perform full repetitions to stimulate blood circulation and alert motor centers.
        </p>
      </div>

      {/* Camera / Pose Estimation Placeholder */}
      <div className="p-5 rounded-2xl bg-slate-950/70 border-2 border-dashed border-slate-800 space-y-2">
        <div className="w-12 h-12 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-center text-xl mx-auto text-amber-400">
          💪
        </div>
        <p className="text-xs font-semibold text-slate-300">
          Camera / Computer Vision Rep Counter
        </p>
        <p className="text-[11px] text-slate-400 max-w-xs mx-auto">
          Automated skeletal pose tracking and repetition counting will be connected in Phase 6 backend integration.
        </p>
        <span className="inline-block text-[10px] font-mono text-amber-400 px-2 py-0.5 rounded bg-amber-950/60 border border-amber-800/50">
          POSE SIMULATION
        </span>
      </div>

      {/* Manual Rep Counter for Demo */}
      <div className="p-6 rounded-2xl bg-slate-950 border border-slate-800 space-y-4">
        <span className="text-xs font-medium text-slate-400 block">
          Demo Repetition Counter (Target: {TARGET_REPS})
        </span>

        <div className="flex items-center justify-center gap-6">
          <button
            type="button"
            onClick={handleDecrement}
            className="w-10 h-10 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-700 flex items-center justify-center text-xl font-bold transition-colors cursor-pointer"
            aria-label="Decrease reps"
          >
            &minus;
          </button>

          <span className="text-4xl font-mono font-extrabold text-white w-16 text-center">
            {reps}
          </span>

          <button
            type="button"
            onClick={handleIncrement}
            className="w-10 h-10 rounded-xl bg-slate-900 hover:bg-slate-800 text-slate-300 border border-slate-700 flex items-center justify-center text-xl font-bold transition-colors cursor-pointer"
            aria-label="Increase reps"
          >
            +
          </button>
        </div>

        {error && (
          <div role="alert" className="p-2.5 rounded-xl bg-rose-950/40 border border-rose-900/60 text-xs text-rose-300 flex items-center justify-center gap-2">
            <svg className="w-4 h-4 text-rose-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="10" strokeWidth="2"></circle>
              <path d="M12 8v4m0 4h.01" strokeWidth="2" strokeLinecap="round"></path>
            </svg>
            <span>{error}</span>
          </div>
        )}

        <button
          type="button"
          onClick={handleVerify}
          className="w-full py-3 rounded-xl text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-500 shadow-lg shadow-indigo-600/30 transition-all cursor-pointer focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          Verify Repetitions
        </button>
      </div>
    </div>
  );
}
