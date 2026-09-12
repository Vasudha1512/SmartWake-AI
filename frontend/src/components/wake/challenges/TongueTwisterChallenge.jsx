import React from 'react';

/**
 * TongueTwisterChallenge component
 * Frontend demo interface for verbal articulation / speech verification.
 *
 * @param {{
 *   onComplete: () => void
 * }} props
 */
export default function TongueTwisterChallenge({ onComplete }) {
  const demoTwister = 'She sells seashells by the seashore, and the shells she sells are seashells for sure.';

  return (
    <div className="space-y-6 text-center max-w-md mx-auto">
      {/* Instructions */}
      <div className="space-y-1">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
          <span>👅 Tongue Twister Verbal Challenge</span>
        </div>
        <h3 className="text-xl font-bold text-slate-900 tracking-tight">
          Recite the Phrase Clearly
        </h3>
        <p className="text-xs text-slate-600">
          Speak the phonetic tongue twister aloud to activate vocal motor control and dismiss the alarm.
        </p>
      </div>

      {/* Phrase Card */}
      <div className="p-6 rounded-2xl bg-slate-50 border border-slate-200 shadow-xs space-y-3">
        <span className="text-[11px] font-mono uppercase tracking-wider text-slate-500 block">
          Demo Tongue Twister
        </span>
        <blockquote className="text-base sm:text-lg font-medium text-slate-900 italic leading-relaxed">
          &ldquo;{demoTwister}&rdquo;
        </blockquote>
      </div>

      {/* Microphone / Speech Recognition Placeholder */}
      <div className="p-5 rounded-2xl bg-slate-50 border-2 border-dashed border-slate-300 space-y-3">
        <div className="w-12 h-12 rounded-full bg-white border border-slate-200 flex items-center justify-center text-xl mx-auto text-rose-600 shadow-2xs">
          <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
          </svg>
        </div>

        <div className="space-y-1">
          <p className="text-xs font-semibold text-slate-800">
            Microphone / Speech Recognition Feed
          </p>
          <p className="text-[11px] text-slate-500 max-w-xs mx-auto">
            Live speech recognition and acoustic confidence scoring will be connected in Phase 6 backend integration.
          </p>
        </div>

        <span className="inline-block text-[10px] font-mono text-rose-800 px-2 py-0.5 rounded bg-rose-100 border border-rose-200">
          SPEECH SIMULATION
        </span>
      </div>

      {/* Demo Action Button */}
      <div className="pt-2">
        <button
          type="button"
          onClick={onComplete}
          className="w-full py-3 rounded-xl text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 shadow-md shadow-indigo-600/20 transition-all cursor-pointer focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          <span>Complete Demo Challenge</span>
          <svg className="w-4 h-4 ml-2 inline-block" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M5 13l4 4L19 7" />
          </svg>
        </button>
      </div>
    </div>
  );
}
