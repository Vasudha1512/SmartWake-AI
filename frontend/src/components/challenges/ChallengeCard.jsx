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
          ? 'bg-indigo-50/60 border-indigo-500 shadow-md ring-2 ring-indigo-500/20'
          : 'bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50/80 shadow-xs'
      }`}
    >
      <div>
        {/* Header: Emoji icon + Selection Indicator */}
        <div className="flex items-start justify-between gap-3 mb-3">
          <div className="w-12 h-12 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-center text-2xl shadow-2xs">
            <span role="img" aria-label={challenge.name}>
              {challenge.icon}
            </span>
          </div>

          <div className="flex items-center gap-2">
            {isSelected ? (
              <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-indigo-600 text-white shadow-xs">
                <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                </svg>
                Selected
              </span>
            ) : (
              <span className="w-5 h-5 rounded-full border-2 border-slate-300 block transition-colors"></span>
            )}
          </div>
        </div>

        {/* Challenge Name & Description */}
        <div className="space-y-1.5">
          <h3 className="text-base font-bold text-slate-900 tracking-tight">
            {challenge.name}
          </h3>
          <p className="text-xs text-slate-600 leading-relaxed">
            {challenge.description}
          </p>
        </div>
      </div>

      {/* Verification Details */}
      <div className="mt-4 pt-3 border-t border-slate-200">
        <span className="text-[11px] text-slate-500 block">
          <strong className="text-slate-700 font-medium">To Dismiss:</strong> {challenge.requirement}
        </span>
      </div>
    </div>
  );
}
