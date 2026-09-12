import React, { useState, useEffect } from 'react';

/**
 * WakeHeader component
 * Displays prominent live wake-up clock, branding context, and urgency indicator.
 */
export default function WakeHeader() {
  const [currentTime, setCurrentTime] = useState('');

  useEffect(() => {
    const updateTime = () => {
      const now = new Date();
      setCurrentTime(
        now.toLocaleTimeString('en-US', {
          hour: '2-digit',
          minute: '2-digit',
          second: '2-digit',
          hour12: true,
        })
      );
    };

    updateTime();
    const timer = setInterval(updateTime, 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <header className="text-center space-y-3 pb-6 border-b border-slate-200">
      <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
        <span className="w-2 h-2 rounded-full bg-amber-500 animate-ping"></span>
        <span>Alarm Triggered &bull; Wake Session Active</span>
      </div>

      <div className="space-y-1">
        <h1 className="text-3xl sm:text-5xl font-extrabold tracking-tight text-slate-900">
          Wake Up!
        </h1>
        <p className="text-sm text-slate-600 max-w-md mx-auto">
          Complete your selected challenge to dismiss the alarm and verify cognitive alertness.
        </p>
      </div>

      {/* Live Digital Clock Display */}
      <div className="pt-2">
        <div className="inline-block px-6 py-2.5 rounded-2xl bg-white border border-slate-200 shadow-xs">
          <span className="text-3xl sm:text-4xl font-mono font-bold tracking-wider text-slate-900">
            {currentTime || '--:--:-- --'}
          </span>
        </div>
      </div>
    </header>
  );
}
