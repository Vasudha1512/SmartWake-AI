import React, { useState } from 'react';
import { useLocation, useNavigate, Link } from 'react-router-dom';
import WakeHeader from '../components/wake/WakeHeader';
import AlarmInfo from '../components/wake/AlarmInfo';
import WakeStatus from '../components/wake/WakeStatus';
import ChallengeRunner from '../components/wake/ChallengeRunner';

/**
 * Wake Page
 * SmartWake AI active wake-session experience.
 * Manages the alarm ringing state, challenge execution simulation, and cognitive completion.
 * Real backend verification and alarm dismissal connect in Phase 6.
 */
export default function Wake() {
  const location = useLocation();
  const navigate = useNavigate();

  const alarmDraft = location.state?.alarmDraft || null;
  const challengeCategory = alarmDraft?.challengeCategory || 'math';

  // Session state: 'ready' | 'in_progress' | 'completed' | 'failed'
  const [sessionStatus, setSessionStatus] = useState('ready');

  const handleStartChallenge = () => {
    setSessionStatus('in_progress');
  };

  const handleChallengeComplete = () => {
    setSessionStatus('completed');
  };

  const handleChallengeFail = () => {
    setSessionStatus('failed');
  };

  const handleRestart = () => {
    setSessionStatus('ready');
  };

  const handleBackToChallenge = () => {
    navigate('/challenge', { state: { alarmDraft } });
  };

  return (
    <div className="space-y-8 max-w-3xl mx-auto">
      {/* 1. Navigation Breadcrumb */}
      <nav aria-label="Breadcrumb" className="flex items-center justify-between">
        <button
          type="button"
          onClick={handleBackToChallenge}
          className="inline-flex items-center text-xs font-semibold text-indigo-400 hover:text-indigo-300 transition-colors cursor-pointer"
        >
          <svg className="w-3.5 h-3.5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 19l-7-7 7-7" />
          </svg>
          Back to Challenge Selection
        </button>

        <span className="text-xs text-slate-500 font-mono">
          Session ID: #DEMO-{challengeCategory.toUpperCase()}
        </span>
      </nav>

      {/* 2. Wake Session Header (Live Digital Clock & Urgent Heading) */}
      <WakeHeader />

      {/* 3. Alarm Information Summary */}
      <AlarmInfo alarmDraft={alarmDraft} />

      {/* 4. Session Status Lifecycle Bar */}
      <WakeStatus status={sessionStatus} />

      {/* 5. Main Interactive Session Viewport */}
      <main className="rounded-2xl bg-slate-900/70 border border-slate-800 p-6 sm:p-8 shadow-xl min-h-[360px] flex flex-col justify-center">
        {/* State A: Ready / Waiting */}
        {sessionStatus === 'ready' && (
          <div className="text-center space-y-6 py-6 max-w-md mx-auto">
            <div className="w-16 h-16 rounded-2xl bg-indigo-500/10 text-indigo-400 border border-indigo-500/20 flex items-center justify-center mx-auto text-2xl shadow-inner animate-pulse">
              ⚡
            </div>

            <div className="space-y-2">
              <h2 className="text-2xl font-extrabold text-white tracking-tight">
                Ready to Wake Up?
              </h2>
              <p className="text-xs text-slate-400 leading-relaxed">
                Your alarm is ringing. Tap below to launch your cognitive challenge and prove morning alertness.
              </p>
            </div>

            <div className="pt-2 space-y-3">
              <button
                type="button"
                onClick={handleStartChallenge}
                className="w-full py-4 rounded-xl text-base font-bold text-white bg-indigo-600 hover:bg-indigo-500 shadow-xl shadow-indigo-600/30 transition-all cursor-pointer focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-slate-900 group"
              >
                <span>Start Challenge</span>
                <svg
                  className="w-5 h-5 ml-2 inline-block transform group-hover:translate-x-1 transition-transform"
                  fill="none"
                  stroke="currentColor"
                  viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M14 5l7 7m0 0l-7 7m7-7H3" />
                </svg>
              </button>

              <p className="text-[11px] text-slate-500">
                Frontend demo simulation. Alarm ringing lifecycle connects in Phase 6.
              </p>
            </div>
          </div>
        )}

        {/* State B: Challenge In Progress */}
        {sessionStatus === 'in_progress' && (
          <div className="py-2">
            <ChallengeRunner
              challengeCategory={challengeCategory}
              onComplete={handleChallengeComplete}
              onFail={handleChallengeFail}
            />
          </div>
        )}

        {/* State C: Challenge Completed / Success */}
        {sessionStatus === 'completed' && (
          <div className="text-center space-y-6 py-6 max-w-md mx-auto">
            <div className="w-16 h-16 rounded-2xl bg-emerald-500/10 text-emerald-400 border border-emerald-500/20 flex items-center justify-center mx-auto text-3xl shadow-inner">
              <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" />
              </svg>
            </div>

            <div className="space-y-2">
              <h2 className="text-2xl font-extrabold text-white tracking-tight">
                Challenge Completed!
              </h2>
              <p className="text-sm text-slate-300">
                You proved morning alertness and successfully completed the verification challenge.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-slate-950/60 border border-slate-800 text-xs text-slate-400 space-y-1">
              <span className="font-semibold text-emerald-400 block">Alarm Silenced (Simulation)</span>
              <p>
                Real-time alarm audio shutdown, snooze lifecycle, and SQLite history logging will be connected during Phase 6 backend integration.
              </p>
            </div>

            <div className="pt-2 flex flex-col sm:flex-row items-center justify-center gap-3">
              <Link
                to="/dashboard"
                className="w-full sm:w-auto px-6 py-3 rounded-xl text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-500 shadow-md transition-colors"
              >
                Finish Wake Session
              </Link>
              <button
                type="button"
                onClick={handleRestart}
                className="w-full sm:w-auto px-5 py-3 rounded-xl text-sm font-semibold text-slate-300 bg-slate-800 hover:bg-slate-700 hover:text-white border border-slate-700 transition-colors cursor-pointer"
              >
                Restart Demo
              </button>
            </div>
          </div>
        )}

        {/* State D: Challenge Failed / Retry State */}
        {sessionStatus === 'failed' && (
          <div className="text-center space-y-6 py-6 max-w-md mx-auto">
            <div className="w-16 h-16 rounded-2xl bg-rose-500/10 text-rose-400 border border-rose-500/20 flex items-center justify-center mx-auto text-2xl shadow-inner">
              <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>

            <div className="space-y-2">
              <h2 className="text-xl font-bold text-white tracking-tight">
                Verification Incomplete
              </h2>
              <p className="text-xs text-slate-400">
                Don&apos;t worry &mdash; take a breath and try again to prove cognitive alertness and stop the alarm.
              </p>
            </div>

            <div className="pt-2">
              <button
                type="button"
                onClick={() => setSessionStatus('in_progress')}
                className="w-full py-3 rounded-xl text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-500 shadow-lg shadow-indigo-600/30 transition-all cursor-pointer"
              >
                Try Again
              </button>
            </div>
          </div>
        )}
      </main>
    </div>
  );
}
