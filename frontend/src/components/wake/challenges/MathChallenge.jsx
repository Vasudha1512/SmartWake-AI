import React, { useState, useRef, useEffect } from 'react';
import {
  generateMathProblem,
  validateMathAnswer,
} from '../../../utils/mathChallenge';

/**
 * MathChallenge component
 * SmartWake AI deterministic cognitive verification challenge.
 *
 * Generates dynamic arithmetic equations and strictly validates user numeric input.
 * On incorrect answers, generates a fresh problem and clears input without revealing
 * the expected solution.
 *
 * @param {{
 *   onComplete: () => void,
 *   onFail?: () => void
 * }} props
 */
export default function MathChallenge({ onComplete, onFail }) {
  // Lazily initialize initial problem once to prevent re-generation during re-renders or StrictMode
  const [problem, setProblem] = useState(() => generateMathProblem({ difficulty: 'medium' }));
  const [answer, setAnswer] = useState('');
  const [feedback, setFeedback] = useState(null); // { type: 'success' | 'error', message: string } | null
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [attempts, setAttempts] = useState(0);

  const inputRef = useRef(null);
  const hasCompletedRef = useRef(false);
  const isSubmittingRef = useRef(false);
  const focusTimeoutRef = useRef(null);

  // Focus input field on mount and cleanup pending timeouts on unmount
  useEffect(() => {
    inputRef.current?.focus();
    return () => {
      if (focusTimeoutRef.current) {
        clearTimeout(focusTimeoutRef.current);
      }
    };
  }, []);

  const handleSubmit = (e) => {
    e.preventDefault();

    if (isSubmitting || isSubmittingRef.current || hasCompletedRef.current) {
      return;
    }

    const trimmed = answer.trim();
    if (!trimmed) {
      setFeedback({
        type: 'error',
        message: 'Please enter a valid numerical answer.',
      });
      inputRef.current?.focus();
      return;
    }

    const validation = validateMathAnswer(problem, trimmed);

    if (validation.error) {
      setFeedback({
        type: 'error',
        message: 'Please enter a valid numerical answer.',
      });
      return;
    }

    isSubmittingRef.current = true;
    setIsSubmitting(true);

    if (validation.correct) {
      if (!hasCompletedRef.current) {
        hasCompletedRef.current = true;
        setFeedback({
          type: 'success',
          message: 'Correct! Verified mathematical alertness.',
        });

        if (typeof onComplete === 'function') {
          onComplete();
        }
      }
    } else {
      setAttempts((prev) => prev + 1);
      // Requirement: Show retry feedback, do not expose the expected answer, clear input, generate fresh problem
      setFeedback({
        type: 'error',
        message: 'Incorrect answer. Try this new equation!',
      });
      setAnswer('');
      setProblem(generateMathProblem({ difficulty: 'medium' }));

      // Reset submission lock and re-focus input field after state reconciliation
      if (focusTimeoutRef.current) {
        clearTimeout(focusTimeoutRef.current);
      }
      focusTimeoutRef.current = setTimeout(() => {
        isSubmittingRef.current = false;
        setIsSubmitting(false);
        inputRef.current?.focus();
      }, 100);
    }
  };

  return (
    <div className="space-y-6 max-w-md mx-auto text-center">
      {/* 1. Instructions */}
      <div className="space-y-1">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
          <span>🧮 Math Arithmetic Challenge</span>
        </div>
        <h3 className="text-xl font-bold text-slate-900 tracking-tight">
          Solve the Equation
        </h3>
        <p className="text-xs text-slate-600">
          Calculate the numerical answer to verify analytical alertness and stop the alarm.
        </p>
      </div>

      {/* 2. Dynamic Problem Display Card */}
      <div className="p-8 rounded-2xl bg-slate-50 border border-slate-200 shadow-xs relative">
        <div className="flex items-center justify-between text-xs font-mono text-slate-500 mb-3">
          <span className="uppercase tracking-wider">Arithmetic Verification</span>
          <span className="bg-slate-200/80 text-slate-700 px-2 py-0.5 rounded text-[11px] font-semibold">
            {problem.difficulty.toUpperCase()}
          </span>
        </div>

        <div
          className="text-4xl sm:text-5xl font-mono font-extrabold text-slate-900 tracking-tight select-all"
          aria-label={`Equation: ${problem.displayExpression}`}
        >
          {problem.displayExpression} = ?
        </div>
      </div>

      {/* 3. Solution Form */}
      <form onSubmit={handleSubmit} className="space-y-4">
        <div className="space-y-2">
          <label htmlFor="math-answer-input" className="sr-only">
            Your Answer
          </label>
          <input
            ref={inputRef}
            id="math-answer-input"
            type="text"
            inputMode="numeric"
            pattern="[0-9\-]*"
            autoComplete="off"
            value={answer}
            onChange={(e) => {
              setAnswer(e.target.value);
              if (feedback?.type === 'error') {
                setFeedback(null);
              }
            }}
            placeholder="Type your answer"
            disabled={isSubmitting || hasCompletedRef.current}
            className="w-full text-center px-4 py-3.5 rounded-xl bg-white border border-slate-300 text-2xl font-mono font-bold text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500 transition-colors shadow-2xs disabled:bg-slate-100 disabled:text-slate-500"
            required
          />
        </div>

        {/* Feedback alert (no layout shift) */}
        {feedback && (
          <div
            role="alert"
            className={`p-3 rounded-xl text-xs font-medium flex items-center justify-center gap-2 border transition-all ${
              feedback.type === 'success'
                ? 'bg-emerald-50 border-emerald-200 text-emerald-800'
                : 'bg-rose-50 border-rose-200 text-rose-800'
            }`}
          >
            <span>{feedback.type === 'success' ? '✓' : '⚠️'}</span>
            <span>{feedback.message}</span>
          </div>
        )}

        <button
          type="submit"
          disabled={isSubmitting || !answer.trim() || hasCompletedRef.current}
          className="w-full py-3.5 rounded-xl text-sm font-bold text-white bg-indigo-600 hover:bg-indigo-700 disabled:opacity-50 disabled:cursor-not-allowed shadow-md shadow-indigo-600/20 transition-all cursor-pointer focus:outline-none focus:ring-2 focus:ring-indigo-500"
        >
          {isSubmitting ? 'Checking Answer...' : 'Submit Answer'}
        </button>
      </form>

      {/* 4. Footer Guidance */}
      <p className="text-[11px] text-slate-500 leading-relaxed">
        Deterministic arithmetic challenge. Solve correctly to dismiss the wake alarm.
      </p>
    </div>
  );
}
