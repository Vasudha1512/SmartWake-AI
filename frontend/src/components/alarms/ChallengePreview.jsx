import React from 'react';

/**
 * ChallengePreview component
 * Informational preview explaining cognitive wake verification and hosting
 * the 'Continue to Challenge' step CTA.
 *
 * @param {{
 *   onContinue: () => void,
 *   isSubmitting?: boolean
 * }} props
 */
export default function ChallengePreview({ onContinue, isSubmitting = false }) {
  return (
    <div className="space-y-4 pt-4 border-t border-slate-800">
      <div className="p-5 rounded-2xl bg-gradient-to-br from-indigo-950/40 via-slate-900/60 to-slate-900/60 border border-indigo-900/30 space-y-3">
        <div className="flex items-center gap-2 text-indigo-400">
          <span className="p-1.5 rounded-lg bg-indigo-500/10 border border-indigo-500/20">
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9.663 17h4.673M12 3v1m6.364 1.636l-.707.707M21 12h-1M4 12H3m3.343-5.657l-.707-.707m2.828 9.9a5 5 0 117.072 0l-.548.547A3.374 3.374 0 0014 18.469V19a2 2 0 11-4 0v-.531c0-.895-.356-1.754-.988-2.386l-.548-.547z" />
            </svg>
          </span>
          <span className="text-xs font-bold uppercase tracking-wider">Next Step: Cognitive Challenge</span>
        </div>

        <div className="space-y-1">
          <h3 className="text-sm font-semibold text-white">
            Cognitive Wake Verification
          </h3>
          <p className="text-xs text-slate-400 leading-relaxed">
            SmartWake AI alarms cannot be dismissed with a single tap. You will choose your challenge
            domain (Math, Logic, Multi-domain) in the next step. Our ML pipeline personalizes challenge
            difficulty based on your sleep patterns.
          </p>
        </div>

        <div className="pt-2">
          <button
            type="button"
            onClick={onContinue}
            disabled={isSubmitting}
            className="w-full sm:w-auto inline-flex items-center justify-center px-6 py-3 rounded-xl text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-500 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-slate-900 shadow-lg shadow-indigo-600/30 transition-all disabled:opacity-50 disabled:cursor-not-allowed group"
          >
            <span>Continue to Challenge</span>
            <svg
              className="w-4 h-4 ml-2 transform group-hover:translate-x-1 transition-transform"
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M14 5l7 7m0 0l-7 7m7-7H3" />
            </svg>
          </button>
        </div>
      </div>
    </div>
  );
}
