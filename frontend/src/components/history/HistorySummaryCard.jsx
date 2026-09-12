import React from 'react';

/**
 * HistorySummaryCard component
 * Displays a single key performance metric card for the History view.
 *
 * @param {{
 *   label: string,
 *   value: string | number,
 *   sublabel: string,
 *   icon: React.ReactNode
 * }} props
 */
export default function HistorySummaryCard({ label, value, sublabel, icon }) {
  return (
    <div className="p-5 rounded-2xl bg-white border border-slate-200 shadow-xs flex flex-col justify-between">
      <div className="flex items-center justify-between gap-2 mb-3">
        <span className="text-xs font-semibold text-slate-600">{label}</span>
        <div className="p-2 rounded-xl bg-slate-50 border border-slate-200 text-slate-600 shadow-2xs">
          {icon}
        </div>
      </div>

      <div className="space-y-1">
        <div className="text-2xl sm:text-3xl font-extrabold text-slate-900 tracking-tight font-mono">
          {value}
        </div>
        <p className="text-[11px] text-slate-500">
          {sublabel}
        </p>
      </div>
    </div>
  );
}
