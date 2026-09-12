import React, { useState, useEffect, useRef } from 'react';
import { useLocation, useNavigate, Link } from 'react-router-dom';
import { useAlarm } from '../context/AlarmContext';
import WakeHeader from '../components/wake/WakeHeader';
import AlarmInfo from '../components/wake/AlarmInfo';
import WakeStatus from '../components/wake/WakeStatus';
import ChallengeRunner from '../components/wake/ChallengeRunner';
import SnoozeControl from '../components/wake/SnoozeControl';
import SnoozeDurationSelector from '../components/wake/SnoozeDurationSelector';
import SnoozeStatus from '../components/wake/SnoozeStatus';

/**
 * Wake Page
 * SmartWake AI active wake-session experience.
 * Manages the alarm ringing state, cognitive challenge execution, and local snooze lifecycle simulation.
 * Real backend verification, SnoozeEvent creation, and alarm dismissal connect in Phase 6.
 */
export default function Wake() {
  const location = useLocation();
  const navigate = useNavigate();
  const {
    alarm: activeAlarm,
    stopSound,
    isSoundPlaying,
    dismissAlarm,
  } = useAlarm();

  // Use route draft if available, or fall back to global active alarm
  const alarmDraft = location.state?.alarmDraft || (activeAlarm?.status !== 'idle' ? activeAlarm : null);
  const challengeCategory = alarmDraft?.challengeCategory || 'math';
  const isAlarmRinging = activeAlarm?.status === 'ringing';

  // Session state: 'ready' | 'in_progress' | 'completed' | 'failed'
  const [sessionStatus, setSessionStatus] = useState('ready');

  // Local Snooze state
  const [snoozeCount, setSnoozeCount] = useState(0);
  const [snoozeDuration, setSnoozeDuration] = useState(null);
  const [snoozeStatus, setSnoozeStatus] = useState('idle'); // 'idle' | 'selecting' | 'snoozed' | 'finished'
  const [selectedDuration, setSelectedDuration] = useState(5);
  const [snoozeRemainingSeconds, setSnoozeRemainingSeconds] = useState(0);

  // Target deadline timestamp ref for drift-free countdown
  const snoozeEndsAtRef = useRef(null);

  // Deadline/timestamp-based countdown effect
  useEffect(() => {
    if (snoozeStatus !== 'snoozed') {
      return;
    }

    const updateCountdown = () => {
      if (!snoozeEndsAtRef.current) {
        return;
      }

      const remainingMs = snoozeEndsAtRef.current - Date.now();
      const remainingSeconds = Math.max(0, Math.ceil(remainingMs / 1000));

      setSnoozeRemainingSeconds(remainingSeconds);

      if (remainingMs <= 0) {
        snoozeEndsAtRef.current = null;
        setSnoozeRemainingSeconds(0);
        setSnoozeStatus('finished');
      }
    };

    // Calculate immediately on mount/entering snoozed state
    updateCountdown();

    // Refresh display every second
    const intervalId = setInterval(updateCountdown, 1000);

    return () => {
      clearInterval(intervalId);
    };
  }, [snoozeStatus]);

  const handleStartChallenge = () => {
    setSessionStatus('in_progress');
  };

  const handleChallengeComplete = () => {
    // Stop active alarm sound and advance repeating alarm or disarm one-time alarm
    stopSound();
    dismissAlarm();
    setSessionStatus('completed');
  };

  const handleChallengeFail = () => {
    setSessionStatus('failed');
  };

  const handleRestart = () => {
    stopSound();
    setSessionStatus('ready');
    setSnoozeStatus('idle');
    setSnoozeCount(0);
    setSnoozeDuration(null);
    setSnoozeRemainingSeconds(0);
    setSelectedDuration(5);
    snoozeEndsAtRef.current = null;
  };

  const handleBackToChallenge = () => {
    navigate('/challenge', { state: { alarmDraft } });
  };

  // Snooze Flow Handlers
  const handleOpenSnoozeSelector = () => {
    setSnoozeStatus('selecting');
  };

  const handleCancelSnooze = () => {
    // Cancel: close selector, do not increment count, do not start countdown
    setSnoozeStatus(snoozeCount > 0 ? 'finished' : 'idle');
  };

  const handleConfirmSnooze = (duration) => {
    // 0. Stop alarm audio on snooze
    stopSound();

    // 1. Validate duration is exactly one of: 5, 10, 15
    const validDuration = [5, 10, 15].includes(duration) ? duration : 5;

    // 2. Increment snoozeCount by exactly 1
    setSnoozeCount((prev) => prev + 1);

    // 3. Save latest snoozeDuration
    setSnoozeDuration(validDuration);
    setSelectedDuration(validDuration);

    // 4. Calculate target deadline timestamp
    const endsAt = Date.now() + validDuration * 60 * 1000;
    snoozeEndsAtRef.current = endsAt;

    // 5. Initialize remaining seconds
    setSnoozeRemainingSeconds(validDuration * 60);

    // 6. Set status to "snoozed"
    setSnoozeStatus('snoozed');
  };

  const handleFastForwardDemo = () => {
    snoozeEndsAtRef.current = null;
    setSnoozeRemainingSeconds(0);
    setSnoozeStatus('finished');
  };

  return (
    <div className="space-y-8 max-w-3xl mx-auto">
      {/* 1. Navigation Breadcrumb */}
      <nav aria-label="Breadcrumb" className="flex items-center justify-between">
        <button
          type="button"
          onClick={handleBackToChallenge}
          className="inline-flex items-center text-xs font-semibold text-indigo-600 hover:text-indigo-700 transition-colors cursor-pointer"
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

      {/* 4. Active Alarm Ringing Alert & Audio Control */}
      {isAlarmRinging && (
        <div className="p-4 sm:p-5 rounded-2xl bg-amber-50 border-2 border-amber-300 shadow-xs space-y-3 animate-fade-in">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div className="flex items-start gap-3">
              <span className="relative flex h-3 w-3 mt-1 shrink-0">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-3 w-3 bg-rose-600"></span>
              </span>
              <div className="space-y-1">
                <div className="flex items-center gap-2 flex-wrap">
                  <span className="px-2.5 py-0.5 rounded-full text-xs font-bold uppercase tracking-wider bg-rose-100 text-rose-700 border border-rose-200">
                    Alarm Ringing
                  </span>
                  <span className="text-sm font-bold text-slate-900">
                    {activeAlarm?.label || alarmDraft?.label || 'Scheduled Alarm'} ({activeAlarm?.time || alarmDraft?.time || '07:00'})
                  </span>
                </div>
                <p className="text-xs text-slate-600">
                  Audio alarm tone is active. You must complete your cognitive challenge below to verify alertness and finish this wake session.
                </p>
              </div>
            </div>

            <div className="shrink-0 flex items-center gap-2">
              {isSoundPlaying ? (
                <button
                  type="button"
                  onClick={stopSound}
                  className="w-full sm:w-auto inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold text-slate-900 bg-white hover:bg-slate-100 border border-slate-300 shadow-xs transition-colors cursor-pointer"
                >
                  <svg className="w-4 h-4 text-rose-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2" />
                  </svg>
                  Stop Alarm Sound
                </button>
              ) : (
                <span className="inline-flex items-center gap-1.5 px-3 py-2 rounded-xl text-xs font-semibold text-slate-600 bg-white border border-slate-200 shadow-2xs">
                  <svg className="w-3.5 h-3.5 text-slate-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5.586 15H4a1 1 0 01-1-1v-4a1 1 0 011-1h1.586l4.707-4.707C10.923 3.663 12 4.109 12 5v14c0 .891-1.077 1.337-1.707.707L5.586 15z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2" />
                  </svg>
                  Sound Silenced
                </span>
              )}
            </div>
          </div>

          <div className="text-[11px] text-amber-800 bg-amber-100/70 px-3 py-2 rounded-xl border border-amber-200/80 font-medium">
            Stopping the alarm audio does not bypass wake verification. The cognitive challenge is still active and required.
          </div>
        </div>
      )}

      {/* 5. Session Status Lifecycle Bar */}
      <WakeStatus status={snoozeStatus === 'snoozed' ? 'snoozed' : sessionStatus} />


      {/* 5. Main Interactive Session Viewport */}
      <main className="rounded-2xl bg-white border border-slate-200 p-6 sm:p-8 shadow-xs min-h-[360px] flex flex-col justify-center">
        {/* Sub-State: Snooze Duration Selection */}
        {snoozeStatus === 'selecting' && (
          <SnoozeDurationSelector
            selectedDuration={selectedDuration}
            onSelectDuration={setSelectedDuration}
            onConfirm={handleConfirmSnooze}
            onCancel={handleCancelSnooze}
          />
        )}

        {/* Sub-State: Actively Snoozed (Countdown Active) */}
        {snoozeStatus === 'snoozed' && (
          <SnoozeStatus
            mode="active_card"
            snoozeCount={snoozeCount}
            snoozeDuration={snoozeDuration}
            snoozeStatus={snoozeStatus}
            remainingSeconds={snoozeRemainingSeconds}
            onFastForwardDemo={handleFastForwardDemo}
          />
        )}

        {/* State A: Ready / Waiting (when not selecting and not snoozed) */}
        {sessionStatus === 'ready' && snoozeStatus !== 'selecting' && snoozeStatus !== 'snoozed' && (
          <div className="text-center space-y-6 py-6 max-w-md mx-auto">
            {/* Snooze finished alert banner */}
            {snoozeStatus === 'finished' && (
              <SnoozeStatus
                mode="banner"
                snoozeCount={snoozeCount}
                snoozeDuration={snoozeDuration}
                snoozeStatus={snoozeStatus}
              />
            )}

            <div className="w-16 h-16 rounded-2xl bg-indigo-50 text-indigo-600 border border-indigo-200 flex items-center justify-center mx-auto text-2xl shadow-xs animate-pulse">
              ⚡
            </div>

            <div className="space-y-2">
              <h2 className="text-2xl font-extrabold text-slate-900 tracking-tight">
                {snoozeStatus === 'finished' ? 'Alarm Resumed!' : 'Ready to Wake Up?'}
              </h2>
              <p className="text-xs text-slate-600 leading-relaxed">
                {snoozeStatus === 'finished'
                  ? 'Your snooze period has ended. Tap below to launch your cognitive challenge and prove morning alertness.'
                  : 'Your alarm is ringing. Tap below to launch your cognitive challenge and prove morning alertness.'}
              </p>
            </div>

            <div className="pt-2 space-y-3">
              {/* Primary action */}
              <button
                type="button"
                onClick={handleStartChallenge}
                className="w-full py-4 rounded-xl text-base font-bold text-white bg-indigo-600 hover:bg-indigo-700 shadow-md shadow-indigo-600/20 transition-all cursor-pointer focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-white group"
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

              {/* Secondary action: Snooze */}
              <div className="flex items-center justify-center pt-1">
                <SnoozeControl onOpenSelector={handleOpenSnoozeSelector} />
              </div>

              {/* Session Snooze Count summary */}
              <div className="pt-1 flex items-center justify-center">
                <SnoozeStatus
                  mode="badge"
                  snoozeCount={snoozeCount}
                  snoozeDuration={snoozeDuration}
                />
              </div>

              <p className="text-[11px] text-slate-500">
                Frontend demo simulation. Alarm ringing lifecycle connects in Phase 6.
              </p>
            </div>
          </div>
        )}

        {/* State B: Challenge In Progress */}
        {sessionStatus === 'in_progress' && (
          <div className="py-2 space-y-4">
            {/* Session snooze status indicator during challenge */}
            <div className="flex items-center justify-between px-4 py-2 rounded-xl bg-slate-50 border border-slate-200 text-xs">
              <span className="text-slate-600 font-medium">Session Context:</span>
              <SnoozeStatus
                mode="badge"
                snoozeCount={snoozeCount}
                snoozeDuration={snoozeDuration}
              />
            </div>

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
            <div className="w-16 h-16 rounded-2xl bg-emerald-50 text-emerald-600 border border-emerald-200 flex items-center justify-center mx-auto text-3xl shadow-xs">
              <svg className="w-8 h-8" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" />
              </svg>
            </div>

            <div className="space-y-2">
              <h2 className="text-2xl font-extrabold text-slate-900 tracking-tight">
                Challenge Completed!
              </h2>
              <p className="text-sm text-slate-600">
                You proved morning alertness and successfully completed the verification challenge.
              </p>
            </div>

            {/* Session Snooze Summary */}
            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-700 space-y-2 text-left">
              <div className="flex items-center justify-between pb-2 border-b border-slate-200">
                <span className="text-slate-700 font-semibold">Session Summary</span>
                <span className="text-[11px] text-amber-800 bg-amber-50 px-2 py-0.5 rounded border border-amber-200 font-mono font-medium">Frontend Demo</span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-600">Snoozes this session:</span>
                <span className="font-semibold text-slate-900">
                  {snoozeCount === 0
                    ? '0 (No snoozes used)'
                    : `${snoozeCount} time${snoozeCount > 1 ? 's' : ''}${snoozeDuration ? ` (latest: ${snoozeDuration}m)` : ''}`}
                </span>
              </div>
              <div className="flex items-center justify-between">
                <span className="text-slate-600">Challenge result:</span>
                <span className="font-semibold text-emerald-700">Verified Alert</span>
              </div>
              <p className="text-[11px] text-slate-500 pt-1 border-t border-slate-200">
                Snooze history and session completion will be persisted to SQLite via FastAPI in Phase 6.
              </p>
            </div>

            <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 text-xs text-slate-600 space-y-1">
              <span className="font-semibold text-emerald-700 block">Alarm Silenced (Simulation)</span>
              <p>
                Real-time alarm audio shutdown, snooze lifecycle, and SQLite history logging will be connected during Phase 6 backend integration.
              </p>
            </div>

            <div className="pt-2 flex flex-col sm:flex-row items-center justify-center gap-3">
              <Link
                to="/dashboard"
                className="w-full sm:w-auto px-6 py-3 rounded-xl text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 shadow-xs transition-colors text-center"
              >
                Finish Wake Session
              </Link>
              <button
                type="button"
                onClick={handleRestart}
                className="w-full sm:w-auto px-5 py-3 rounded-xl text-sm font-semibold text-slate-700 bg-white hover:bg-slate-50 hover:text-slate-900 border border-slate-300 transition-colors cursor-pointer text-center shadow-2xs"
              >
                Restart Demo
              </button>
            </div>
          </div>
        )}

        {/* State D: Challenge Failed / Retry State */}
        {sessionStatus === 'failed' && (
          <div className="text-center space-y-6 py-6 max-w-md mx-auto">
            <div className="w-16 h-16 rounded-2xl bg-rose-50 text-rose-600 border border-rose-200 flex items-center justify-center mx-auto text-2xl shadow-xs">
              <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </div>

            <div className="space-y-2">
              <h2 className="text-xl font-bold text-slate-900 tracking-tight">
                Verification Incomplete
              </h2>
              <p className="text-xs text-slate-600">
                Don&apos;t worry &mdash; take a breath and try again to prove cognitive alertness and stop the alarm.
              </p>
            </div>

            <div className="pt-2">
              <button
                type="button"
                onClick={() => setSessionStatus('in_progress')}
                className="w-full py-3 rounded-xl text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 shadow-xs transition-all cursor-pointer"
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
