import React from 'react';

/**
 * Format total seconds into MM:SS string
 * @param {number} totalSeconds
 * @returns {string}
 */
function formatCountdown(totalSeconds) {
  const safeSeconds = Math.max(0, Math.floor(totalSeconds || 0));
  const mins = Math.floor(safeSeconds / 60);
  const secs = safeSeconds % 60;
  return `${String(mins).padStart(2, '0')}:${String(secs).padStart(2, '0')}`;
}

/**
 * SnoozeStatus component
 * Handles snooze statistics display, active countdown card, and completion banner.
 *
 * @param {{
 *   mode?: 'badge' | 'banner' | 'active_card',
 *   snoozeCount: number,
 *   snoozeDuration?: number | null,
 *   snoozeStatus?: 'idle' | 'selecting' | 'snoozed' | 'finished',
 *   remainingSeconds?: number,
 *   onFastForwardDemo?: () => void
 * }} props
 */
export default function SnoozeStatus({
  mode = 'badge',
  snoozeCount = 0,
  snoozeDuration = null,
  snoozeStatus = 'idle',
  remainingSeconds = 0,
  onFastForwardDemo,
}) {
  // Format snooze count label according to specification
  const getCountLabel = () => {
    if (snoozeCount === 0) {
      return 'No snoozes yet';
    }
    if (snoozeCount === 1) {
      return snoozeDuration ? `Snoozed 1 time (latest: ${snoozeDuration} min)` : 'Snoozed 1 time';
    }
    return `Snoozed ${snoozeCount} times${snoozeDuration ? ` (latest: ${snoozeDuration} min)` : ''}`;
  };

  // 1. Banner mode: shown when countdown finishes and challenge is ready
  if (mode === 'banner' || snoozeStatus === 'finished') {
    return (
      <div
        role="alert"
        className="p-4 rounded-xl bg-purple-50 border border-purple-200 text-center space-y-1 animate-fadeIn"
      >
        <div className="flex items-center justify-center gap-2 text-purple-800 font-semibold text-sm">
          <span className="w-2 h-2 rounded-full bg-purple-500 animate-ping"></span>
          <span>Your challenge is ready.</span>
        </div>
        <p className="text-xs text-slate-600">
          Snooze period has elapsed. Launch your challenge to prove alertness and silence the alarm.
        </p>
      </div>
    );
  }

  // 2. Active Card mode: shown during active snooze countdown
  if (mode === 'active_card' || snoozeStatus === 'snoozed') {
    return (
      <div
        role="region"
        aria-label="Active snooze countdown"
        className="text-center space-y-6 py-6 max-w-md mx-auto animate-fadeIn"
      >
        <div className="w-20 h-20 rounded-3xl bg-purple-50 text-purple-600 border border-purple-200 flex items-center justify-center mx-auto text-3xl shadow-xs animate-pulse">
          💤
        </div>

        <div className="space-y-2">
          <span className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold bg-purple-100 text-purple-800 border border-purple-200">
            <span className="w-2 h-2 rounded-full bg-purple-500 animate-ping"></span>
            <span>Snoozed for {snoozeDuration || 5} minutes</span>
          </span>

          <h2 className="text-3xl sm:text-4xl font-extrabold text-slate-900 tracking-tight font-mono">
            {formatCountdown(remainingSeconds)}
          </h2>

          <p className="text-sm font-medium text-purple-700">
            Challenge returns in {formatCountdown(remainingSeconds)}
          </p>

          <p className="text-xs text-slate-600 max-w-sm mx-auto leading-relaxed pt-1">
            The wake session remains active. When this timer reaches zero, your cognitive challenge will return automatically so you can dismiss the alarm.
          </p>
        </div>

        {/* Local Session Snooze Count Badge */}
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-700">
          <span className="text-slate-500">Session Status:</span>
          <span className="font-semibold text-purple-700">{getCountLabel()}</span>
        </div>

        {/* Developer Demo Testing Fast-Forward Control */}
        {onFastForwardDemo && (
          <div className="pt-2 border-t border-slate-200 space-y-2">
            <button
              type="button"
              onClick={onFastForwardDemo}
              aria-label="Fast-forward demo to expire snooze immediately"
              className="px-4 py-2 rounded-lg text-xs font-semibold text-amber-900 bg-amber-50 hover:bg-amber-100 border border-amber-300 transition-all cursor-pointer focus:outline-none focus:ring-2 focus:ring-amber-500 shadow-2xs"
            >
              ⚡ Fast-forward demo (expire timer)
            </button>
            <p className="text-[10px] text-slate-500">
              Developer/testing control only. Simulates countdown reaching zero.
            </p>
          </div>
        )}
      </div>
    );
  }

  // 3. Badge mode: compact session count display
  return (
    <span
      className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-slate-100 text-slate-700 border border-slate-200"
      aria-label={`Snooze status: ${getCountLabel()}`}
    >
      <svg className="w-3.5 h-3.5 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
      </svg>
      <span>{getCountLabel()}</span>
    </span>
  );
}
