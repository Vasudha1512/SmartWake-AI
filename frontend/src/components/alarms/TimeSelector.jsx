import React, { useState, useEffect, useMemo, useCallback } from 'react';
import { calculateNextOccurrence, formatRingInDuration } from '../../utils/alarmScheduler';

/**
 * Convert 24-hour HH:mm format to 12-hour components
 * @param {string} time24
 * @returns {{ hour: number, minute: string, period: 'AM' | 'PM' }}
 */
export function from24Hour(time24) {
  if (!time24 || typeof time24 !== 'string' || !time24.includes(':')) {
    return { hour: 7, minute: '00', period: 'AM' };
  }
  const [hStr, mStr] = time24.split(':');
  const h24 = parseInt(hStr, 10);
  const m = parseInt(mStr, 10);

  if (isNaN(h24) || isNaN(m)) {
    return { hour: 7, minute: '00', period: 'AM' };
  }

  const period = h24 >= 12 ? 'PM' : 'AM';
  const hour = h24 % 12 === 0 ? 12 : h24 % 12;
  const minute = String(Math.max(0, Math.min(59, m))).padStart(2, '0');

  return { hour, minute, period };
}

/**
 * Convert 12-hour components to canonical 24-hour HH:mm string
 * @param {number} hour
 * @param {string|number} minute
 * @param {'AM' | 'PM'} period
 * @returns {string}
 */
export function to24Hour(hour, minute, period) {
  const h12 = parseInt(hour, 10) || 12;
  const m = parseInt(minute, 10) || 0;

  let h24 = h12;
  if (period === 'AM') {
    h24 = h12 === 12 ? 0 : h12;
  } else {
    h24 = h12 === 12 ? 12 : h12 + 12;
  }

  return `${String(h24).padStart(2, '0')}:${String(m).padStart(2, '0')}`;
}

/**
 * Format canonical 24-hour HH:mm string to human-readable 12-hour label
 * @param {string} time24
 * @returns {string}
 */
export function formatDisplayTime(time24) {
  const { hour, minute, period } = from24Hour(time24);
  const formattedHour = String(hour).padStart(2, '0');
  return `${formattedHour}:${minute} ${period}`;
}

/**
 * Compact TimeSelector with native time input and separate native AM/PM <select>
 *
 * Visual Structure:
 * Alarm Time
 * [ 08:30 ] [ PM ]
 * 08:30 PM
 * Rings in ...
 *
 * - Native time-entry control for typing/selecting hour and minute
 * - Separate compact native AM/PM <select> (only 2 options: AM, PM)
 * - 12-hour visible user-facing format
 * - Canonical 24-hour HH:mm format preserved for scheduler and AlarmForm
 *
 * @param {{
 *   time: string,
 *   onChange: (canonicalTime24: string) => void,
 *   error?: string | null,
 *   selectedDays?: string[],
 *   timezone?: string
 * }} props
 */
export default function TimeSelector({
  time,
  onChange,
  error,
  selectedDays = [],
  timezone,
}) {
  const { hour, minute, period } = useMemo(() => from24Hour(time), [time]);

  // Formatted 12-hour time string for the native time input (e.g. "08:30")
  const time12 = `${String(hour).padStart(2, '0')}:${minute}`;

  // Compute live ring-in duration using canonical alarmScheduler logic
  const getRingInDuration = useCallback(() => {
    if (!time || !time.includes(':')) return '';
    const tz = timezone || (typeof Intl !== 'undefined' ? Intl.DateTimeFormat().resolvedOptions().timeZone : 'UTC');
    const nextMs = calculateNextOccurrence(
      {
        time,
        selectedDays,
        timezone: tz,
      },
      Date.now()
    );
    return formatRingInDuration(nextMs, Date.now());
  }, [time, selectedDays, timezone]);

  const [ringInText, setRingInText] = useState(getRingInDuration);

  useEffect(() => {
    setRingInText(getRingInDuration());
    const interval = setInterval(() => {
      setRingInText(getRingInDuration());
    }, 30000);
    return () => clearInterval(interval);
  }, [getRingInDuration]);

  // Handle typing or selecting in native hour:minute control
  const handleTimeChange = (e) => {
    const val = e.target.value;
    if (!val || !val.includes(':')) return;

    const [hStr, mStr] = val.split(':');
    const h = parseInt(hStr, 10);
    const m = parseInt(mStr, 10);
    if (isNaN(h) || isNaN(m)) return;

    let newPeriod = period;
    let h12 = h;

    // Handle 24-hour input values gracefully
    if (h > 12) {
      newPeriod = 'PM';
      h12 = h - 12;
    } else if (h === 0) {
      newPeriod = 'AM';
      h12 = 12;
    }

    onChange(to24Hour(h12, m, newPeriod));
  };

  // Handle AM / PM change in native select
  const handlePeriodChange = (newPeriod) => {
    if (newPeriod !== period) {
      onChange(to24Hour(hour, minute, newPeriod));
    }
  };

  const presets12h = [
    { label: '06:30 AM', time24: '06:30' },
    { label: '07:00 AM', time24: '07:00' },
    { label: '07:30 AM', time24: '07:30' },
    { label: '08:00 AM', time24: '08:00' },
    { label: '10:00 PM', time24: '22:00' },
  ];

  return (
    <div className="space-y-3">
      <div className="flex items-center justify-between">
        <label htmlFor="alarm-time-input" className="text-sm font-semibold text-slate-900">
          Alarm Time <span className="text-rose-500">*</span>
        </label>
        <span className="text-xs text-slate-500">12-Hour Format</span>
      </div>

      {/* Main Time Entry Card */}
      <div className="p-4 sm:p-5 rounded-2xl bg-slate-50 border border-slate-200 text-center relative overflow-hidden group hover:border-slate-300 transition-colors space-y-3 shadow-xs">
        {/* Desired Visual Structure: [ 08:30 ] [ PM ] */}
        <div className="flex items-center justify-center gap-2 sm:gap-3">
          {/* Native Time Entry Control for Typing/Selecting Hour and Minute */}
          <input
            id="alarm-time-input"
            type="time"
            step="60"
            value={time12}
            onChange={handleTimeChange}
            aria-label="Alarm time hour and minute"
            className="h-[50px] w-40 sm:w-44 px-3 text-xl sm:text-2xl font-mono font-bold text-center text-slate-900 bg-white border border-slate-300 rounded-xl shadow-xs focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 cursor-pointer [&::-webkit-datetime-edit-ampm-field]:hidden"
          />

          {/* Separate Compact Native AM/PM <select> Control */}
          <select
            id="alarm-period-select"
            aria-label="Select AM or PM"
            value={period}
            onChange={(e) => handlePeriodChange(e.target.value)}
            className="h-[50px] w-20 sm:w-24 px-2 sm:px-3 text-lg sm:text-xl font-mono font-bold text-center text-slate-900 bg-white border border-slate-300 rounded-xl shadow-xs focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 cursor-pointer"
          >
            <option value="AM">AM</option>
            <option value="PM">PM</option>
          </select>
        </div>

        {/* 12-Hour Confirmation Display: 08:30 PM */}
        <div className="pt-1">
          <span className="text-sm sm:text-base font-mono font-bold text-slate-800 tracking-wide">
            {formatDisplayTime(time)}
          </span>
        </div>

        {/* Rings in ... */}
        {ringInText && (
          <div>
            <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
              <svg className="w-3.5 h-3.5 text-indigo-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <circle cx="12" cy="12" r="10" strokeWidth="2"></circle>
                <path d="M12 6v6l4 2" strokeWidth="2" strokeLinecap="round"></path>
              </svg>
              <span>{ringInText}</span>
            </div>
          </div>
        )}

        {/* Quick Presets */}
        <div className="pt-2.5 border-t border-slate-200 flex items-center justify-center gap-2 flex-wrap">
          <span className="text-xs text-slate-500 mr-1">Quick Presets:</span>
          {presets12h.map((preset) => {
            const isSelected = time === preset.time24;
            return (
              <button
                key={preset.label}
                type="button"
                onClick={() => onChange(preset.time24)}
                className={`px-2.5 py-1 rounded-lg text-xs font-mono font-medium transition-all cursor-pointer focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-1 ${
                  isSelected
                    ? 'bg-indigo-600 text-white shadow-xs'
                    : 'bg-white text-slate-700 hover:text-slate-900 hover:bg-slate-100 border border-slate-300 shadow-2xs'
                }`}
              >
                {preset.label}
              </button>
            );
          })}
        </div>
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
    </div>
  );
}
