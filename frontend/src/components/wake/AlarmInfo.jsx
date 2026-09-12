import React from 'react';
import { Link } from 'react-router-dom';

const CHALLENGE_ICONS = {
  dance: '🕺',
  math: '🧮',
  memory: '🧠',
  tongue_twister: '👅',
  pushups: '💪',
};

/**
 * AlarmInfo component
 * Displays read-only information about the triggered alarm and challenge,
 * or an honest fallback if no router state was passed.
 *
 * @param {{
 *   alarmDraft?: {
 *     time?: string,
 *     label?: string,
 *     challengeCategory?: string,
 *     challengeName?: string,
 *     selectedDays?: string[]
 *   } | null
 * }} props
 */
export default function AlarmInfo({ alarmDraft = null }) {
  if (!alarmDraft) {
    return (
      <div className="p-6 rounded-2xl bg-white border border-dashed border-slate-300 text-center space-y-3 shadow-xs">
        <div className="w-10 h-10 rounded-xl bg-amber-50 text-amber-600 border border-amber-200 flex items-center justify-center mx-auto">
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
          </svg>
        </div>
        <div className="space-y-1">
          <h3 className="text-sm font-semibold text-slate-900">No Active Session Data Received</h3>
          <p className="text-xs text-slate-600 max-w-md mx-auto">
            This screen was opened without draft alarm parameters from the creation flow.
            You can configure a new alarm or test the default demo challenge below.
          </p>
        </div>
        <div className="pt-2 flex flex-wrap justify-center gap-3">
          <Link
            to="/alarms"
            className="px-3.5 py-1.5 rounded-lg text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-700 shadow-xs transition-colors"
          >
            Create Alarm
          </Link>
          <Link
            to="/challenge"
            className="px-3.5 py-1.5 rounded-lg text-xs font-semibold text-slate-700 bg-white hover:bg-slate-50 transition-colors border border-slate-300 shadow-2xs"
          >
            Select Challenge
          </Link>
        </div>
      </div>
    );
  }

  const category = alarmDraft.challengeCategory || 'math';
  const icon = CHALLENGE_ICONS[category] || '⚡';
  const challengeTitle = alarmDraft.challengeName || category.toUpperCase();

  return (
    <div className="p-5 rounded-2xl bg-white border border-slate-200 shadow-xs">
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
        <div className="space-y-1">
          <span className="text-slate-500 block">Triggered Alarm</span>
          <span className="text-base font-bold text-slate-900 font-mono block">
            {alarmDraft.time || '07:00 AM'}
          </span>
        </div>

        <div className="space-y-1">
          <span className="text-slate-500 block">Alarm Label</span>
          <span className="text-sm font-medium text-slate-800 block truncate">
            {alarmDraft.label || 'Morning Wake Session'}
          </span>
        </div>

        <div className="space-y-1">
          <span className="text-slate-500 block">Challenge Required</span>
          <span className="text-sm font-bold text-indigo-700 flex items-center gap-1.5">
            <span role="img" aria-label={challengeTitle}>{icon}</span>
            <span>{challengeTitle}</span>
          </span>
        </div>
      </div>
    </div>
  );
}
