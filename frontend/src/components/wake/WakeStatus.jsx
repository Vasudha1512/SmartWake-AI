import React from 'react';

/**
 * WakeStatus component
 * Visual session state badge and lifecycle indicator.
 *
 * @param {{
 *   status: 'ready' | 'snoozed' | 'in_progress' | 'completed' | 'failed' | 'no_session'
 * }} props
 */
export default function WakeStatus({ status }) {
  const statusConfig = {
    ready: {
      label: 'Alarm Ringing &bull; Waiting to Start',
      bgColor: 'bg-amber-50',
      textColor: 'text-amber-800',
      borderColor: 'border-amber-200',
      dotColor: 'bg-amber-500',
    },
    snoozed: {
      label: 'Alarm Snoozed &bull; Countdown Active',
      bgColor: 'bg-purple-50',
      textColor: 'text-purple-800',
      borderColor: 'border-purple-200',
      dotColor: 'bg-purple-500 animate-pulse',
    },
    in_progress: {
      label: 'Challenge In Progress &bull; Verification Active',
      bgColor: 'bg-indigo-50',
      textColor: 'text-indigo-800',
      borderColor: 'border-indigo-200',
      dotColor: 'bg-indigo-500 animate-pulse',
    },
    completed: {
      label: 'Challenge Completed &bull; Alertness Verified',
      bgColor: 'bg-emerald-50',
      textColor: 'text-emerald-800',
      borderColor: 'border-emerald-200',
      dotColor: 'bg-emerald-500',
    },
    failed: {
      label: 'Verification Incomplete &bull; Retry Needed',
      bgColor: 'bg-rose-50',
      textColor: 'text-rose-800',
      borderColor: 'border-rose-200',
      dotColor: 'bg-rose-500',
    },
    no_session: {
      label: 'Standby &bull; No Active Wake Session',
      bgColor: 'bg-slate-100',
      textColor: 'text-slate-700',
      borderColor: 'border-slate-200',
      dotColor: 'bg-slate-400',
    },
  };

  const current = statusConfig[status] || statusConfig.ready;

  return (
    <div className="flex items-center justify-between pb-2 border-b border-slate-200">
      <span className="text-xs font-semibold uppercase tracking-wider text-slate-500">
        Session Status
      </span>

      <span
        className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold border ${current.bgColor} ${current.textColor} ${current.borderColor}`}
      >
        <span className={`w-2 h-2 rounded-full ${current.dotColor}`}></span>
        <span dangerouslySetInnerHTML={{ __html: current.label }} />
      </span>
    </div>
  );
}
