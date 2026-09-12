import React from 'react';
import { Link } from 'react-router-dom';

/**
 * QuickActions component
 * Provides accessible shortcut cards navigating to primary SmartWake modules.
 */
export default function QuickActions() {
  const actions = [
    {
      id: 'create-alarm',
      title: 'Create Alarm',
      description: 'Set a new alarm with cognitive challenge domain and schedule preferences.',
      path: '/alarms',
      ctaText: 'Open Alarms',
      icon: (
        <svg className="w-5 h-5 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4v16m8-8H4" />
        </svg>
      ),
      accentColor: 'hover:border-indigo-300 hover:bg-indigo-50/40',
    },
    {
      id: 'wake-session',
      title: 'Wake Session',
      description: 'Access the active alarm wake screen, snooze control, and live challenge solver.',
      path: '/wake',
      ctaText: 'Launch Wake UI',
      icon: (
        <svg className="w-5 h-5 text-amber-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
      ),
      accentColor: 'hover:border-amber-300 hover:bg-amber-50/40',
    },
    {
      id: 'view-history',
      title: 'View History',
      description: 'Review historical wake session transcripts, challenge accuracy, and ML adaptation.',
      path: '/history',
      ctaText: 'Explore Logs',
      icon: (
        <svg className="w-5 h-5 text-purple-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
        </svg>
      ),
      accentColor: 'hover:border-purple-300 hover:bg-purple-50/40',
    },
  ];

  return (
    <section aria-labelledby="quick-actions-heading" className="space-y-4">
      <div className="flex items-center justify-between">
        <h2 id="quick-actions-heading" className="text-base font-semibold text-slate-900">
          Quick Actions
        </h2>
        <span className="text-xs text-slate-500">Navigation shortcuts</span>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
        {actions.map((action) => (
          <Link
            key={action.id}
            to={action.path}
            className={`group p-5 rounded-2xl bg-white border border-slate-200 transition-all duration-200 flex flex-col justify-between hover:scale-[1.01] hover:shadow-md ${action.accentColor}`}
          >
            <div className="space-y-3">
              <div className="w-10 h-10 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-center shadow-2xs">
                {action.icon}
              </div>
              <h3 className="text-sm font-semibold text-slate-900 group-hover:text-indigo-600 transition-colors">
                {action.title}
              </h3>
              <p className="text-xs text-slate-600 leading-relaxed">
                {action.description}
              </p>
            </div>

            <div className="pt-4 mt-2 border-t border-slate-200 flex items-center justify-between text-xs font-medium text-slate-700 group-hover:text-slate-900">
              <span>{action.ctaText}</span>
              <span className="transform group-hover:translate-x-1 transition-transform text-slate-400 group-hover:text-slate-700">&rarr;</span>
            </div>
          </Link>
        ))}
      </div>
    </section>
  );
}
