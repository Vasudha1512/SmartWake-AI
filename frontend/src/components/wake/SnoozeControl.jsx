import React from 'react';

/**
 * SnoozeControl component
 * Renders the secondary Snooze action on the Wake Screen.
 * Visually subordinate to the primary "Start Challenge" action.
 *
 * @param {{
 *   onOpenSelector: () => void,
 *   disabled?: boolean
 * }} props
 */
export default function SnoozeControl({ onOpenSelector, disabled = false }) {
  return (
    <button
      type="button"
      onClick={onOpenSelector}
      disabled={disabled}
      aria-label="Snooze alarm and choose duration"
      className="w-full sm:w-auto px-5 py-2.5 rounded-xl text-sm font-medium text-slate-700 bg-white hover:bg-slate-50 hover:text-slate-900 border border-slate-300 transition-all cursor-pointer focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-offset-2 focus:ring-offset-white disabled:opacity-50 disabled:cursor-not-allowed inline-flex items-center justify-center gap-2 shadow-2xs"
    >
      <svg
        className="w-4 h-4 text-purple-600"
        fill="none"
        stroke="currentColor"
        viewBox="0 0 24 24"
        aria-hidden="true"
      >
        <path
          strokeLinecap="round"
          strokeLinejoin="round"
          strokeWidth="2"
          d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z"
        />
      </svg>
      <span>Snooze</span>
      <span className="text-xs text-slate-500 font-normal">
        &bull; Need a few more minutes?
      </span>
    </button>
  );
}
