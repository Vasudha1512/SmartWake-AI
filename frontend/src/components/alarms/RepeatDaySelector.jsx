import React from 'react';

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

/**
 * RepeatDaySelector component
 * Multi-select day picker with quick shortcuts (Every day, Weekdays, Weekends).
 *
 * @param {{
 *   selectedDays: string[],
 *   onChange: (days: string[]) => void,
 *   error?: string | null
 * }} props
 */
export default function RepeatDaySelector({ selectedDays = [], onChange, error }) {
  const toggleDay = (dayId) => {
    if (selectedDays.includes(dayId)) {
      onChange(selectedDays.filter((id) => id !== dayId));
    } else {
      onChange([...selectedDays, dayId]);
    }
  };

  const isAllSelected = ALL_DAY_IDS.every((id) => selectedDays.includes(id));
  const isWeekdaysSelected =
    WEEKDAY_IDS.every((id) => selectedDays.includes(id)) &&
    !WEEKEND_IDS.some((id) => selectedDays.includes(id));
  const isWeekendSelected =
    WEEKEND_IDS.every((id) => selectedDays.includes(id)) &&
    !WEEKDAY_IDS.some((id) => selectedDays.includes(id));

  const selectEveryDay = () => {
    if (isAllSelected) {
      onChange([]);
    } else {
      onChange([...ALL_DAY_IDS]);
    }
  };

  const selectWeekdays = () => {
    onChange([...WEEKDAY_IDS]);
  };

  const selectWeekends = () => {
    onChange([...WEEKEND_IDS]);
  };

  const clearSelection = () => {
    onChange([]);
  };

  return (
    <fieldset className="space-y-4">
      <div className="flex items-center justify-between">
        <legend className="text-sm font-semibold text-slate-900">
          Repeat Schedule
        </legend>
        <span className="text-xs text-slate-500">
          {selectedDays.length === 0
            ? 'One-time alarm (No repeat)'
            : isAllSelected
            ? 'Every day'
            : `${selectedDays.length} day${selectedDays.length > 1 ? 's' : ''} selected`}
        </span>
      </div>

      {/* Day Pills Container */}
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
              className={`flex flex-col items-center justify-center py-3 px-1 rounded-xl text-xs font-semibold transition-all select-none focus:outline-none focus:ring-2 focus:ring-indigo-500 ${
                isSelected
                  ? 'bg-indigo-600 text-white border-2 border-indigo-500 shadow-xs'
                  : 'bg-slate-50 text-slate-700 border border-slate-200 hover:text-slate-900 hover:bg-slate-100'
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

      {/* Quick Selection Shortcuts */}
      <div className="flex flex-wrap items-center gap-2 pt-1">
        <button
          type="button"
          onClick={selectEveryDay}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            isAllSelected
              ? 'bg-indigo-50 text-indigo-700 border border-indigo-200 font-semibold'
              : 'bg-white text-slate-700 hover:text-slate-900 hover:bg-slate-100 border border-slate-300 shadow-2xs'
          }`}
        >
          {isAllSelected ? 'Deselect All' : 'Every day'}
        </button>

        <button
          type="button"
          onClick={selectWeekdays}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            isWeekdaysSelected
              ? 'bg-indigo-50 text-indigo-700 border border-indigo-200 font-semibold'
              : 'bg-white text-slate-700 hover:text-slate-900 hover:bg-slate-100 border border-slate-300 shadow-2xs'
          }`}
        >
          Weekdays
        </button>

        <button
          type="button"
          onClick={selectWeekends}
          className={`px-3 py-1.5 rounded-lg text-xs font-medium transition-colors ${
            isWeekendSelected
              ? 'bg-indigo-50 text-indigo-700 border border-indigo-200 font-semibold'
              : 'bg-white text-slate-700 hover:text-slate-900 hover:bg-slate-100 border border-slate-300 shadow-2xs'
          }`}
        >
          Weekends
        </button>

        {selectedDays.length > 0 && (
          <button
            type="button"
            onClick={clearSelection}
            className="px-3 py-1.5 rounded-lg text-xs font-medium text-slate-500 hover:text-rose-600 transition-colors ml-auto"
          >
            Clear
          </button>
        )}
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
