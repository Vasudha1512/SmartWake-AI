import React, { useMemo, useState, useEffect } from 'react';

/**
 * Convert 24-hour HH:mm format to 12-hour components
 * @param {string} time24
 * @returns {{ hour: number, minute: string, period: 'AM' | 'PM' }}
 */
function from24Hour(time24) {
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
  const minute = String(m).padStart(2, '0');

  return { hour, minute, period };
}

/**
 * Convert 12-hour components to canonical 24-hour HH:mm string
 * @param {number} hour
 * @param {string|number} minute
 * @param {'AM' | 'PM'} period
 * @returns {string}
 */
function to24Hour(hour, minute, period) {
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
 * Calculates remaining duration from now until the alarm triggers next.
 * @param {string} time24
 * @returns {string}
 */
function calculateRingIn(time24) {
  if (!time24 || !time24.includes(':')) return '';

  const [hStr, mStr] = time24.split(':');
  const targetH = parseInt(hStr, 10);
  const targetM = parseInt(mStr, 10);
  if (isNaN(targetH) || isNaN(targetM)) return '';

  const now = new Date();
  const target = new Date();
  target.setHours(targetH, targetM, 0, 0);

  if (target.getTime() <= now.getTime()) {
    target.setDate(target.getDate() + 1);
  }

  const diffMs = target.getTime() - now.getTime();
  const totalMins = Math.round(diffMs / 60000);
  const hours = Math.floor(totalMins / 60);
  const mins = totalMins % 60;

  if (hours === 0 && mins === 0) {
    return 'Rings in less than a minute';
  }
  if (hours === 0) {
    return `Rings in ${mins} minute${mins === 1 ? '' : 's'}`;
  }
  if (mins === 0) {
    return `Rings in ${hours} hour${hours === 1 ? '' : 's'}`;
  }
  return `Rings in ${hours} hr ${mins} min`;
}

/**
 * 12-hour Phone-Alarm Style TimeSelector
 *
 * Provides a touch/mouse-friendly 12-hour interface with hours (1–12),
 * minutes (00–59), and distinct AM/PM buttons.
 *
 * Internally produces canonical 24-hour HH:mm string to preserve API and state compatibility.
 *
 * @param {{
 *   time: string,
 *   onChange: (canonicalTime24: string) => void,
 *   error?: string | null
 * }} props
 */
export default function TimeSelector({ time, onChange, error }) {
  const { hour, minute, period } = useMemo(() => from24Hour(time), [time]);

  // Live ring-in calculation ticker
  const [ringInText, setRingInText] = useState(() => calculateRingIn(time));

  useEffect(() => {
    setRingInText(calculateRingIn(time));
    const interval = setInterval(() => {
      setRingInText(calculateRingIn(time));
    }, 30000);
    return () => clearInterval(interval);
  }, [time]);

  const handleHourChange = (newHour) => {
    const h = parseInt(newHour, 10);
    if (!isNaN(h) && h >= 1 && h <= 12) {
      onChange(to24Hour(h, minute, period));
    }
  };

  const handleMinuteChange = (newMinute) => {
    const m = parseInt(newMinute, 10);
    if (!isNaN(m) && m >= 0 && m <= 59) {
      onChange(to24Hour(hour, m, period));
    }
  };

  const handlePeriodChange = (newPeriod) => {
    if (newPeriod !== period) {
      onChange(to24Hour(hour, minute, newPeriod));
    }
  };

  const adjustHour = (delta) => {
    let next = hour + delta;
    if (next > 12) next = 1;
    if (next < 1) next = 12;
    handleHourChange(next);
  };

  const adjustMinute = (delta) => {
    let m = parseInt(minute, 10) + delta;
    if (m >= 60) m = 0;
    if (m < 0) m = 55;
    handleMinuteChange(m);
  };

  const presets12h = [
    { label: '06:30 AM', time24: '06:30' },
    { label: '07:00 AM', time24: '07:00' },
    { label: '07:30 AM', time24: '07:30' },
    { label: '08:00 AM', time24: '08:00' },
    { label: '10:00 PM', time24: '22:00' },
  ];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <label className="text-sm font-semibold text-slate-900">
          Alarm Time <span className="text-rose-500">*</span>
        </label>
        <span className="text-xs text-slate-500">12-Hour Phone Style</span>
      </div>

      {/* Main 12-Hour Interactive Clock Card */}
      <div className="p-6 rounded-2xl bg-slate-50 border border-slate-200 text-center relative overflow-hidden group hover:border-slate-300 transition-colors space-y-5 shadow-xs">
        {/* Time Stepper / Display Area */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-4 sm:gap-6">
          {/* Digits Block */}
          <div className="flex items-center justify-center gap-2">
            {/* Hour Selector */}
            <div className="flex flex-col items-center space-y-1">
              <button
                type="button"
                onClick={() => adjustHour(1)}
                aria-label="Increment hour"
                className="w-10 h-7 rounded-lg bg-white hover:bg-slate-100 text-slate-600 border border-slate-200 flex items-center justify-center text-xs font-bold transition-colors cursor-pointer shadow-2xs"
              >
                ▲
              </button>
              <select
                aria-label="Select hour (1 to 12)"
                value={hour}
                onChange={(e) => handleHourChange(e.target.value)}
                className="w-20 h-16 sm:w-24 sm:h-20 text-center font-mono text-4xl sm:text-5xl font-extrabold text-slate-900 bg-white border border-slate-300 rounded-2xl shadow-xs focus:outline-none focus:ring-2 focus:ring-indigo-500 cursor-pointer appearance-none px-2"
              >
                {Array.from({ length: 12 }, (_, i) => i + 1).map((h) => (
                  <option key={h} value={h}>
                    {String(h).padStart(2, '0')}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => adjustHour(-1)}
                aria-label="Decrement hour"
                className="w-10 h-7 rounded-lg bg-white hover:bg-slate-100 text-slate-600 border border-slate-200 flex items-center justify-center text-xs font-bold transition-colors cursor-pointer shadow-2xs"
              >
                ▼
              </button>
              <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
                Hour
              </span>
            </div>

            {/* Colon Separator */}
            <span className="text-4xl sm:text-5xl font-extrabold text-slate-400 font-mono pb-6">
              :
            </span>

            {/* Minute Selector */}
            <div className="flex flex-col items-center space-y-1">
              <button
                type="button"
                onClick={() => adjustMinute(5)}
                aria-label="Increment minutes by 5"
                className="w-10 h-7 rounded-lg bg-white hover:bg-slate-100 text-slate-600 border border-slate-200 flex items-center justify-center text-xs font-bold transition-colors cursor-pointer shadow-2xs"
              >
                ▲
              </button>
              <select
                aria-label="Select minutes (00 to 59)"
                value={minute}
                onChange={(e) => handleMinuteChange(e.target.value)}
                className="w-20 h-16 sm:w-24 sm:h-20 text-center font-mono text-4xl sm:text-5xl font-extrabold text-slate-900 bg-white border border-slate-300 rounded-2xl shadow-xs focus:outline-none focus:ring-2 focus:ring-indigo-500 cursor-pointer appearance-none px-2"
              >
                {Array.from({ length: 60 }, (_, i) => String(i).padStart(2, '0')).map((m) => (
                  <option key={m} value={m}>
                    {m}
                  </option>
                ))}
              </select>
              <button
                type="button"
                onClick={() => adjustMinute(-5)}
                aria-label="Decrement minutes by 5"
                className="w-10 h-7 rounded-lg bg-white hover:bg-slate-100 text-slate-600 border border-slate-200 flex items-center justify-center text-xs font-bold transition-colors cursor-pointer shadow-2xs"
              >
                ▼
              </button>
              <span className="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">
                Minute
              </span>
            </div>
          </div>

          {/* AM / PM Segmented Control */}
          <div
            role="radiogroup"
            aria-label="Select AM or PM"
            className="flex sm:flex-col gap-2 p-1.5 rounded-2xl bg-white border border-slate-200 shadow-2xs"
          >
            <button
              type="button"
              role="radio"
              aria-checked={period === 'AM'}
              onClick={() => handlePeriodChange('AM')}
              className={`px-5 py-3 sm:py-3.5 rounded-xl text-base font-extrabold tracking-wider transition-all cursor-pointer select-none focus:outline-none focus:ring-2 focus:ring-indigo-500 ${
                period === 'AM'
                  ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/20'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
              }`}
            >
              AM
            </button>
            <button
              type="button"
              role="radio"
              aria-checked={period === 'PM'}
              onClick={() => handlePeriodChange('PM')}
              className={`px-5 py-3 sm:py-3.5 rounded-xl text-base font-extrabold tracking-wider transition-all cursor-pointer select-none focus:outline-none focus:ring-2 focus:ring-indigo-500 ${
                period === 'PM'
                  ? 'bg-indigo-600 text-white shadow-md shadow-indigo-600/20'
                  : 'text-slate-600 hover:text-slate-900 hover:bg-slate-100'
              }`}
            >
              PM
            </button>
          </div>
        </div>

        {/* Small Phone-Alarm Feature: "Rings in X hours Y minutes" */}
        {ringInText && (
          <div className="inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
            <svg className="w-3.5 h-3.5 text-indigo-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="10" strokeWidth="2"></circle>
              <path d="M12 6v6l4 2" strokeWidth="2" strokeLinecap="round"></path>
            </svg>
            <span>{ringInText}</span>
          </div>
        )}

        {/* Quick Presets */}
        <div className="pt-4 border-t border-slate-200 flex items-center justify-center gap-2 flex-wrap">
          <span className="text-xs text-slate-500 mr-1">Quick Presets:</span>
          {presets12h.map((preset) => {
            const isSelected = time === preset.time24;
            return (
              <button
                key={preset.label}
                type="button"
                onClick={() => onChange(preset.time24)}
                className={`px-3 py-1 rounded-lg text-xs font-mono font-medium transition-all cursor-pointer ${
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
