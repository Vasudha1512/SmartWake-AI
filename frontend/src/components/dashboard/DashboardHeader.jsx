import React from 'react';

export default function DashboardHeader() {
  const getGreeting = () => {
    const hour = new Date().getHours();
    if (hour < 12) return 'Good morning';
    if (hour < 17) return 'Good afternoon';
    return 'Good evening';
  };

  const todayFormatted = new Intl.DateTimeFormat('en-US', {
    weekday: 'long',
    month: 'short',
    day: 'numeric',
  }).format(new Date());

  return (
    <header className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-6 border-b border-slate-800/80">
      <div>
        <div className="flex items-center gap-2 mb-1 text-xs font-semibold uppercase tracking-wider text-indigo-400">
          <span className="w-2 h-2 rounded-full bg-indigo-500"></span>
          <span>{todayFormatted}</span>
        </div>
        <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-white">
          {getGreeting()}
        </h1>
        <p className="text-sm text-slate-400 mt-1">
          Monitor your cognitive alarms, wake schedules, and morning alertness metrics.
        </p>
      </div>

      <div className="flex items-center gap-3 self-start sm:self-auto">
        <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-xl text-xs font-medium bg-slate-900 border border-slate-800 text-slate-300 shadow-sm">
          <span className="w-2 h-2 rounded-full bg-emerald-400"></span>
          <span>Cognitive Engine Ready</span>
        </div>
      </div>
    </header>
  );
}
