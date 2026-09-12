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
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
          <span>💪 Push-ups Physical Challenge</span>
        </div>
        <h3 className="text-xl font-bold text-slate-900 tracking-tight">
          {`Complete ${TARGET_REPS} Push-ups`}
        </h3>
        <p className="text-xs text-slate-600">
          Perform full repetitions to stimulate blood circulation and alert motor centers.
        </p>
      </div>

      {/* Camera / Pose Estimation Placeholder */}
      <div className="p-5 rounded-2xl bg-slate-50 border-2 border-dashed border-slate-300 space-y-2">
        <div className="w-12 h-12 rounded-xl bg-white border border-slate-200 flex items-center justify-center text-xl mx-auto text-amber-600 shadow-2xs">
          💪
        </div>
        <p className="text-xs font-semibold text-slate-800">
          Camera / Computer Vision Rep Counter
        </p>
        <p className="text-[11px] text-slate-500 max-w-xs mx-auto">
          Automated skeletal pose tracking and repetition counting will be connected in Phase 6 backend integration.
        </p>
        <span className="inline-block text-[10px] font-mono text-amber-800 px-2 py-0.5 rounded bg-amber-100 border border-amber-200">
          POSE SIMULATION
        </span>
      </div>

      {/* Manual Rep Counter for Demo */}
      <div className="p-6 rounded-2xl bg-slate-50 border border-slate-200 space-y-4 shadow-xs">
        <span className="text-xs font-medium text-slate-600 block">
          Demo Repetition Counter (Target: {TARGET_REPS})
        </span>

        <div className="flex items-center justify-center gap-6">
          <button
            type="button"
            onClick={handleDecrement}
            className="w-10 h-10 rounded-xl bg-white hover:bg-slate-100 text-slate-700 border border-slate-300 flex items-center justify-center text-xl font-bold transition-colors cursor-pointer shadow-2xs"
            aria-label="Decrease reps"
          >
            &minus;
          </button>

          <span className="text-4xl font-mono font-extrabold text-slate-900 w-16 text-center">
            {reps}
          </span>

          <button
            type="button"
            onClick={handleIncrement}
            className="w-10 h-10 rounded-xl bg-white hover:bg-slate-100 text-slate-700 border border-slate-300 flex items-center justify-center text-xl font-bold transition-colors cursor-pointer shadow-2xs"
            aria-label="Increase reps"
          >
            +
          </button>
        </div>

        {error && (
          <div role="alert" className="p-2.5 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-700 flex items-center justify-center gap-2">
            <svg className="w-4 h-4 text-rose-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="10" strokeWidth="2"></circle>
              <path d="M12 8v4m0 4h.01" strokeWidth="2" strokeLinecap="round"></path>
            </svg>
            <span>{error}</span>
          </div>
        )}

        <button
          type="button"
          onClick={handleVerify}
          className="w-full py-3 rounded-xl text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 shadow-md shadow-indigo-600/20 transition-all cursor-pointer focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          Verify Repetitions
        </button>
      </div>
    </div>
  );
}
