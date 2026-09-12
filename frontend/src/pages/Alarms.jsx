import React from 'react';
import { Link } from 'react-router-dom';
import AlarmForm from '../components/alarms/AlarmForm';
import LiveClock from '../components/common/LiveClock';

/**
 * Alarms Page
 * SmartWake AI Alarm Creation experience.
 * Configures scheduled wake times, repeat days, and alarm settings
 * before proceeding to cognitive challenge selection.
 */
export default function Alarms() {
  return (
    <div className="space-y-8 max-w-2xl mx-auto">
      {/* 1. Page Header, Live Current Clock & Back Navigation */}
      <header className="space-y-4">
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

        <div className="border-b border-slate-200 pb-5 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900">
              Create Alarm
            </h1>
            <p className="text-sm text-slate-600 mt-1 leading-relaxed max-w-md">
              Configure your wake-up time and schedule. SmartWake AI requires solving an adaptive cognitive challenge to dismiss the alarm.
            </p>
          </div>

          <div className="self-start sm:self-auto shrink-0">
            <LiveClock />
          </div>
        </div>
      </header>

      {/* 2. Main Alarm Creation Form Container */}
      <main className="rounded-2xl bg-white border border-slate-200 p-6 sm:p-8 shadow-xs">
        <AlarmForm />
      </main>
    </div>
  );
}
