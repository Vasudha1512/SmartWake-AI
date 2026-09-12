import React, { useState, useEffect } from 'react';

/**
 * LiveClock component
 * Displays the user's current local time and date in real time.
 * Cleans up timer on unmount and supports custom timezones.
 *
 * @param {{
 *   timezone?: string,
 *   showSeconds?: boolean,
 *   className?: string
 * }} props
 */
export default function LiveClock({ timezone, showSeconds = true, className = '' }) {
  const [timeState, setTimeState] = useState({
    timeStr: '',
    dateStr: '',
    isoStr: '',
  });

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      const tzOptions = timezone ? { timeZone: timezone } : {};

      try {
        const timeStr = now.toLocaleTimeString('en-US', {
          hour: '2-digit',
          minute: '2-digit',
          second: showSeconds ? '2-digit' : undefined,
          hour12: true,
          ...tzOptions,
        });

        const dateStr = now.toLocaleDateString('en-US', {
          weekday: 'long',
          day: 'numeric',
          month: 'long',
          ...tzOptions,
        });

        setTimeState({
          timeStr,
          dateStr,
          isoStr: now.toISOString(),
        });
      } catch (e) {
        // Fallback if timezone identifier is invalid
        setTimeState({
          timeStr: now.toLocaleTimeString(),
          dateStr: now.toLocaleDateString(),
          isoStr: now.toISOString(),
        });
      }
    };

    updateTime();
    const intervalId = setInterval(updateTime, 1000);

    return () => clearInterval(intervalId);
  }, [timezone, showSeconds]);

  if (!timeState.timeStr) {
    return null;
  }

  return (
    <div
      className={`inline-flex items-center gap-3 px-4 py-2.5 rounded-2xl bg-white border border-slate-200 shadow-xs ${className}`}
      aria-label="Current local time"
    >
      <div className="w-8 h-8 rounded-xl bg-indigo-50 border border-indigo-200 text-indigo-600 flex items-center justify-center shrink-0">
        <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24" aria-hidden="true">
          <circle cx="12" cy="12" r="10" strokeWidth="2"></circle>
          <path d="M12 6v6l4 2" strokeWidth="2" strokeLinecap="round"></path>
        </svg>
      </div>

      <div className="text-left">
        <div className="flex items-center gap-1.5">
          <span className="text-xs font-bold uppercase tracking-wider text-slate-500">
            Current Time
          </span>
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 animate-pulse" title="Clock active"></span>
        </div>
        <time dateTime={timeState.isoStr} className="flex flex-wrap items-baseline gap-2">
          <span className="text-base font-bold text-slate-900 font-mono tracking-tight">
            {timeState.timeStr}
          </span>
          <span className="text-xs text-slate-500 font-medium">
            &bull; {timeState.dateStr}
          </span>
        </time>
      </div>
    </div>
  );
}
