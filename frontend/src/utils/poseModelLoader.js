/**
 * SmartWake AI — MoveNet Pose Model Loader
 *
 * Provides a resilient singleton loader for MoveNet Lightning via @tensorflow-models/pose-detection.
 * Initializes the WebGL acceleration backend safely and prevents overlapping frame inferences.
 */

import * as tf from '@tensorflow/tfjs-core';
import '@tensorflow/tfjs-backend-webgl';
import * as poseDetection from '@tensorflow-models/pose-detection';

let activeDetector = null;
let detectorPromise = null;
let isInferencing = false;

/**
 * Initializes and returns the MoveNet Lightning pose detector singleton.
 *
 * @returns {Promise<poseDetection.PoseDetector>}
 */
export async function loadPoseDetector() {
  if (activeDetector) {
    return activeDetector;
  }

  if (detectorPromise) {
    return detectorPromise;
  }

  detectorPromise = (async () => {
    try {
      // Ensure WebGL backend is initialized and ready
      await tf.ready();
      if (tf.getBackend() !== 'webgl') {
        await tf.setBackend('webgl').catch(() => {
          // Fall back to currently registered backend if WebGL fails
        });
      }

      const detector = await poseDetection.createDetector(
        poseDetection.SupportedModels.MoveNet,
        {
          modelType: poseDetection.movenet.modelType.SINGLEPOSE_LIGHTNING,
          enableSmoothing: true,
        }
      );

      activeDetector = detector;
      return detector;
    } catch (err) {
      detectorPromise = null;
      activeDetector = null;
      throw err;
    }
  })();

  return detectorPromise;
}

/**
 * Runs single-pose estimation on a live HTML5 Video element.
 * Skips execution if the video is not ready or if an inference pass is currently running.
 *
 * @param {HTMLVideoElement} videoElement
 * @returns {Promise<Array<poseDetection.Pose>>}
 */
export async function estimatePoses(videoElement) {
  if (!activeDetector || !videoElement || videoElement.readyState < 2 || isInferencing) {
    return [];
  }

  isInferencing = true;
  try {
    const poses = await activeDetector.estimatePoses(videoElement, {
      maxPoses: 1,
      flipHorizontal: false, // Mirrored via CSS scale-x-[-1]
    });
    return poses;
  } catch (err) {
    // If context was lost, log non-fatal error and return empty keypoint set
    console.warn('[poseModelLoader] Pose estimation frame error:', err);
    return [];
  } finally {
    isInferencing = false;
  }
}

/**
 * Releases the active detector and resets singleton state.
 */
export function releasePoseDetector() {
  if (activeDetector) {
    try {
      activeDetector.dispose();
    } catch {
      // Ignore disposal errors
    }
    activeDetector = null;
  }
  detectorPromise = null;
  isInferencing = false;
}
