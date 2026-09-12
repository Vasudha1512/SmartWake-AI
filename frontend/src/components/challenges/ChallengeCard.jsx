import React from 'react';

/**
 * ChallengeCard component
 * Accessible card representing a selectable wake-up challenge category.
 *
 * @param {{
 *   challenge: {
 *     id: string,
 *     icon: string,
 *     name: string,
 *     description: string,
 *     requirement: string
 *   },
 *   isSelected: boolean,
 *   onSelect: () => void
 * }} props
 */
export default function ChallengeCard({ challenge, isSelected, onSelect }) {
  return (
    <div
      role="radio"
      aria-checked={isSelected}
      tabIndex={0}
      onClick={onSelect}
      onKeyDown={(e) => {
        if (e.key === ' ' || e.key === 'Enter') {
          e.preventDefault();
          onSelect();
        }
      }}
      className={`relative p-5 rounded-2xl border transition-all cursor-pointer select-none flex flex-col justify-between focus:outline-none focus:ring-2 focus:ring-indigo-500 ${
        isSelected
          ? 'bg-gradient-to-br from-indigo-950/60 to-slate-900 border-indigo-500 shadow-xl shadow-indigo-600/10 ring-2 ring-indigo-500/40'
          : 'bg-slate-900/60 border-slate-800 hover:border-slate-700 hover:bg-slate-850'
      }`}
    >
      <div>
        {/* Header: Emoji icon + Selection Indicator */}
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="w-12 h-12 rounded-xl bg-slate-950/80 border border-slate-800 flex items-center justify-center text-2xl shadow-inner">
            <span role="img" aria-label={challenge.name}>
              {challenge.icon}
            </span>
          </div>

          <div className="flex items-center gap-2">
            {isSelected ? (
              <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-indigo-500 text-white shadow-sm">
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                </svg>
                Selected
              </span>
            ) : (
              <span className="w-5 h-5 rounded-full border-2 border-slate-700 block transition-colors"></span>
            )}
          </div>
        </div>

        {/* Challenge Name & Description */}
        <div className="space-y-1.5">
          <h3 className="text-base font-bold text-white tracking-tight">
            {challenge.name}
          </h3>
          <p className="text-xs text-slate-300 leading-relaxed">
            {challenge.description}
          </p>
        </div>
      </div>

      {/* Verification Details */}
      <div className="mt-4 pt-3 border-t border-slate-800/80">
        <span className="text-[11px] text-slate-400 block">
          <strong className="text-slate-300 font-medium">To Dismiss:</strong> {challenge.requirement}
        </span>
      </div>
    </div>
  );
}
