import React, { useState } from 'react';
import { useLocation, useNavigate, Link } from 'react-router-dom';
import AlarmSummary from '../components/challenges/AlarmSummary';
import ChallengeGrid, { CHALLENGES } from '../components/challenges/ChallengeGrid';

/**
 * Challenge Page
 * SmartWake AI Challenge Selection experience.
 * Allows the user to select the cognitive or physical challenge required to dismiss the alarm.
 * ML adapts difficulty and parameters later; the user has full authority over the challenge domain.
 */
export default function Challenge() {
  const location = useLocation();
  const navigate = useNavigate();

  const alarmDraft = location.state?.alarmDraft || null;
  const [selectedChallengeId, setSelectedChallengeId] = useState(null);

  const challengeList = CHALLENGES || ChallengeGrid?.CHALLENGES || [];
  const selectedChallenge = challengeList.find((c) => c.id === selectedChallengeId);

  const handleContinue = () => {
    if (!selectedChallengeId) return;

    const completeDraft = {
      ...alarmDraft,
      challengeCategory: selectedChallengeId,
      challengeName: selectedChallenge?.name,
    };

    // Navigate to next stage (Wake Screen)
    navigate('/wake', { state: { alarmDraft: completeDraft } });
  };

  return (
    <div className="space-y-8 max-w-4xl mx-auto">
      {/* 1. Header & Back Navigation */}
      <header className="space-y-3">
        <nav aria-label="Breadcrumb">
          <Link
            to="/alarms"
            className="inline-flex items-center text-xs font-semibold text-indigo-600 hover:text-indigo-700 transition-colors"
          >
            <svg className="w-3.5 h-3.5 mr-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 19l-7-7 7-7" />
            </svg>
            Back to Alarm
          </Link>
        </nav>

        <div className="border-b border-slate-200 pb-4 flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
          <div>
            <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900">
              Choose Wake-up Challenge
            </h1>
            <p className="text-sm text-slate-600 mt-1">
              Select the challenge category required to dismiss your alarm.
            </p>
          </div>

          <span className="text-xs px-3 py-1 rounded-full bg-slate-100 border border-slate-200 text-slate-600 font-medium self-start sm:self-auto">
            Step 2 of 2
          </span>
        </div>
      </header>

      {/* 2. Read-only Alarm Summary */}
      <AlarmSummary alarmDraft={alarmDraft} />

      {/* 3. Challenge Category Selection */}
      <section aria-labelledby="challenge-section-heading" className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
          <div>
            <h2 id="challenge-section-heading" className="text-base font-semibold text-slate-900">
              Challenge Categories
            </h2>
            <p className="text-xs text-slate-600">
              Select one category. SmartWake AI will dynamically calibrate challenge parameters to your wake profile.
            </p>
          </div>

          {selectedChallenge ? (
            <span className="text-xs font-semibold text-indigo-700 bg-indigo-50 px-3 py-1 rounded-full border border-indigo-200 self-start sm:self-auto">
              Selected: {selectedChallenge.name}
            </span>
          ) : (
            <span className="text-xs font-medium text-amber-800 bg-amber-50 px-3 py-1 rounded-full border border-amber-200 self-start sm:self-auto">
              Selection Required
            </span>
          )}
        </div>

        <ChallengeGrid
          selectedId={selectedChallengeId}
          onSelect={setSelectedChallengeId}
        />
      </section>

      {/* 4. Product Rule / ML Architecture Explainer */}
      <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 flex items-start gap-3 text-xs text-slate-600">
        <span className="p-1 rounded-md bg-indigo-100 text-indigo-700 shrink-0 mt-0.5">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
          </svg>
        </span>
        <div className="space-y-1">
          <span className="font-semibold text-slate-900 block">User Choice &amp; ML Personalization</span>
          <p className="leading-relaxed">
            You maintain full control over which challenge category activates. During active alarms, our
            ML engine personalizes the difficulty level (e.g. math complexity, sequence length, movement reps)
            based on your historical alertness logs.
          </p>
        </div>
      </div>

      {/* 5. Action Buttons */}
      <div className="pt-2 border-t border-slate-200 flex flex-col-reverse sm:flex-row items-center justify-between gap-4">
        <Link
          to="/alarms"
          className="w-full sm:w-auto inline-flex items-center justify-center px-5 py-2.5 rounded-xl text-sm font-semibold text-slate-700 hover:text-slate-900 hover:bg-slate-100 border border-slate-300 bg-white shadow-2xs transition-colors"
        >
          &larr; Back to Alarm
        </Link>

        <button
          type="button"
          onClick={handleContinue}
          disabled={!selectedChallengeId}
          className={`w-full sm:w-auto inline-flex items-center justify-center px-8 py-3 rounded-xl text-sm font-semibold transition-all shadow-md ${
            selectedChallengeId
              ? 'bg-indigo-600 hover:bg-indigo-700 text-white shadow-indigo-600/20 cursor-pointer focus:outline-none focus:ring-2 focus:ring-indigo-500'
              : 'bg-slate-200 text-slate-400 cursor-not-allowed border border-slate-300'
          }`}
        >
          <span>Continue</span>
          <svg className="w-4 h-4 ml-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M14 5l7 7m0 0l-7 7m7-7H3" />
          </svg>
        </button>
      </div>
    </div>
  );
}
