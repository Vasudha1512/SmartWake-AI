import React, { useMemo } from 'react';

const DAYS = [
  { id: 'mon', label: 'Monday', short: 'Mon' },
  { id: 'tue', label: 'Tuesday', short: 'Tue' },
  { id: 'wed', label: 'Wednesday', short: 'Wed' },
  { id: 'thu', label: 'Thursday', short: 'Thu' },
  { id: 'fri', label: 'Friday', short: 'Fri' },
  { id: 'sat', label: 'Saturday', short: 'Sat' },
  { id: 'sun', label: 'Sunday', short: 'Sun' },
];

const WEEKDAY_IDS = ['mon', 'tue', 'wed', 'thu', 'fri'];
const WEEKEND_IDS = ['sat', 'sun'];
const ALL_DAY_IDS = ['mon', 'tue', 'wed', 'thu', 'fri', 'sat', 'sun'];

const SCHEDULE_MODES = [
  { id: 'once', label: 'Once', desc: 'One-time ring, no repeat' },
  { id: 'everyday', label: 'Every day', desc: 'All 7 days' },
  { id: 'weekdays', label: 'Weekdays', desc: 'Mon to Fri (Office)' },
  { id: 'weekends', label: 'Weekends', desc: 'Sat & Sun' },
  { id: 'custom', label: 'Custom', desc: 'Pick specific days' },
];

/**
 * RepeatDaySelector component
 *
 * Provides accessible preset schedules (Once, Every day, Weekdays, Weekends, Custom)
 * and individual day selection pills.
 *
 * @param {{
 *   selectedDays: string[],
 *   onChange: (days: string[]) => void,
 *   error?: string | null
 * }} props
 */
export default function RepeatDaySelector({ selectedDays = [], onChange, error }) {
  // Determine active schedule mode based on selectedDays array
  const activeMode = useMemo(() => {
    if (!selectedDays || selectedDays.length === 0) return 'once';
    if (selectedDays.length === 7) return 'everyday';
    if (selectedDays.length === 5 && WEEKDAY_IDS.every((d) => selectedDays.includes(d))) {
      return 'weekdays';
    }
    if (selectedDays.length === 2 && WEEKEND_IDS.every((d) => selectedDays.includes(d))) {
      return 'weekends';
    }
    return 'custom';
  }, [selectedDays]);

  const handleSelectMode = (modeId) => {
    switch (modeId) {
      case 'once':
        onChange([]);
        break;
      case 'everyday':
        onChange([...ALL_DAY_IDS]);
        break;
      case 'weekdays':
        onChange([...WEEKDAY_IDS]);
        break;
      case 'weekends':
        onChange([...WEEKEND_IDS]);
        break;
      case 'custom':
        // If currently once or all, keep or provide initial custom selection
        if (selectedDays.length === 0) {
          onChange(['mon', 'wed', 'fri']);
        }
        break;
      default:
        break;
    }
  };

  const toggleDay = (dayId) => {
    if (selectedDays.includes(dayId)) {
      onChange(selectedDays.filter((id) => id !== dayId));
    } else {
      onChange([...selectedDays, dayId]);
    }
  };

  const getScheduleSummary = () => {
    switch (activeMode) {
      case 'once':
        return 'One-time ring (no repeat on subsequent days)';
      case 'everyday':
        return 'Rings every day (Monday through Sunday)';
      case 'weekdays':
        return 'Rings Monday through Friday (Office / Work schedule)';
      case 'weekends':
        return 'Rings on Saturday and Sunday';
      case 'custom':
      default:
        return selectedDays.length > 0
          ? `Rings on: ${selectedDays.map((d) => DAYS.find((item) => item.id === d)?.short).join(', ')}`
          : 'No days selected (select at least one day or choose Once)';
    }
  };

  return (
    <fieldset className="space-y-4">
      <div className="flex items-center justify-between">
        <legend className="text-sm font-semibold text-slate-900">
          Repeat Schedule
        </legend>
        <span className="text-xs font-medium text-indigo-700 bg-indigo-50 px-2.5 py-0.5 rounded-full border border-indigo-200">
          {SCHEDULE_MODES.find((m) => m.id === activeMode)?.label || 'Custom'}
        </span>
      </div>

      {/* 1. Quick Schedule Mode Pills (Once / Every day / Weekdays / Weekends / Custom) */}
      <div
        role="radiogroup"
        aria-label="Preset schedule modes"
        className="grid grid-cols-2 sm:grid-cols-5 gap-2"
      >
        {SCHEDULE_MODES.map((mode) => {
          const isSelected = activeMode === mode.id;
          return (
            <button
              key={mode.id}
              type="button"
              role="radio"
              aria-checked={isSelected}
              onClick={() => handleSelectMode(mode.id)}
              className={`py-2 px-3 rounded-xl text-xs font-semibold transition-all cursor-pointer text-center select-none focus:outline-none focus:ring-2 focus:ring-indigo-500 ${
                isSelected
                  ? 'bg-indigo-600 text-white shadow-xs'
                  : 'bg-slate-50 text-slate-700 hover:text-slate-900 hover:bg-slate-100 border border-slate-200'
              }`}
            >
              {mode.label}
            </button>
          );
        })}
      </div>

      {/* 2. Individual Mon–Sun Day Pills */}
      <div className="space-y-2 pt-1">
        <div className="flex items-center justify-between">
          <span className="text-xs font-medium text-slate-600">
            {activeMode === 'custom' ? 'Custom Days (Click to toggle):' : 'Active Days in Schedule:'}
          </span>
          {activeMode === 'custom' && selectedDays.length > 0 && (
            <button
              type="button"
              onClick={() => onChange([])}
              className="text-[11px] text-slate-500 hover:text-rose-600 transition-colors cursor-pointer"
            >
              Clear
            </button>
          )}
        </div>

        <div className="grid grid-cols-7 gap-2">
          {DAYS.map((day) => {
            const isSelected = selectedDays.includes(day.id);
            return (
              <button
                key={day.id}
                type="button"
                onClick={() => toggleDay(day.id)}
                aria-pressed={isSelected}
                aria-label={day.label}
                className={`flex flex-col items-center justify-center py-2.5 px-1 rounded-xl text-xs font-semibold transition-all select-none focus:outline-none focus:ring-2 focus:ring-indigo-500 cursor-pointer ${
                  isSelected
                    ? 'bg-indigo-600 text-white border-2 border-indigo-500 shadow-xs'
                    : 'bg-white text-slate-700 border border-slate-200 hover:text-slate-900 hover:bg-slate-50'
                }`}
              >
                <span className="tracking-tight">{day.short}</span>
                <span className="mt-1">
                  {isSelected ? (
                    <svg className="w-3.5 h-3.5 text-indigo-100" fill="currentColor" viewBox="0 0 20 20">
                      <path
                        fillRule="evenodd"
                        d="M16.707 5.293a1 1 0 010 1.414l-8 8a1 1 0 01-1.414 0l-4-4a1 1 0 011.414-1.414L8 12.586l7.293-7.293a1 1 0 011.414 0z"
                        clipRule="evenodd"
                      />
                    </svg>
                  ) : (
                    <span className="w-1.5 h-1.5 rounded-full bg-slate-300 block"></span>
                  )}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* 3. Selected Schedule Summary Notice */}
      <div className="p-3 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-600 flex items-center gap-2">
        <svg className="w-4 h-4 text-indigo-600 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <circle cx="12" cy="12" r="10" strokeWidth="2"></circle>
          <path d="M12 6v6l4 2" strokeWidth="2" strokeLinecap="round"></path>
        </svg>
        <span>{getScheduleSummary()}</span>
      </div>

      {error && (
        <p role="alert" className="text-xs font-medium text-rose-600 flex items-center gap-1.5">
          <svg className="w-4 h-4 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="10" strokeWidth="2"></circle>
            <path d="M12 8v4m0 4h.01" strokeWidth="2" strokeLinecap="round"></path>
          </svg>
          {error}
        </p>
      )}
    </fieldset>
  );
}
