import React from 'react';
import { Link } from 'react-router-dom';
import AlarmForm from '../components/alarms/AlarmForm';

/**
 * Alarms Page
 * SmartWake AI Alarm Creation experience.
 * Configures scheduled wake times, repeat days, and alarm settings
 * before proceeding to cognitive challenge selection.
 */
export default function Alarms() {
  return (
    <div className="space-y-8 max-w-2xl mx-auto">
      {/* 1. Page Header & Back Navigation */}
      <header className="space-y-3">
        <nav aria-label="Breadcrumb">
          <Link
            to="/dashboard"
            className="inline-flex items-center text-xs font-semibold text-indigo-400 hover:text-indigo-300 transition-colors"
          >
            <svg className="w-3.5 h-3.5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 19l-7-7 7-7" />
            </svg>
            Back to Dashboard
          </Link>
        </nav>

        <div className="border-b border-slate-800/80 pb-4">
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-white">
            Create Alarm
          </h1>
          <p className="text-sm text-slate-400 mt-1 leading-relaxed">
            Configure your wake-up time and schedule. Unlike traditional alarms, SmartWake AI requires
            solving an adaptive cognitive challenge before ringing can be stopped.
          </p>
        </div>
      </header>

      {/* 2. Main Alarm Creation Form Container */}
      <main className="rounded-2xl bg-slate-900/60 border border-slate-800 p-6 sm:p-8 shadow-xl">
        <AlarmForm />
      </main>
    </div>
  );
}
