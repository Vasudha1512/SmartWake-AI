import React, { useState } from 'react';

const PADS = [
  { id: 1, label: 'Pad 1', color: 'bg-indigo-600', activeColor: 'bg-indigo-400 ring-4 ring-indigo-300' },
  { id: 2, label: 'Pad 2', color: 'bg-emerald-600', activeColor: 'bg-emerald-400 ring-4 ring-emerald-300' },
  { id: 3, label: 'Pad 3', color: 'bg-purple-600', activeColor: 'bg-purple-400 ring-4 ring-purple-300' },
  { id: 4, label: 'Pad 4', color: 'bg-amber-600', activeColor: 'bg-amber-400 ring-4 ring-amber-300' },
];

const DEMO_SEQUENCE = [1, 3, 2, 4];

/**
 * MemoryChallenge component
 * Visual spatial memory sequence reproduction challenge.
 *
 * @param {{
 *   onComplete: () => void,
 *   onFail?: () => void
 * }} props
 */
export default function MemoryChallenge({ onComplete, onFail }) {
  const [phase, setPhase] = useState('ready'); // 'ready' | 'showing' | 'recalling'
  const [activePad, setActivePad] = useState(null);
  const [userSequence, setUserSequence] = useState([]);
  const [error, setError] = useState(null);

  const startSequence = () => {
    setPhase('showing');
    setError(null);
    setUserSequence([]);

    // Sequentially highlight the pads
    DEMO_SEQUENCE.forEach((padId, index) => {
      setTimeout(() => {
        setActivePad(padId);
      }, (index + 1) * 700);

      setTimeout(() => {
        setActivePad(null);
      }, (index + 1) * 700 + 450);
    });

    // Switch to recall phase after sequence displays
    setTimeout(() => {
      setActivePad(null);
      setPhase('recalling');
    }, (DEMO_SEQUENCE.length + 1) * 700);
  };

  const handlePadClick = (padId) => {
    if (phase !== 'recalling') return;

    const nextIndex = userSequence.length;
    const expectedPadId = DEMO_SEQUENCE[nextIndex];

    if (padId === expectedPadId) {
      const nextSequence = [...userSequence, padId];
      setUserSequence(nextSequence);

      if (nextSequence.length === DEMO_SEQUENCE.length) {
        // Complete!
        onComplete();
      }
    } else {
      // Mismatch!
      setError('Sequence mismatch. Watch the demo sequence again and retry.');
      setUserSequence([]);
      setPhase('ready');
      if (onFail) onFail();
    }
  };

  return (
    <div className="space-y-6 max-w-md mx-auto text-center">
      {/* Instructions */}
      <div className="space-y-1">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-500/10 text-emerald-400 border border-emerald-500/20">
          <span>🧠 Visual Memory Challenge</span>
        </div>
        <h3 className="text-xl font-bold text-white tracking-tight">
          Repeat the Sequence
        </h3>
        <p className="text-xs text-slate-400">
          Watch the pads illuminate, then tap them in the exact order shown.
        </p>
      </div>

      {/* Memory Pads Grid */}
      <div className="p-6 rounded-2xl bg-slate-950 border border-slate-800 shadow-inner">
        <div className="grid grid-cols-2 gap-4 max-w-xs mx-auto">
          {PADS.map((pad) => {
            const isHighlighted = activePad === pad.id;
            return (
              <button
                key={pad.id}
                type="button"
                disabled={phase !== 'recalling'}
                onClick={() => handlePadClick(pad.id)}
                aria-label={pad.label}
                className={`h-24 sm:h-28 rounded-2xl transition-all duration-150 flex items-center justify-center text-white font-bold text-xl shadow-lg focus:outline-none ${
                  isHighlighted
                    ? pad.activeColor + ' scale-105 shadow-2xl'
                    : pad.color + ' hover:opacity-90 active:scale-95'
                } ${phase !== 'recalling' ? 'cursor-default opacity-80' : 'cursor-pointer'}`}
              >
                {pad.id}
              </button>
            );
          })}
        </div>

        {/* Phase Status */}
        <div className="mt-4 text-xs font-medium text-slate-400">
          {phase === 'ready' && 'Press "Show Sequence" to begin.'}
          {phase === 'showing' && 'Watch carefully...'}
          {phase === 'recalling' && (
            <span className="text-emerald-400">
              Your turn! Tap the pads ({userSequence.length}/{DEMO_SEQUENCE.length})
            </span>
          )}
        </div>
      </div>

      {/* Error / Failure Banner */}
      {error && (
        <div role="alert" className="p-3 rounded-xl bg-rose-950/40 border border-rose-900/60 text-xs text-rose-300 flex items-center justify-center gap-2">
          <svg className="w-4 h-4 text-rose-400 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <circle cx="12" cy="12" r="10" strokeWidth="2"></circle>
            <path d="M12 8v4m0 4h.01" strokeWidth="2" strokeLinecap="round"></path>
          </svg>
          <span>{error}</span>
        </div>
      )}

      {/* Controls */}
      <div className="pt-2">
        {phase === 'ready' && (
          <button
            type="button"
            onClick={startSequence}
            className="w-full py-3 rounded-xl text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-500 shadow-lg shadow-indigo-600/30 transition-all cursor-pointer focus:outline-none focus:ring-2 focus:ring-indigo-500"
          >
            Show Sequence (4 steps)
          </button>
        )}

        {phase === 'showing' && (
          <div className="w-full py-3 rounded-xl text-sm font-semibold text-slate-400 bg-slate-900 border border-slate-800 animate-pulse">
            Displaying Sequence...
          </div>
        )}

        {phase === 'recalling' && (
          <button
            type="button"
            onClick={() => {
              setPhase('ready');
              setUserSequence([]);
            }}
            className="text-xs text-slate-400 hover:text-white transition-colors"
          >
            Restart Sequence
          </button>
        )}
      </div>

      {/* Disclaimer */}
      <p className="text-[11px] text-slate-400">
        Deterministic demo sequence. Adaptive sequence lengths calibrate via ML in Phase 6.
      </p>
    </div>
  );
}
