import React from 'react';

const DURATION_OPTIONS = [
  { minutes: 5, label: '5 min', desc: 'Short rest' },
  { minutes: 10, label: '10 min', desc: 'Standard snooze' },
  { minutes: 15, label: '15 min', desc: 'Extended rest' },
];

/**
 * SnoozeDurationSelector component
 * Allows the user to select exactly 5, 10, or 15 minutes of snooze duration.
 *
 * @param {{
 *   selectedDuration: number,
 *   onSelectDuration: (duration: number) => void,
 *   onConfirm: (duration: number) => void,
 *   onCancel: () => void
 * }} props
 */
export default function SnoozeDurationSelector({
  selectedDuration = 5,
  onSelectDuration,
  onConfirm,
  onCancel,
}) {
  return (
    <div
      role="region"
      aria-label="Snooze duration selection"
      className="p-6 sm:p-7 rounded-2xl bg-white border border-slate-200 shadow-lg max-w-md mx-auto space-y-5 text-left animate-fadeIn"
    >
      <div className="flex items-center justify-between pb-3 border-b border-slate-200">
        <div className="flex items-center gap-2.5">
          <div className="w-9 h-9 rounded-xl bg-purple-50 text-purple-600 border border-purple-200 flex items-center justify-center text-lg">
            💤
          </div>
          <div>
            <h3 className="text-base font-bold text-slate-900 tracking-tight">
              Snooze Alarm
            </h3>
            <p className="text-xs text-slate-500">
              Select snooze duration:
            </p>
          </div>
        </div>

        <button
          type="button"
          onClick={onCancel}
          aria-label="Cancel snooze"
          className="text-slate-400 hover:text-slate-700 p-1.5 rounded-lg hover:bg-slate-100 transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-slate-400"
        >
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
          </svg>
        </button>
      </div>

      {/* Duration Options */}
      <div className="space-y-2">
        <span className="text-xs font-semibold text-slate-700 block">
          Choose duration:
        </span>
        <div className="grid grid-cols-3 gap-2.5" role="radiogroup" aria-label="Snooze duration options">
          {DURATION_OPTIONS.map((opt) => {
            const isSelected = selectedDuration === opt.minutes;
            return (
              <button
                key={opt.minutes}
                type="button"
                role="radio"
                aria-checked={isSelected}
                onClick={() => onSelectDuration(opt.minutes)}
                className={`py-3.5 px-3 rounded-xl border text-center transition-all cursor-pointer flex flex-col items-center justify-center gap-1 focus:outline-none focus:ring-2 focus:ring-purple-500 min-h-[64px] ${
                  isSelected
                    ? 'bg-purple-50 border-purple-500 text-purple-950 shadow-xs ring-1 ring-purple-400'
                    : 'bg-slate-50 border-slate-200 text-slate-700 hover:bg-slate-100 hover:border-slate-300'
                }`}
              >
                <span className="text-sm font-bold tracking-tight">
                  {opt.label}
                </span>
                <span className={`text-[10px] ${isSelected ? 'text-purple-700 font-medium' : 'text-slate-500'}`}>
                  {opt.desc}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Selected duration summary */}
      <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-700 flex items-center justify-between">
        <span className="text-slate-500">Selected Snooze:</span>
        <span className="font-semibold text-purple-700 flex items-center gap-1.5">
          <span className="w-2 h-2 rounded-full bg-purple-500 animate-pulse"></span>
          {selectedDuration} minutes
        </span>
      </div>

      <p className="text-[11px] text-slate-500 leading-relaxed">
        The wake session remains active. Your challenge will return when the snooze countdown expires.
      </p>

      {/* Action Buttons */}
      <div className="flex flex-col sm:flex-row items-center gap-3 pt-1">
        <button
          type="button"
          onClick={() => onConfirm(selectedDuration)}
          className="w-full sm:flex-1 py-3 px-4 rounded-xl text-sm font-semibold text-white bg-purple-600 hover:bg-purple-700 shadow-md shadow-purple-600/20 transition-all cursor-pointer focus:outline-none focus:ring-2 focus:ring-purple-500 focus:ring-offset-2 focus:ring-offset-white text-center"
        >
          Confirm Snooze
        </button>

        <button
          type="button"
          onClick={onCancel}
          className="w-full sm:w-auto py-3 px-5 rounded-xl text-sm font-medium text-slate-700 bg-white hover:bg-slate-50 hover:text-slate-900 border border-slate-300 transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-slate-400 text-center shadow-2xs"
        >
          Cancel
        </button>
      </div>
    </div>
  );
}
