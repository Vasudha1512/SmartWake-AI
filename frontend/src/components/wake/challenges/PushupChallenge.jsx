import React, { useState, useEffect, useRef, useCallback } from 'react';
import {
  TARGET_PUSHUPS,
  MIN_CONFIDENCE_THRESHOLD,
  evaluatePushupPose,
  createPushupStateMachine,
} from '../../../utils/pushupDetector';
import {
  loadPoseDetector,
  estimatePoses,
  releasePoseDetector,
} from '../../../utils/poseModelLoader';

/**
 * PushupChallenge component
 * SmartWake AI physical movement challenge powered by MoveNet computer-vision pose detection.
 *
 * Tracks user skeletal landmarks in real time through the device webcam.
 * Visualizes detected body joints on an aligned transparent canvas overlay
 * and counts valid push-ups via a strict deterministic state machine:
 * READY -> DOWN (elbow <= 95°) -> UP (elbow >= 150°) -> COOLDOWN -> READY.
 *
 * @param {{
 *   onComplete: () => void,
 *   onFail?: () => void
 * }} props
 */
export default function PushupChallenge({ onComplete, onFail }) {
  // 'ready' | 'starting' | 'active' | 'completed' | 'error'
  const [challengeState, setChallengeState] = useState('ready');
  const [errorMessage, setErrorMessage] = useState(null);
  const [reps, setReps] = useState(0);
  const [poseStatus, setPoseStatus] = useState('RED');
  const [stateMachineState, setStateMachineState] = useState('READY');
  const [elbowAngle, setElbowAngle] = useState(null);
  const [guidanceMessage, setGuidanceMessage] = useState('Step into camera view');

  const videoRef = useRef(null);
  const overlayCanvasRef = useRef(null);
  const mediaStreamRef = useRef(null);
  const animationFrameRef = useRef(null);
  const stateMachineRef = useRef(null);
  const hasCompletedRef = useRef(false);

  /**
   * Safely releases all camera tracks, animation loops, model memory,
   * and clears the overlay canvas.
   */
  const stopAllResources = useCallback(() => {
    // 1. Cancel requestAnimationFrame loop
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

    // 4. Clear overlay canvas
    if (overlayCanvasRef.current) {
      try {
        const ctx = overlayCanvasRef.current.getContext('2d');
        if (ctx) {
          ctx.clearRect(
            0,
            0,
            overlayCanvasRef.current.width,
            overlayCanvasRef.current.height
          );
        }
      } catch {
        // Ignore canvas clear errors
      }
    }

    // 5. Reset state machine
    if (stateMachineRef.current) {
      stateMachineRef.current.reset();
    }
  }, []);

  // Guarantee clean teardown when component unmounts
  useEffect(() => {
    return () => {
      stopAllResources();
      releasePoseDetector();
    };
  }, [stopAllResources]);

  /**
   * Challenge success sequence.
   * Invokes the authoritative wake session completion callback exactly once.
   */
  const handleSuccess = useCallback(() => {
    stopAllResources();
    setChallengeState('completed');

    if (typeof onComplete === 'function') {
      onComplete();
    }
  }, [onComplete, stopAllResources]);

  /**
   * Pose estimation and skeleton rendering animation loop.
   */
  const startPoseTrackingLoop = useCallback(() => {
    const loop = async () => {
      const video = videoRef.current;
      const overlay = overlayCanvasRef.current;
      const stateMachine = stateMachineRef.current;

      if (!video || !stateMachine || hasCompletedRef.current) {
        return;
      }

      if (video.readyState >= 2 && video.videoWidth > 0 && video.videoHeight > 0) {
        // Keep overlay canvas coordinate dimensions matching video feed
        if (overlay) {
          if (overlay.width !== video.videoWidth || overlay.height !== video.videoHeight) {
            overlay.width = video.videoWidth;
            overlay.height = video.videoHeight;
          }
        }

        try {
          // Perform real MoveNet pose estimation
          const poses = await estimatePoses(video);
          const keypoints = poses && poses.length > 0 ? poses[0].keypoints : [];

          // Evaluate skeletal geometry
          const evaluation = evaluatePushupPose(keypoints, {
            minConfidence: MIN_CONFIDENCE_THRESHOLD,
          });

          // Process state machine transitions
          const result = stateMachine.process(evaluation, performance.now());

          setReps(result.reps);
          setStateMachineState(result.state);
          setPoseStatus(evaluation.status);
          setElbowAngle(evaluation.elbowAngle);
          setGuidanceMessage(evaluation.message);

          // Render real skeletal landmarks on canvas overlay
          if (overlay) {
            const ctx = overlay.getContext('2d');
            if (ctx) {
              ctx.clearRect(0, 0, overlay.width, overlay.height);

              if (evaluation.status === 'GREEN' || evaluation.status === 'YELLOW') {
                const isGreen = evaluation.status === 'GREEN';
                const jointColor = isGreen ? '#22c55e' : '#eab308';
                const lineColor = isGreen ? 'rgba(34, 197, 94, 0.85)' : 'rgba(234, 179, 8, 0.85)';

                // 1. Draw real skeleton connecting lines
                ctx.strokeStyle = lineColor;
                ctx.lineWidth = 3;
                ctx.lineCap = 'round';

                for (const segment of evaluation.skeleton) {
                  ctx.beginPath();
                  ctx.moveTo(segment.from.x, segment.from.y);
                  ctx.lineTo(segment.to.x, segment.to.y);
                  ctx.stroke();
                }

                // 2. Draw real landmark joint points
                for (const joint of evaluation.joints) {
                  ctx.beginPath();
                  ctx.arc(joint.x, joint.y, 5, 0, 2 * Math.PI);
                  ctx.fillStyle = jointColor;
                  ctx.fill();

                  ctx.beginPath();
                  ctx.arc(joint.x, joint.y, 8, 0, 2 * Math.PI);
                  ctx.strokeStyle = jointColor;
                  ctx.lineWidth = 1.5;
                  ctx.stroke();
                }
              }
              // In RED state: clearRect leaves the canvas completely transparent.
            }
          }

          // Check completion
          if (result.isCompleted && !hasCompletedRef.current) {
            hasCompletedRef.current = true;
            handleSuccess();
            return;
          }
        } catch (err) {
          console.warn('[PushupChallenge] Frame processing error:', err);
        }
      }

      animationFrameRef.current = requestAnimationFrame(loop);
    };

    animationFrameRef.current = requestAnimationFrame(loop);
  }, [handleSuccess]);

  /**
   * Initializes camera access, loads MoveNet model, and starts the tracking loop.
   */
  const handleStartChallenge = async () => {
    stopAllResources();
    setChallengeState('starting');
    setErrorMessage(null);
    setReps(0);
    setPoseStatus('RED');
    setStateMachineState('READY');
    setElbowAngle(null);
    setGuidanceMessage('Loading MoveNet pose model...');
    hasCompletedRef.current = false;

    // Initialize state machine
    stateMachineRef.current = createPushupStateMachine({
      targetReps: TARGET_PUSHUPS,
    });

    try {
      if (!navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
        throw new Error('Camera access is not supported by your browser.');
      }

      // 1. Preload MoveNet pose detector
      await loadPoseDetector();

      // 2. Request user camera access
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

      setChallengeState('active');
      setGuidanceMessage('Step into camera view');
      startPoseTrackingLoop();
    } catch (err) {
      stopAllResources();
      setChallengeState('error');

      if (err.name === 'NotAllowedError' || err.name === 'PermissionDeniedError') {
        setErrorMessage(
          'Camera access was denied. Please grant camera permission in your browser address bar to perform the Push-up challenge.'
        );
      } else if (err.name === 'NotFoundError' || err.name === 'DevicesNotFoundError') {
        setErrorMessage(
          'No camera was found on this device. Please connect a webcam or enable camera hardware.'
        );
      } else {
        setErrorMessage(
          err.message || 'Could not initialize camera or pose detection model. Please try again.'
        );
      }
    }
  };

  /**
   * Resets challenge to ready state.
   */
  const handleReset = () => {
    stopAllResources();
    setChallengeState('ready');
    setReps(0);
    setPoseStatus('RED');
    setStateMachineState('READY');
    setElbowAngle(null);
    setGuidanceMessage('Step into camera view');
    setErrorMessage(null);
    hasCompletedRef.current = false;
  };

  const progressPercent = Math.min(100, Math.round((reps / TARGET_PUSHUPS) * 100));

  return (
    <div className="space-y-6 text-center max-w-lg mx-auto">
      {/* 1. Header & Instructions */}
      <div className="space-y-1">
        <div className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-amber-50 text-amber-700 border border-amber-200">
          <span>💪 Push-ups Physical Challenge</span>
        </div>
        <h3 className="text-xl font-bold text-slate-900 tracking-tight">
          Complete {TARGET_PUSHUPS} Push-ups
        </h3>
        <p className="text-xs text-slate-600 max-w-md mx-auto">
          Position your body horizontally in camera view and perform 5 full repetitions (chest down, arms push up).
        </p>
      </div>

      {/* 2. Main Viewport Area */}
      <div className="relative aspect-video max-w-md mx-auto rounded-2xl bg-slate-900 border-2 border-amber-200 overflow-hidden shadow-md flex items-center justify-center">
        {/* State A: Live Video Feed */}
        <video
          ref={videoRef}
          playsInline
          muted
          autoPlay
          className={`w-full h-full object-cover transform scale-x-[-1] ${
            challengeState === 'active' ? 'block' : 'hidden'
          }`}
          aria-label="Live camera feed for pushup tracking"
        />

        {/* Live Real Computer-Vision Skeleton Canvas Overlay */}
        <canvas
          ref={overlayCanvasRef}
          className={`absolute inset-0 w-full h-full object-cover transform scale-x-[-1] pointer-events-none ${
            challengeState === 'active' ? 'block' : 'hidden'
          }`}
          aria-hidden="true"
        />

        {/* Live HUD Overlays (when active) */}
        {challengeState === 'active' && (
          <div className="absolute inset-0 pointer-events-none flex flex-col justify-between p-3.5 bg-gradient-to-b from-black/40 via-transparent to-black/60">
            {/* Top Status Bar: Pose detection status & Rep Target */}
            <div className="flex items-center justify-between gap-2">
              <div
                role="status"
                aria-live="polite"
                className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-[11px] font-bold shadow-xs backdrop-blur-xs transition-colors ${
                  poseStatus === 'GREEN'
                    ? 'bg-emerald-600/90 text-white border border-emerald-400/40'
                    : poseStatus === 'YELLOW'
                    ? 'bg-amber-500/90 text-slate-950 border border-amber-300/40'
                    : 'bg-rose-600/80 text-white border border-rose-400/40'
                }`}
              >
                <span
                  className={`w-2 h-2 rounded-full ${
                    poseStatus === 'GREEN'
                      ? 'bg-white animate-ping'
                      : poseStatus === 'YELLOW'
                      ? 'bg-slate-950'
                      : 'bg-white'
                  }`}
                />
                <span>
                  {poseStatus === 'GREEN'
                    ? 'Pose Detected'
                    : poseStatus === 'YELLOW'
                    ? 'Adjust Alignment'
                    : 'No Pose Detected'}
                </span>
              </div>

              {/* Rep Count Pill */}
              <span
                role="timer"
                aria-live="polite"
                className="px-3 py-1 rounded-full text-xs font-mono font-extrabold bg-black/60 text-amber-300 backdrop-blur-xs border border-white/20 shadow-xs"
              >
                Reps: {reps} / {TARGET_PUSHUPS}
              </span>
            </div>

            {/* Bottom Status Bar: State & Guidance */}
            <div className="space-y-1.5">
              <div className="flex items-center justify-between text-xs">
                {/* Movement Position Pill */}
                <div
                  className={`inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-md font-mono font-bold text-[11px] ${
                    stateMachineState === 'DOWN'
                      ? 'bg-emerald-500 text-white'
                      : stateMachineState === 'COOLDOWN'
                      ? 'bg-purple-600 text-white'
                      : 'bg-black/60 text-slate-200 border border-white/10'
                  }`}
                >
                  <span>Position: {stateMachineState}</span>
                </div>

                {/* Elbow Angle */}
                {elbowAngle !== null && (
                  <span className="text-[11px] font-mono text-white/90 bg-black/50 px-2 py-0.5 rounded backdrop-blur-xs">
                    Elbow: {elbowAngle}°
                  </span>
                )}
              </div>

              {/* Guidance Message Banner */}
              <div className="text-left text-[11px] text-white/90 bg-black/40 px-2.5 py-1 rounded backdrop-blur-xs font-medium">
                {guidanceMessage}
              </div>
            </div>
          </div>
        )}

        {/* State B: Ready / Start Placeholder */}
        {challengeState === 'ready' && (
          <div className="p-6 text-center space-y-3">
            <div className="w-16 h-16 rounded-2xl bg-amber-100 text-amber-700 border border-amber-200 flex items-center justify-center text-3xl mx-auto shadow-2xs">
              💪
            </div>
            <div className="space-y-1">
              <p className="text-sm font-bold text-white">MoveNet Pose Tracking Ready</p>
              <p className="text-xs text-slate-300 max-w-xs mx-auto">
                Press start below to activate real-time skeletal tracking and rep counting.
              </p>
            </div>
          </div>
        )}

        {/* State C: Starting / Loading Model */}
        {challengeState === 'starting' && (
          <div className="p-6 text-center space-y-3">
            <div className="w-12 h-12 rounded-full border-3 border-amber-400 border-t-transparent animate-spin mx-auto" />
            <p className="text-sm font-semibold text-white">
              Connecting camera &amp; initializing MoveNet...
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
            <p className="text-base font-bold text-white">Push-up Challenge Complete!</p>
            <p className="text-xs text-emerald-400">
              Verified {TARGET_PUSHUPS} valid push-up repetitions.
            </p>
          </div>
        )}

        {/* State E: Error Display in Viewport */}
        {challengeState === 'error' && (
          <div className="p-5 text-center space-y-2 max-w-xs">
            <div className="w-12 h-12 rounded-xl bg-rose-500/20 text-rose-400 border border-rose-500/30 flex items-center justify-center text-xl mx-auto">
              ⚠️
            </div>
            <p className="text-xs font-bold text-rose-300">Camera / Model Notice</p>
            <p className="text-[11px] text-slate-300 leading-relaxed">
              {errorMessage || 'Unable to open camera.'}
            </p>
          </div>
        )}
      </div>

      {/* 3. Progress Tracking Bar */}
      {(challengeState === 'active' || challengeState === 'starting' || challengeState === 'completed') && (
        <div className="space-y-2 bg-slate-50 border border-slate-200 p-4 rounded-xl text-left shadow-2xs">
          <div className="flex items-center justify-between text-xs font-semibold">
            <span className="text-slate-700">Push-up Repetition Progress</span>
            <span className="font-mono text-amber-700">
              {reps} / {TARGET_PUSHUPS} reps ({progressPercent}%)
            </span>
          </div>

          <div
            className="h-3 w-full bg-slate-200 rounded-full overflow-hidden shadow-inner"
            role="progressbar"
            aria-valuenow={progressPercent}
            aria-valuemin="0"
            aria-valuemax="100"
            aria-label="Push-up repetition progress"
          >
            <div
              className="h-full bg-gradient-to-r from-amber-500 to-orange-600 transition-all duration-200 rounded-full"
              style={{ width: `${progressPercent}%` }}
            />
          </div>

          <div className="flex items-center justify-between text-[11px] text-slate-500 pt-0.5">
            <span>Deterministic rule: 5 valid DOWN → UP cycles</span>
            <span
              className={
                poseStatus === 'GREEN'
                  ? 'text-emerald-600 font-bold'
                  : 'text-slate-500'
              }
            >
              {poseStatus === 'GREEN'
                ? '● Ready for push-ups'
                : '○ Step into camera view'}
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
              <span className="font-bold block">Camera / Tracking Notice</span>
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
              className="px-3 py-2 rounded-lg text-xs font-medium text-slate-600 hover:text-slate-900 bg-white border border-slate-200 transition-colors cursor-pointer"
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
            className="w-full sm:w-auto inline-flex items-center justify-center px-8 py-3.5 rounded-xl text-sm font-bold text-white bg-amber-600 hover:bg-amber-700 shadow-md shadow-amber-600/20 transition-all cursor-pointer focus:outline-none focus:ring-2 focus:ring-amber-500"
          >
            <svg className="w-5 h-5 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 10l4.553-2.276A1 1 0 0121 8.618v6.764a1 1 0 01-1.447.894L15 14M5 18h8a2 2 0 002-2V8a2 2 0 00-2-2H5a2 2 0 00-2 2v8a2 2 0 002 2z" />
            </svg>
            <span>Start Push-up Challenge</span>
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
