import React, { useState } from 'react';

/**
 * MathChallenge component
 * Deterministic frontend demo interface for arithmetic cognitive verification.
 *
 * @param {{
 *   onComplete: () => void,
 *   onFail?: () => void
 * }} props
 */
export default function MathChallenge({ onComplete, onFail }) {
  const [answer, setAnswer] = useState('');
  const [error, setError] = useState(null);
  const [attempts, setAttempts] = useState(0);

  // Deterministic demo problem (34 + 29 = 63)
  const problem = {
    num1: 34,
    num2: 29,
    operator: '+',
    solution: 63,
  };

  const handleSubmit = (e) => {
    e.preventDefault();

    const parsed = parseInt(answer.trim(), 10);
    if (isNaN(parsed)) {
      setError('Please enter a numerical answer.');
      return;
    }

    if (parsed === problem.solution) {
      setError(null);
      onComplete();
    } else {
      const newAttempts = attempts + 1;
      setAttempts(newAttempts);
      setError(`Incorrect answer (${parsed}). Take another look and calculate again.`);
      setAnswer('');
      if (onFail) onFail();
    }
  };

  return (
    <div className="space-y-6 max-w-md mx-auto text-center">
      {/* Instructions */}
      <div className="space-y-1">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
          <span>🧮 Math Arithmetic Challenge</span>
        </div>
        <h3 className="text-xl font-bold text-slate-900 tracking-tight">
          Solve the Equation
        </h3>
        <p className="text-xs text-slate-600">
          Calculate the numerical sum to verify analytical alertness and stop the alarm.
        </p>
      </div>

      {/* Problem Display Card */}
      <div className="p-8 rounded-2xl bg-slate-50 border border-slate-200 shadow-xs">
        <span className="text-xs font-mono uppercase tracking-wider text-slate-500 block mb-2">
          Demo Equation
        </span>
        <div className="text-4xl sm:text-5xl font-mono font-extrabold text-slate-900 tracking-tight">
          {problem.num1} {problem.operator} {problem.num2} = ?
        </div>
      </div>

      {/* Solution Form */}
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-2">
          <label htmlFor="math-answer-input" className="sr-only">
            Solution Answer
          </label>
          <input
            id="math-answer-input"
            type="number"
            value={answer}
            onChange={(e) => {
              setAnswer(e.target.value);
              if (error) setError(null);
            }}
            placeholder="Type your answer"
            className="w-full text-center px-4 py-3 rounded-xl bg-white border border-slate-300 text-xl font-mono font-bold text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 transition-colors shadow-2xs"
            autoFocus
            required
          />
        </div>

        {error && (
          <div role="alert" className="p-3 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-700 flex items-center justify-center gap-2">
            <svg className="w-4 h-4 text-rose-500 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <circle cx="12" cy="12" r="10" strokeWidth="2"></circle>
              <path d="M12 8v4m0 4h.01" strokeWidth="2" strokeLinecap="round"></path>
            </svg>
            <span>{error}</span>
          </div>
        )}

        <button
          type="submit"
          className="w-full py-3 rounded-xl text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-700 shadow-md shadow-indigo-600/20 transition-all cursor-pointer focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          Submit Answer
        </button>
      </form>

      {/* Disclaimer */}
      <p className="text-[11px] text-slate-500 leading-relaxed">
        Deterministic demo content. Real GenAI challenge generation and adaptive difficulty connect in Phase 6.
      </p>
    </div>
  );
}
