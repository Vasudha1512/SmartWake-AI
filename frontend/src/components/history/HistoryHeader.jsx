import React from 'react';
import { Link } from 'react-router-dom';

/**
 * HistoryHeader component
 * Displays page title, description, dashboard breadcrumb, and demo context badge.
 */
export default function HistoryHeader() {
  return (
    <header className="space-y-4 pb-6 border-b border-slate-200">
      <nav aria-label="Breadcrumb">
        <Link
          to="/dashboard"
          className="inline-flex items-center text-xs font-semibold text-indigo-600 hover:text-indigo-700 transition-colors"
        >
          <svg className="w-3.5 h-3.5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 19l-7-7 7-7" />
          </svg>
          Back to Dashboard
        </Link>
      </nav>

      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900">
            Wake History
          </h1>
          <p className="text-sm text-slate-600 mt-1 max-w-2xl">
            Review previous wake-up sessions, cognitive challenge results, and snooze patterns.
          </p>
        </div>

        <div className="self-start sm:self-auto">
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-medium bg-indigo-50 text-indigo-700 border border-indigo-200">
            <span className="w-1.5 h-1.5 rounded-full bg-indigo-500"></span>
            Demo Data &bull; Backend Connects in Phase 6
          </span>
        </div>
      </div>
    </header>
  );
}
