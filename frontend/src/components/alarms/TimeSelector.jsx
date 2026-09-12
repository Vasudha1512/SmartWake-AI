import React from 'react';

/**
 * TimeSelector component
 * Accessible HTML5 time input with large visual display and presets.
 *
 * @param {{
 *   time: string,
 *   onChange: (time: string) => void,
 *   error?: string | null
 * }} props
 */
export default function TimeSelector({ time, onChange, error }) {
  const formatDisplayTime = (timeStr) => {
    if (!timeStr) return { formatted: '--:--', period: '' };
    const [hoursStr, minutesStr] = timeStr.split(':');
    const hours = parseInt(hoursStr, 10);
    if (isNaN(hours)) return { formatted: timeStr, period: '' };
    const period = hours >= 12 ? 'PM' : 'AM';
    const displayHours = hours % 12 === 0 ? 12 : hours % 12;
    const formattedHours = displayHours < 10 ? `0${displayHours}` : `${displayHours}`;
    return {
      formatted: `${formattedHours}:${minutesStr || '00'}`,
      period,
    };
  };

  const { formatted, period } = formatDisplayTime(time);

  const presets = ['06:30', '07:00', '07:30', '08:00'];

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <label htmlFor="alarm-time-input" className="text-sm font-semibold text-white">
          Alarm Time <span className="text-rose-400">*</span>
        </label>
        <span className="text-xs text-slate-400">24-hour or 12-hour format</span>
      </div>

      {/* Visual Clock Display Card */}
      <div className="p-6 rounded-2xl bg-slate-950/70 border border-slate-800 text-center relative overflow-hidden group hover:border-slate-700 transition-colors">
        <div className="flex items-baseline justify-center gap-2">
          <span className="text-5xl sm:text-6xl font-extrabold tracking-tight text-white font-mono">
            {formatted}
          </span>
          <span className="text-xl sm:text-2xl font-bold text-indigo-400">
            {period}
          </span>
        </div>

        {/* Hidden/Native accessible time input overlay */}
        <div className="mt-4 flex justify-center">
          <input
            id="alarm-time-input"
            type="time"
            value={time}
            onChange={(e) => onChange(e.target.value)}
            className="px-4 py-2.5 rounded-xl bg-slate-900 border border-slate-700 text-white font-mono text-base focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-colors cursor-pointer"
            aria-describedby={error ? 'time-error-message' : undefined}
            aria-invalid={!!error}
            required
          />
        </div>

        {/* Quick Presets */}
        <div className="mt-4 pt-4 border-t border-slate-900 flex items-center justify-center gap-2 flex-wrap">
          <span className="text-xs text-slate-400 mr-1">Presets:</span>
          {presets.map((preset) => (
            <button
              key={preset}
              type="button"
              onClick={() => onChange(preset)}
              className={`px-2.5 py-1 rounded-lg text-xs font-mono font-medium transition-all ${
                time === preset
                  ? 'bg-indigo-600 text-white shadow-sm shadow-indigo-600/30'
                  : 'bg-slate-900 text-slate-400 hover:text-white hover:bg-slate-800 border border-slate-800'
              }`}
            >
              {preset}
            </button>
          ))}
        </div>
      </div>

      {error && (
        <p id="time-error-message" role="alert" className="text-xs font-medium text-rose-400 flex items-center gap-1.5">
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
