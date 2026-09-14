/**
 * SmartWake AI — Dance Challenge Motion Detection Service
 *
 * Provides deterministic frame-differencing motion analysis for browser cameras.
 * Lightweight, 100% offline, zero heavy ML/WASM bundle dependencies.
 *
 * Evaluates pixel deltas between consecutive frames and accumulates verified
 * movement time towards the target active duration.
 */

export const MOTION_THRESHOLD = 12;
export const TARGET_ACTIVE_MOVEMENT_MS = 10000;
export const FRAME_WIDTH = 64;
export const FRAME_HEIGHT = 48;
export const MAX_FRAME_DELTA_MS = 100;

/**
 * Converts an ImageData (RGBA) buffer into a compact 8-bit grayscale array.
 *
 * @param {ImageData} imageData
 * @param {number} width
 * @param {number} height
 * @returns {Uint8Array}
 */
export function extractGrayscale(imageData, width = FRAME_WIDTH, height = FRAME_HEIGHT) {
  const pixelCount = width * height;
  const grayscale = new Uint8Array(pixelCount);
  const data = imageData.data;

  for (let i = 0; i < pixelCount; i++) {
    const offset = i * 4;
    // Fast integer luminance weighting: (R + 2G + B) / 4
    grayscale[i] = (data[offset] + (data[offset + 1] << 1) + data[offset + 2]) >> 2;
  }

  return grayscale;
}

/**
 * Computes the mean absolute pixel difference between two grayscale frame buffers.
 *
 * @param {Uint8Array} currentPixels
 * @param {Uint8Array} prevPixels
 * @returns {number} Mean difference score (0 to 255)
 */
export function calculateMotionScore(currentPixels, prevPixels) {
  if (!currentPixels || !prevPixels || currentPixels.length !== prevPixels.length) {
    return 0;
  }

  const length = currentPixels.length;
  if (length === 0) return 0;

  let totalDiff = 0;
  for (let i = 0; i < length; i++) {
    totalDiff += Math.abs(currentPixels[i] - prevPixels[i]);
  }

  return totalDiff / length;
}

/**
 * Creates a deterministic motion detector instance.
 *
 * @param {Object} [options]
 * @param {number} [options.threshold]
 * @param {number} [options.targetMs]
 * @param {number} [options.width]
 * @param {number} [options.height]
 * @param {number} [options.maxDeltaMs]
 */
export function createMotionDetector(options = {}) {
  const threshold = typeof options.threshold === 'number' ? options.threshold : MOTION_THRESHOLD;
  const targetMs = typeof options.targetMs === 'number' ? options.targetMs : TARGET_ACTIVE_MOVEMENT_MS;
  const width = typeof options.width === 'number' ? options.width : FRAME_WIDTH;
  const height = typeof options.height === 'number' ? options.height : FRAME_HEIGHT;
  const maxDeltaMs = typeof options.maxDeltaMs === 'number' ? options.maxDeltaMs : MAX_FRAME_DELTA_MS;

  let prevFrame = null;
  let accumulatedActiveMs = 0;
  let isCompleted = false;
  let lastMotionScore = 0;

  return {
    get threshold() { return threshold; },
    get targetMs() { return targetMs; },
    get width() { return width; },
    get height() { return height; },
    get accumulatedActiveMs() { return accumulatedActiveMs; },
    get isCompleted() { return isCompleted; },
    get lastMotionScore() { return lastMotionScore; },

    /**
     * Processes a new grayscale frame and advances accumulated movement time
     * if the motion score meets or exceeds the threshold.
     *
     * Protects against frame skips/stalls by clamping actualDeltaMs to maxDeltaMs.
     *
     * @param {Uint8Array} currentPixels
     * @param {number} actualDeltaMs Time elapsed since previous processed frame
     * @returns {{
     *   isMoving: boolean,
     *   motionScore: number,
     *   accumulatedMs: number,
     *   progress: number,
     *   isCompleted: boolean
     * }}
     */
    processFrame(currentPixels, actualDeltaMs = 0) {
      if (isCompleted) {
        return {
          isMoving: false,
          motionScore: lastMotionScore,
          accumulatedMs: accumulatedActiveMs,
          progress: 1,
          isCompleted: true,
        };
      }

      // Initial frame: register baseline, no movement credited yet
      if (!prevFrame || prevFrame.length !== currentPixels.length) {
        prevFrame = new Uint8Array(currentPixels);
        lastMotionScore = 0;
        return {
          isMoving: false,
          motionScore: 0,
          accumulatedMs: accumulatedActiveMs,
          progress: accumulatedActiveMs / targetMs,
          isCompleted: false,
        };
      }

      // Calculate pixel-differencing motion score
      const motionScore = calculateMotionScore(currentPixels, prevFrame);
      lastMotionScore = motionScore;

      // Update baseline for next frame
      prevFrame.set(currentPixels);

      // Clamp elapsed time to prevent burst credit from tab throttling or lag spikes
      const effectiveDeltaMs = Math.max(0, Math.min(actualDeltaMs, maxDeltaMs));
      const isMoving = motionScore >= threshold;

      if (isMoving && effectiveDeltaMs > 0) {
        accumulatedActiveMs = Math.min(targetMs, accumulatedActiveMs + effectiveDeltaMs);
        if (accumulatedActiveMs >= targetMs) {
          isCompleted = true;
        }
      }

      return {
        isMoving,
        motionScore,
        accumulatedMs: accumulatedActiveMs,
        progress: Math.min(1, accumulatedActiveMs / targetMs),
        isCompleted,
      };
    },

    /**
     * Resets detector state and buffers.
     */
    reset() {
      prevFrame = null;
      accumulatedActiveMs = 0;
      isCompleted = false;
      lastMotionScore = 0;
    },
  };
}
