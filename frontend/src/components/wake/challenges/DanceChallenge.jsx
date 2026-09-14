import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  createMotionDetector,
  extractGrayscale,
  MOTION_THRESHOLD,
  TARGET_ACTIVE_MOVEMENT_MS,
  FRAME_WIDTH,
  FRAME_HEIGHT,
  MAX_FRAME_DELTA_MS,
} from '../../../utils/motionDetector';
import {
  startDanceMusic,
  stopDanceMusic,
  isDanceMusicPlaying,
} from '../../../utils/danceAudio';

/**
 * DanceChallenge component
 * SmartWake AI interactive physical movement challenge.
 *
 * Uses getUserMedia() for camera stream, procedural Web Audio for upbeat dance music,
 * and deterministic HTML5 Canvas frame-differencing for body movement detection.
 *
 * Exact completion rule:
 * User must accumulate 10,000 ms (10 seconds) of verified movement where
 * mean frame pixel delta >= MOTION_THRESHOLD (12). Frame deltas are clamped to
 * MAX_FRAME_DELTA_MS (100ms) to prevent burst credit from stalls.
 *
 * @param {{
 *   onComplete: () => void
 * }} props
 */
export default function DanceChallenge({ onComplete }) {
  // 'ready' | 'starting' | 'active' | 'completed' | 'error'
  const [challengeState, setChallengeState] = useState('ready');
  const [errorMessage, setErrorMessage] = useState(null);
  const [activeMovementMs, setActiveMovementMs] = useState(0);
  const [isMoving, setIsMoving] = useState(false);
  const [motionScore, setMotionScore] = useState(0);

  const videoRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const animationFrameRef = useRef(null);
  const detectorRef = useRef(null);
  const offscreenCanvasRef = useRef(null);
  const lastFrameTimestampRef = useRef(null);
  const hasCompletedRef = useRef(false);

  /**
   * Safely releases all active camera tracks, animation loops,
   * audio synthesizer nodes, and detector buffers.
   */
  const stopAllResources = useCallback(() => {
    // 1. Cancel animation frame loop
    if (animationFrameRef.current) {
      cancelAnimationFrame(animationFrameRef.current);
      animationFrameRef.current = null;
    }

    // 2. Stop camera stream tracks
    if (mediaStreamRef.current) {
      try {
        const tracks = mediaStreamRef.current.getTracks();
        for (const track of tracks) {
          track.stop();
        }
      } catch {
        // Ignore track stopping errors
      }
      mediaStreamRef.current = null;
    }

    // 3. Clear video source
    if (videoRef.current) {
      videoRef.current.srcObject = null;
    }

    // 4. Stop Dance challenge music
    stopDanceMusic();

    // 5. Reset detector
    if (detectorRef.current) {
      detectorRef.current.reset();
    }
    lastFrameTimestampRef.current = null;
  }, []);

  // Guarantee clean teardown when component unmounts or user navigates away
  useEffect(() => {
    return () => {
      stopAllResources();
    };
  }, [stopAllResources]);

  /**
   * Challenge success sequence.
   * Cleans up all hardware/audio resources and invokes the single authoritative
   * wake completion callback passed from Wake.jsx.
   */
  const handleSuccess = useCallback(() => {
    stopAllResources();
    setChallengeState('completed');

    if (typeof onComplete === 'function') {
      onComplete();
    }
  }, [onComplete, stopAllResources]);

  /**
   * Motion analysis animation frame loop.
   * Samples video frames at browser's available refresh rate and passes
   * downsampled grayscale buffers to the motion detector.
   */
  const startMotionLoop = useCallback(() => {
    const loop = (currentTimestamp) => {
      const video = videoRef.current;
      const detector = detectorRef.current;

      if (!video || !detector || hasCompletedRef.current) {
        return;
      }

      // Ensure video is ready and has valid dimensions
      if (video.readyState >= 2 && video.videoWidth > 0 && video.videoHeight > 0) {
        const actualDeltaMs = lastFrameTimestampRef.current !== null
          ? currentTimestamp - lastFrameTimestampRef.current
          : 16;
        lastFrameTimestampRef.current = currentTimestamp;

        if (!offscreenCanvasRef.current) {
          offscreenCanvasRef.current = document.createElement('canvas');
          offscreenCanvasRef.current.width = FRAME_WIDTH;
          offscreenCanvasRef.current.height = FRAME_HEIGHT;
        }

        const canvas = offscreenCanvasRef.current;
        const ctx = canvas.getContext('2d', { willReadFrequently: true });

        if (ctx) {
          ctx.drawImage(video, 0, 0, FRAME_WIDTH, FRAME_HEIGHT);
          const imageData = ctx.getImageData(0, 0, FRAME_WIDTH, FRAME_HEIGHT);
          const grayscale = extractGrayscale(imageData, FRAME_WIDTH, FRAME_HEIGHT);

          const result = detector.processFrame(grayscale, actualDeltaMs);

          setActiveMovementMs(result.accumulatedMs);
          setIsMoving(result.isMoving);
          setMotionScore(Math.round(result.motionScore));

          if (result.isCompleted && !hasCompletedRef.current) {
            hasCompletedRef.current = true;
            handleSuccess();
            return;
          }
        }
      }

      animationFrameRef.current = requestAnimationFrame(loop);
    };

    animationFrameRef.current = requestAnimationFrame(loop);
  }, [handleSuccess]);

  /**
   * Initiates camera access, starts dance rhythm music,
   * and mounts the motion tracking loop.
   */
  const handleStartChallenge = async () => {
    stopAllResources();
    setChallengeState('starting');
    setErrorMessage(null);
    setActiveMovementMs(0);
    setIsMoving(false);
    setMotionScore(0);
    hasCompletedRef.current = false;

    // Initialize motion detector
    detectorRef.current = createMotionDetector({
      threshold: MOTION_THRESHOLD,
      targetMs: TARGET_ACTIVE_MOVEMENT_MS,
      width: FRAME_WIDTH,
      height: FRAME_HEIGHT,
      maxDeltaMs: MAX_FRAME_DELTA_MS,
    });

    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error('Camera access is not supported by your browser.');
      }

      const stream = await navigator.mediaDevices.getUserMedia({
        video: {
          facingMode: 'user',
          width: { ideal: 640 },
          height: { ideal: 480 },
        },
        audio: false,
      });

      mediaStreamRef.current = stream;

      if (videoRef.current) {
        videoRef.current.srcObject = stream;
        await videoRef.current.play().catch(() => {});
      }

      // Start Dance challenge music upon user interaction
      startDanceMusic();

      setChallengeState('active');
      lastFrameTimestampRef.current = performance.now();
      startMotionLoop();
    } catch (err) {
      stopAllResources();
      setChallengeState('error');

      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        setErrorMessage(
          'Camera access was denied. Please grant camera permission in your browser address bar to perform the Dance challenge.'
        );
      } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
        setErrorMessage(
          'No camera was found on this device. Please connect a webcam or enable camera hardware.'
        );
      } else {
        setErrorMessage(
          err.message || 'Could not initialize camera. Please check your browser settings and try again.'
        );
      }
    }
  };

  /**
   * Resets the challenge to the ready state and cleans up resources.
   */
  const handleReset = () => {
    stopAllResources();
    setChallengeState('ready');
    setActiveMovementMs(0);
    setIsMoving(false);
    setMotionScore(0);
    setErrorMessage(null);
    hasCompletedRef.current = false;
  };

  const remainingSeconds = Math.max(
    0,
    Math.ceil((TARGET_ACTIVE_MOVEMENT_MS - activeMovementMs) / 1000)
  );
  const progressPercent = Math.min(
    100,
    Math.round((activeMovementMs / TARGET_ACTIVE_MOVEMENT_MS) * 100)
  );

  return (
    <div className="space-y-6 text-center max-w-lg mx-auto">
      {/* 1. Header & Instructions */}
      <div className="space-y-1">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-purple-50 text-purple-700 border border-purple-200">
          <span>🕺 Dance Movement Challenge</span>
        </div>
        <h3 className="text-xl font-bold text-slate-900 tracking-tight">
          Morning Dance Verification
        </h3>
        <p className="text-xs text-slate-600 max-w-md mx-auto">
          Move your body to the rhythm for 10 cumulative seconds to prove motor alertness and wakefulness.
        </p>
      </div>

      {/* 2. Main Viewport Area */}
      <div className="relative aspect-video max-w-md mx-auto rounded-2xl bg-slate-900 border-2 border-purple-200 overflow-hidden shadow-md flex items-center justify-center">
        {/* State A: Camera Active Viewport */}
        <video
          ref={videoRef}
          playsInline
          muted
          autoPlay
          className={`w-full h-full object-cover transform scale-x-[-1] ${
            challengeState === 'active' ? 'block' : 'hidden'
          }`}
          aria-label="Live camera feed for movement detection"
        />

        {/* Live Camera Overlays (when active) */}
        {challengeState === 'active' && (
          <div className="absolute inset-0 pointer-events-none flex flex-col justify-between p-3.5 bg-gradient-to-b from-black/40 via-transparent to-black/60">
            {/* Top Status Bar: Audio badge & countdown */}
            <div className="flex items-center justify-between gap-2">
              <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold bg-purple-600/90 text-white backdrop-blur-xs border border-purple-400/40 shadow-xs animate-pulse">
                <span>🎵</span>
                <span>Rhythm Playing</span>
              </span>

              <span
                role="timer"
                aria-live="polite"
                className="px-3 py-1 rounded-full text-xs font-mono font-bold bg-black/60 text-amber-300 backdrop-blur-xs border border-white/20 shadow-xs"
              >
                {remainingSeconds}s remaining
              </span>
            </div>

            {/* Bottom Status Bar: Live motion indicator & score */}
            <div className="space-y-2">
              <div className="flex items-center justify-between">
                <div
                  role="status"
                  aria-live="polite"
                  className={`inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-bold shadow-sm transition-colors ${
                    isMoving
                      ? 'bg-emerald-500 text-white'
                      : 'bg-amber-500 text-slate-950'
                  }`}
                >
                  <span className={`w-2 h-2 rounded-full ${isMoving ? 'bg-white animate-ping' : 'bg-slate-950'}`} />
                  <span>{isMoving ? 'Active Dancing!' : 'Move to the Beat!'}</span>
                </div>

                <span className="text-[11px] font-mono text-white/90 bg-black/50 px-2 py-0.5 rounded backdrop-blur-xs">
                  Motion: {motionScore} (min {MOTION_THRESHOLD})
                </span>
              </div>
            </div>
          </div>
        )}

        {/* State B: Pre-start / Ready Placeholder */}
        {challengeState === 'ready' && (
          <div className="p-6 text-center space-y-3">
            <div className="w-16 h-16 rounded-2xl bg-purple-100 text-purple-700 border border-purple-200 flex items-center justify-center text-3xl mx-auto shadow-2xs">
              🕺
            </div>
            <div className="space-y-1">
              <p className="text-sm font-bold text-white">Camera &amp; Music Ready</p>
              <p className="text-xs text-slate-300 max-w-xs mx-auto">
                Press start below to activate the video camera and rhythmic music.
              </p>
            </div>
          </div>
        )}

        {/* State C: Starting / Requesting Permissions */}
        {challengeState === 'starting' && (
          <div className="p-6 text-center space-y-3">
            <div className="w-12 h-12 rounded-full border-3 border-purple-400 border-t-transparent animate-spin mx-auto" />
            <p className="text-sm font-semibold text-white">
              Connecting camera &amp; starting rhythm...
            </p>
            <p className="text-xs text-slate-400">
              Please allow browser camera permissions when prompted.
            </p>
          </div>
        )}

        {/* State D: Success Overlay */}
        {challengeState === 'completed' && (
          <div className="p-6 text-center space-y-2 bg-slate-900/95 inset-0 absolute flex flex-col items-center justify-center">
            <div className="w-14 h-14 rounded-2xl bg-emerald-500 text-white flex items-center justify-center text-2xl shadow-lg">
              ✓
            </div>
            <p className="text-base font-bold text-white">Dance Challenge Complete!</p>
            <p className="text-xs text-emerald-400">
              Verified 10 seconds of active physical movement.
            </p>
          </div>
        )}

        {/* State E: Error Display in Viewport */}
        {challengeState === 'error' && (
          <div className="p-5 text-center space-y-2 max-w-xs">
            <div className="w-12 h-12 rounded-xl bg-rose-500/20 text-rose-400 border border-rose-500/30 flex items-center justify-center text-xl mx-auto">
              ⚠️
            </div>
            <p className="text-xs font-bold text-rose-300">Camera Unavailable</p>
            <p className="text-[11px] text-slate-300 leading-relaxed">
              {errorMessage || 'Unable to open camera.'}
            </p>
          </div>
        )}
      </div>

      {/* 3. Progress Tracking Bar (visible when active or after start) */}
      {(challengeState === 'active' || challengeState === 'starting' || challengeState === 'completed') && (
        <div className="space-y-2 bg-slate-50 border border-slate-200 p-4 rounded-xl text-left shadow-2xs">
          <div className="flex items-center justify-between text-xs font-semibold">
            <span className="text-slate-700">Movement Accumulation</span>
            <span className="font-mono text-purple-700">
              {(activeMovementMs / 1000).toFixed(1)}s / {(TARGET_ACTIVE_MOVEMENT_MS / 1000).toFixed(0)}s ({progressPercent}%)
            </span>
          </div>

          <div
            className="h-3 w-full bg-slate-200 rounded-full overflow-hidden shadow-inner"
            role="progressbar"
            aria-valuenow={progressPercent}
            aria-valuemin="0"
            aria-valuemax="100"
            aria-label="Dance movement progress"
          >
            <div
              className="h-full bg-gradient-to-r from-purple-600 to-indigo-600 transition-all duration-150 rounded-full"
              style={{ width: `${progressPercent}%` }}
            />
          </div>

          <div className="flex items-center justify-between text-[11px] text-slate-500 pt-0.5">
            <span>Deterministic rule: 10.0s active body motion</span>
            <span className={isMoving ? 'text-emerald-600 font-bold' : 'text-slate-500'}>
              {isMoving ? '● Accumulating progress' : '○ Stand in view & move'}
            </span>
          </div>
        </div>
      )}

      {/* 4. Error Card & Recovery Action */}
      {challengeState === 'error' && (
        <div
          role="alert"
          className="p-4 rounded-xl bg-rose-50 border border-rose-200 text-xs text-rose-800 space-y-3 text-left"
        >
          <div className="flex items-start gap-2.5">
            <span className="text-base leading-none">⚠️</span>
            <div className="space-y-1">
              <span className="font-bold block">Camera Access Notice</span>
              <p className="leading-relaxed">{errorMessage}</p>
            </div>
          </div>

          <div className="pt-1 flex items-center gap-2">
            <button
              type="button"
              onClick={handleStartChallenge}
              className="px-4 py-2 rounded-lg text-xs font-bold text-white bg-rose-600 hover:bg-rose-700 transition-colors cursor-pointer shadow-xs"
            >
              Retry Camera Permission
            </button>
            <button
              type="button"
              onClick={handleReset}
              className="px-3 py-2 rounded-lg text-xs font-medium text-slate-600 hover:text-slate-900 bg-white border border-slate-200 rounded-lg transition-colors cursor-pointer"
            >
              Cancel
            </button>
          </div>
        </div>
      )}

      {/* 5. Primary Actions */}
      <div className="pt-1 flex flex-col sm:flex-row items-center justify-center gap-3">
        {challengeState === 'ready' && (
          <button
            type="button"
            onClick={handleStartChallenge}
            className="w-full sm:w-auto inline-flex items-center justify-center px-8 py-3.5 rounded-xl text-sm font-bold text-white bg-purple-600 hover:bg-purple-700 shadow-md shadow-purple-600/20 transition-all cursor-pointer focus:outline-none focus:ring-2 focus:ring-purple-500"
          >
            <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
            <span>Start Dance Challenge</span>
          </button>
        )}

        {challengeState === 'active' && (
          <button
            type="button"
            onClick={handleReset}
            className="w-full sm:w-auto px-5 py-2.5 rounded-xl text-xs font-semibold text-slate-700 bg-white hover:bg-slate-100 border border-slate-300 shadow-2xs transition-colors cursor-pointer"
          >
            Restart Challenge
          </button>
        )}

        {challengeState === 'completed' && (
          <div className="text-xs text-emerald-700 font-semibold bg-emerald-50 px-4 py-2 rounded-xl border border-emerald-200">
            Handing off to wake session completion...
          </div>
        )}
      </div>
    </div>
  );
}
