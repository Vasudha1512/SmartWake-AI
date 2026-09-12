import React from 'react';

/**
 * AlarmSettings component
 * Controls alarm enabled toggle state and optional descriptive label.
 *
 * @param {{
 *   enabled: boolean,
 *   onToggleEnabled: (enabled: boolean) => void,
 *   label: string,
 *   onChangeLabel: (label: string) => void
 * }} props
 */
export default function AlarmSettings({
  enabled,
  onToggleEnabled,
  label,
  onChangeLabel,
}) {
  return (
    <div className="space-y-6">
      {/* Alarm Enabled State Toggle */}
      <div className="p-4 rounded-2xl bg-slate-950/60 border border-slate-800 flex items-center justify-between gap-4">
        <div className="space-y-0.5">
          <label htmlFor="alarm-toggle-switch" className="text-sm font-semibold text-white cursor-pointer">
            Alarm Active
          </label>
          <p className="text-xs text-slate-400">
            {enabled
              ? 'Alarm will ring when scheduled (unsaved draft)'
              : 'Alarm will remain inactive upon creation'}
          </p>
        </div>

        <button
          id="alarm-toggle-switch"
          type="button"
          role="switch"
          aria-checked={enabled}
          onClick={() => onToggleEnabled(!enabled)}
          className={`relative inline-flex h-7 w-12 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-slate-900 ${
            enabled ? 'bg-indigo-600' : 'bg-slate-800'
          }`}
        >
          <span className="sr-only">Toggle alarm active state</span>
          <span
            aria-hidden="true"
            className={`pointer-events-none inline-block h-6 w-6 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out ${
              enabled ? 'translate-x-5' : 'translate-x-0'
            }`}
          />
        </button>
      </div>

      {/* Optional Alarm Label */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label htmlFor="alarm-label-input" className="text-sm font-semibold text-white">
            Alarm Label <span className="text-xs font-normal text-slate-400">(Optional)</span>
          </label>
          <span className="text-xs text-slate-500">{label.length}/40 characters</span>
        </div>

        <div className="relative">
          <input
            id="alarm-label-input"
            type="text"
            maxLength={40}
            value={label}
            onChange={(e) => onChangeLabel(e.target.value)}
            placeholder="e.g. Morning workout, Deep work focus"
            className="w-full px-4 py-2.5 rounded-xl bg-slate-950/70 border border-slate-800 text-sm text-white placeholder-slate-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-colors"
          />
          {label.length > 0 && (
            <button
              type="button"
              onClick={() => onChangeLabel('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-white p-1"
              aria-label="Clear alarm label"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
