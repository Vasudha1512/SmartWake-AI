import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  verifySpeech,
  SPEECH_MATCH_THRESHOLD,
  DEFAULT_TONGUE_TWISTER,
} from '../../../utils/speechVerifier';

/**
 * TongueTwisterChallenge component
 * SmartWake AI interactive verbal articulation challenge.
 *
 * Uses browser Web Speech API (window.SpeechRecognition || window.webkitSpeechRecognition)
 * to capture user speech, and deterministic local string/token similarity to verify accuracy.
 *
 * Speech verification is performed locally using deterministic text comparison
 * without an LLM or external verification service. Browser speech recognition
 * availability and processing depend on the browser/platform.
 *
 * @param {{
 *   onComplete: () => void
 * }} props
 */
export default function TongueTwisterChallenge({ onComplete }) {
  // 'idle' | 'listening' | 'processing' | 'success' | 'failed' | 'unsupported' | 'permission_error'
  const [status, setStatus] = useState('idle');
  const [interimTranscript, setInterimTranscript] = useState('');
  const [finalTranscript, setFinalTranscript] = useState('');
  const [verificationResult, setVerificationResult] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);

  const targetPhrase = DEFAULT_TONGUE_TWISTER;

  const recognitionRef = useRef(null);
  const recognitionErrorRef = useRef(null);
  const finalTranscriptRef = useRef('');
  const hasCompletedRef = useRef(false);

  /**
   * Safely aborts recognition and strips event handlers to prevent
   * stale callbacks or memory leaks.
   */
  const cleanupRecognition = useCallback(() => {
    if (recognitionRef.current) {
      const rec = recognitionRef.current;
      rec.onstart = null;
      rec.onresult = null;
      rec.onerror = null;
      rec.onend = null;
      try {
        rec.abort();
      } catch {
        // Ignore abort errors on already-stopped instances
      }
      recognitionRef.current = null;
    }
  }, []);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      cleanupRecognition();
    };
  }, [cleanupRecognition]);

  /**
   * Starts a fresh speech recognition session upon user click.
   */
  const startListening = useCallback(() => {
    // 1. Clean up any previous session
    cleanupRecognition();

    // 2. Reset session state and guard refs
    recognitionErrorRef.current = null;
    finalTranscriptRef.current = '';
    hasCompletedRef.current = false;
    setInterimTranscript('');
    setFinalTranscript('');
    setVerificationResult(null);
    setErrorMessage(null);

    // 3. Detect browser Web Speech API support safely
    const SpeechRecognition =
      typeof window !== 'undefined'
        ? window.SpeechRecognition || window.webkitSpeechRecognition
        : null;

    if (!SpeechRecognition) {
      setStatus('unsupported');
      setErrorMessage(
        'Web Speech Recognition is not supported by your current browser. Please try using a supported browser like Chrome, Edge, or Safari.'
      );
      return;
    }

    try {
      const recognition = new SpeechRecognition();
      recognition.lang = 'en-US';
      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.maxAlternatives = 1;

      recognition.onstart = () => {
        if (hasCompletedRef.current) return;
        setStatus('listening');
        setErrorMessage(null);
      };

      recognition.onresult = (event) => {
        if (hasCompletedRef.current || recognitionErrorRef.current) return;

        let interim = '';
        let final = '';

        for (let i = event.resultIndex; i < event.results.length; i++) {
          const result = event.results[i];
          const transcriptChunk = result[0]?.transcript || '';

          if (result.isFinal) {
            final += transcriptChunk;
          } else {
            interim += transcriptChunk;
          }
        }

        if (interim) {
          setInterimTranscript(interim);
        }

        if (final) {
          finalTranscriptRef.current += (finalTranscriptRef.current ? ' ' : '') + final.trim();
          setFinalTranscript(finalTranscriptRef.current);
          setInterimTranscript('');
        }
      };

      recognition.onerror = (event) => {
        // Record that this session terminated with an error
        recognitionErrorRef.current = event.error || 'unknown';

        let friendlyMessage = 'Speech recognition encountered an issue. Please try again.';

        if (event.error === 'not-allowed' || event.error === 'permission-denied') {
          setStatus('permission_error');
          friendlyMessage =
            'Microphone access was denied. Please grant microphone permissions in your browser address bar to recite the tongue twister.';
        } else if (event.error === 'no-speech') {
          setStatus('failed');
          friendlyMessage = 'No speech was detected. Please speak clearly into your microphone and try again.';
        } else if (event.error === 'audio-capture') {
          setStatus('permission_error');
          friendlyMessage = 'No microphone was detected on your device. Please connect an audio input device.';
        } else if (event.error === 'network') {
          setStatus('failed');
          friendlyMessage = 'Speech service network error occurred. Please check your connection and try again.';
        } else if (event.error === 'aborted') {
          return;
        } else {
          setStatus('failed');
        }

        setErrorMessage(friendlyMessage);
      };

      recognition.onend = () => {
        // Critical race-condition protection:
        // Do NOT verify or complete if session ended due to an error or if already completed
        if (recognitionErrorRef.current) {
          return;
        }

        if (hasCompletedRef.current) {
          return;
        }

        const transcriptToVerify = finalTranscriptRef.current.trim();

        if (!transcriptToVerify) {
          setStatus('failed');
          setErrorMessage('No finalized speech was recognized. Please try reciting the phrase again.');
          return;
        }

        setStatus('processing');

        // Deterministic offline verification
        const result = verifySpeech(transcriptToVerify, targetPhrase, SPEECH_MATCH_THRESHOLD);
        setVerificationResult(result);

        if (result.matched) {
          hasCompletedRef.current = true;
          setStatus('success');
          cleanupRecognition();

          // Invoke authoritative wake session completion exactly once
          if (typeof onComplete === 'function') {
            onComplete();
          }
        } else {
          setStatus('failed');
        }
      };

      recognitionRef.current = recognition;
      recognition.start();
    } catch (err) {
      cleanupRecognition();
      recognitionErrorRef.current = 'exception';
      setStatus('failed');
      setErrorMessage(err.message || 'Unable to start speech recognition. Please try again.');
    }
  }, [cleanupRecognition, onComplete, targetPhrase]);

  /**
   * Stops listening manually.
   */
  const stopListening = () => {
    if (recognitionRef.current) {
      try {
        recognitionRef.current.stop();
      } catch {
        cleanupRecognition();
      }
    }
  };

  /**
   * Resets state back to idle ready state.
   */
  const handleReset = () => {
    cleanupRecognition();
    recognitionErrorRef.current = null;
    finalTranscriptRef.current = '';
    hasCompletedRef.current = false;
    setInterimTranscript('');
    setFinalTranscript('');
    setVerificationResult(null);
    setErrorMessage(null);
    setStatus('idle');
  };

  return (
    <div className="space-y-6 text-center max-w-lg mx-auto">
      {/* 1. Instructions Header */}
      <div className="space-y-1">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-rose-50 text-rose-700 border border-rose-200">
          <span>👅 Tongue Twister Verbal Challenge</span>
        </div>
        <h3 className="text-xl font-bold text-slate-900 tracking-tight">
          Recite the Phrase Aloud
        </h3>
        <p className="text-xs text-slate-600 max-w-md mx-auto">
          Speak the tongue twister clearly to activate verbal motor coordination and prove morning wakefulness.
        </p>
      </div>

      {/* 2. Target Tongue Twister Card (always visible during attempt) */}
      <div className="p-5 sm:p-6 rounded-2xl bg-white border-2 border-rose-200 shadow-xs space-y-2 text-left relative overflow-hidden">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-bold uppercase tracking-wider text-rose-600">
            Target Tongue Twister
          </span>
          <span className="text-[10px] font-mono text-slate-500 bg-slate-100 px-2 py-0.5 rounded border border-slate-200">
            Min {Math.round(SPEECH_MATCH_THRESHOLD * 100)}% Match
          </span>
        </div>

        <blockquote className="text-base sm:text-lg font-semibold text-slate-900 leading-relaxed italic border-l-4 border-rose-400 pl-3 py-1">
          &ldquo;{targetPhrase}&rdquo;
        </blockquote>

        <p className="text-[11px] text-slate-500 pt-1">
          Recite the full sentence at a natural pace.
        </p>
      </div>

      {/* 3. Live Speech Recognition Viewport */}
      <div className="p-5 sm:p-6 rounded-2xl bg-slate-50 border border-slate-200 shadow-2xs space-y-4">
        {/* State A: Idle / Ready to Listen */}
        {status === 'idle' && (
          <div className="space-y-2 py-2">
            <div className="w-12 h-12 rounded-full bg-rose-100 text-rose-600 flex items-center justify-center mx-auto text-xl shadow-2xs">
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
              </svg>
            </div>
            <p className="text-sm font-semibold text-slate-800">Ready to Listen</p>
            <p className="text-xs text-slate-500 max-w-xs mx-auto">
              Click &quot;Start Speaking&quot; below, allow microphone access, and recite the phrase aloud.
            </p>
          </div>
        )}

        {/* State B: Listening State */}
        {status === 'listening' && (
          <div className="space-y-3 py-1 animate-fade-in" role="status" aria-live="polite">
            <div className="flex items-center justify-center gap-2">
              <span className="relative flex h-3.5 w-3.5">
                <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-rose-400 opacity-75"></span>
                <span className="relative inline-flex rounded-full h-3.5 w-3.5 bg-rose-600"></span>
              </span>
              <span className="text-xs font-bold uppercase tracking-wider text-rose-700 font-mono">
                Listening for speech...
              </span>
            </div>

            {/* Live Transcript Display Box */}
            <div className="p-3.5 rounded-xl bg-white border border-rose-200 min-h-[64px] flex flex-col justify-center text-left">
              <span className="text-[10px] font-mono text-slate-600 uppercase mb-1 block">
                Live Speech Recognition:
              </span>
              <p className="text-xs text-slate-800 font-medium italic">
                {finalTranscript ? <span>{finalTranscript} </span> : null}
                <span className="text-rose-600 font-normal">
                  {interimTranscript || (!finalTranscript ? 'Speak now...' : '')}
                </span>
              </p>
            </div>

            <button
              type="button"
              onClick={stopListening}
              className="inline-flex items-center px-4 py-1.5 rounded-lg text-xs font-semibold text-slate-700 bg-white hover:bg-slate-100 border border-slate-300 shadow-2xs transition-colors cursor-pointer"
            >
              <span>Stop &amp; Verify</span>
            </button>
          </div>
        )}

        {/* State C: Processing / Verifying */}
        {status === 'processing' && (
          <div className="space-y-2 py-3" role="status" aria-live="polite">
            <div className="w-8 h-8 rounded-full border-2 border-rose-500 border-t-transparent animate-spin mx-auto" />
            <p className="text-xs font-semibold text-slate-800">Verifying speech phonetics...</p>
          </div>
        )}

        {/* State D: Success */}
        {status === 'success' && (
          <div className="space-y-3 py-2 animate-fade-in" role="status" aria-live="polite">
            <div className="w-12 h-12 rounded-2xl bg-emerald-50 text-emerald-600 border border-emerald-200 flex items-center justify-center text-2xl mx-auto shadow-xs">
              ✓
            </div>
            <div className="space-y-1">
              <p className="text-base font-bold text-slate-900">Speech Verified!</p>
              <p className="text-xs text-emerald-700 font-medium">
                Match Score: {Math.round((verificationResult?.score || 0) * 100)}% (Passes {Math.round(SPEECH_MATCH_THRESHOLD * 100)}% threshold)
              </p>
            </div>

            <div className="p-3 rounded-xl bg-emerald-50 border border-emerald-200 text-left text-xs text-emerald-900 space-y-1">
              <span className="text-[10px] font-mono uppercase text-emerald-700 block font-bold">
                Recognized Speech:
              </span>
              <p className="italic">&ldquo;{finalTranscript}&rdquo;</p>
            </div>
          </div>
        )}

        {/* State E: Failed Verification (Mismatch or partial) */}
        {status === 'failed' && (
          <div className="space-y-3 py-1 text-left" role="alert">
            <div className="flex items-center justify-between">
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-100 text-amber-800 border border-amber-200">
                <span>⚠️</span>
                <span>Verification Incomplete</span>
              </span>
              {verificationResult && (
                <span className="text-xs font-mono font-bold text-slate-700">
                  Score: {Math.round(verificationResult.score * 100)}% (Required: {Math.round(SPEECH_MATCH_THRESHOLD * 100)}%)
                </span>
              )}
            </div>

            {errorMessage && (
              <p className="text-xs text-slate-600">{errorMessage}</p>
            )}

            {finalTranscript && (
              <div className="p-3 rounded-xl bg-white border border-slate-200 space-y-1">
                <span className="text-[10px] font-mono uppercase text-slate-600 block">
                  What was heard:
                </span>
                <p className="text-xs text-slate-800 italic">&ldquo;{finalTranscript}&rdquo;</p>
              </div>
            )}

            <p className="text-[11px] text-slate-500">
              Ensure you recite the entire phrase clearly without skipping words or trailing off.
            </p>
          </div>
        )}

        {/* State F: Permission Error */}
        {status === 'permission_error' && (
          <div className="space-y-2 py-1 text-left" role="alert">
            <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-bold bg-rose-100 text-rose-800 border border-rose-200">
              <span>🔒</span>
              <span>Microphone Access Required</span>
            </div>
            <p className="text-xs text-slate-700 leading-relaxed">
              {errorMessage || 'Microphone permission was not granted.'}
            </p>
            <p className="text-[11px] text-slate-500">
              Click the microphone or permissions icon in your browser address bar to allow access.
            </p>
          </div>
        )}

        {/* State G: Unsupported Browser */}
        {status === 'unsupported' && (
          <div className="space-y-2 py-1 text-left" role="alert">
            <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-bold bg-amber-100 text-amber-900 border border-amber-200">
              <span>⚠️</span>
              <span>Browser Speech API Unsupported</span>
            </div>
            <p className="text-xs text-slate-700 leading-relaxed">
              {errorMessage}
            </p>
          </div>
        )}
      </div>

      {/* 4. Technology & Local Processing Notice */}
      <div className="p-3.5 rounded-xl bg-slate-50 border border-slate-200 text-[11px] text-slate-500 text-left leading-relaxed">
        <span className="font-semibold text-slate-700 block mb-0.5">Local Deterministic Verification</span>
        Speech verification is performed locally using deterministic text comparison without an LLM or external verification service. Browser speech recognition availability and processing depend on the browser/platform.
      </div>

      {/* 5. Primary Action Buttons */}
      <div className="pt-1 flex flex-col sm:flex-row items-center justify-center gap-3">
        {(status === 'idle' || status === 'unsupported') && (
          <button
            type="button"
            onClick={startListening}
            disabled={status === 'unsupported'}
            className={`w-full sm:w-auto inline-flex items-center justify-center px-8 py-3.5 rounded-xl text-sm font-bold text-white shadow-md transition-all ${
              status === 'unsupported'
                ? 'bg-slate-400 cursor-not-allowed shadow-none'
                : 'bg-rose-600 hover:bg-rose-700 shadow-rose-600/20 cursor-pointer focus:outline-none focus:ring-2 focus:ring-rose-500'
            }`}
          >
            <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 11a7 7 0 01-7 7m0 0a7 7 0 01-7-7m7 7v4m0 0H8m4 0h4m-4-8a3 3 0 01-3-3V5a3 3 0 116 0v6a3 3 0 01-3 3z" />
            </svg>
            <span>Start Speaking</span>
          </button>
        )}

        {(status === 'failed' || status === 'permission_error') && (
          <div className="w-full sm:w-auto flex items-center gap-2">
            <button
              type="button"
              onClick={startListening}
              className="w-full sm:w-auto inline-flex items-center justify-center px-6 py-3 rounded-xl text-sm font-bold text-white bg-rose-600 hover:bg-rose-700 shadow-md shadow-rose-600/20 transition-all cursor-pointer"
            >
              <svg className="w-4 h-4 mr-1.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
              </svg>
              <span>Try Again</span>
            </button>
            <button
              type="button"
              onClick={handleReset}
              className="px-4 py-3 rounded-xl text-xs font-semibold text-slate-700 bg-white hover:bg-slate-100 border border-slate-300 shadow-2xs transition-colors cursor-pointer"
            >
              Reset
            </button>
          </div>
        )}

        {status === 'success' && (
          <div className="text-xs font-semibold text-emerald-700 bg-emerald-50 px-4 py-2 rounded-xl border border-emerald-200">
            Handing off to wake session completion...
          </div>
        )}
      </div>
    </div>
  );
}
