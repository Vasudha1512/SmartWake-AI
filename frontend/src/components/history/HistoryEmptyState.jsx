import React from 'react';
import { Link } from 'react-router-dom';

/**
 * HistoryEmptyState component
 * Displayed when no history records exist.
 * Provides guidance and a primary call-to-action to create an alarm.
 */
export default function HistoryEmptyState() {
  return (
    <div
      role="region"
      aria-label="Empty history state"
      className="p-8 sm:p-12 rounded-2xl bg-white border border-dashed border-slate-300 text-center space-y-4 shadow-xs"
    >
      <div className="w-12 h-12 rounded-2xl bg-indigo-50 text-indigo-600 border border-indigo-200 flex items-center justify-center mx-auto shadow-2xs">
        <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <circle cx="12" cy="13" r="8" strokeWidth="2"></circle>
          <path d="M12 9v4l2 2" strokeWidth="2" strokeLinecap="round"></path>
          <path d="M5 3 2 6" strokeWidth="2" strokeLinecap="round"></path>
          <path d="m22 6-3-3" strokeWidth="2" strokeLinecap="round"></path>
        </svg>
      </div>

      <div className="space-y-1 max-w-md mx-auto">
        <h3 className="text-lg font-bold text-slate-900 tracking-tight">
          No wake-up history yet.
        </h3>
        <p className="text-sm text-slate-600 leading-relaxed">
          Your wake session results, cognitive challenge accuracy, and snooze statistics will appear here once your scheduled alarms trigger and verify morning alertness.
        </p>
      </div>

      <div className="pt-2">
        <Link
          to="/alarms"
          className="inline-flex items-center justify-center px-5 py-2.5 rounded-xl text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 shadow-md shadow-indigo-600/20 transition-all focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-white"
        >
          <svg className="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" />
          </svg>
          Set an Alarm
        </Link>
      </div>
    </div>
  );
}
