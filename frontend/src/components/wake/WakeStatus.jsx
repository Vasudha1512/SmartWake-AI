import React from 'react';

/**
 * WakeStatus component
 * Visual session state badge and lifecycle indicator.
 *
 * @param {{
 *   status: 'ready' | 'in_progress' | 'completed' | 'failed' | 'no_session'
 * }} props
 */
export default function WakeStatus({ status }) {
  const statusConfig = {
    ready: {
      label: 'Alarm Ringing &bull; Waiting to Start',
      bgColor: 'bg-amber-950/60',
      textColor: 'text-amber-400',
      borderColor: 'border-amber-800/60',
      dotColor: 'bg-amber-400',
    },
    in_progress: {
      label: 'Challenge In Progress &bull; Verification Active',
      bgColor: 'bg-indigo-950/60',
      textColor: 'text-indigo-400',
      borderColor: 'border-indigo-800/60',
      dotColor: 'bg-indigo-400 animate-pulse',
    },
    completed: {
      label: 'Challenge Completed &bull; Alertness Verified',
      bgColor: 'bg-emerald-950/60',
      textColor: 'text-emerald-400',
      borderColor: 'border-emerald-800/60',
      dotColor: 'bg-emerald-400',
    },
    failed: {
      label: 'Verification Incomplete &bull; Retry Needed',
      bgColor: 'bg-rose-950/60',
      textColor: 'text-rose-400',
      borderColor: 'border-rose-800/60',
      dotColor: 'bg-rose-400',
    },
    no_session: {
      label: 'Standby &bull; No Active Wake Session',
      bgColor: 'bg-slate-900',
      textColor: 'text-slate-400',
      borderColor: 'border-slate-800',
      dotColor: 'bg-slate-500',
    },
  };

  const current = statusConfig[status] || statusConfig.ready;

  return (
    <div className="flex items-center justify-between pb-2 border-b border-slate-800/60">
      <span className="text-xs font-semibold uppercase tracking-wider text-slate-400">
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
