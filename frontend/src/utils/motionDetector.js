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
export const LOW_MOTION_THRESHOLD = 4;
export const TARGET_ACTIVE_MOVEMENT_MS = 10000;
export const FRAME_WIDTH = 64;
export const FRAME_HEIGHT = 48;
export const MAX_FRAME_DELTA_MS = 100;
export const GRID_COLS = 16;
export const GRID_ROWS = 12;

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
     *   movementStatus: 'active' | 'low' | 'idle',
     *   motionRegions: Array<{ x: number, y: number, width: number, height: number, intensity: number }>,
     *   motionBounds: { x: number, y: number, width: number, height: number } | null,
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
          movementStatus: 'idle',
          motionRegions: [],
          motionBounds: null,
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
          movementStatus: 'idle',
          motionRegions: [],
          motionBounds: null,
          accumulatedMs: accumulatedActiveMs,
          progress: accumulatedActiveMs / targetMs,
          isCompleted: false,
        };
      }

      // Calculate pixel-differencing motion score & cell deltas across 16x12 grid
      const length = currentPixels.length;
      let totalDiff = 0;
      const cellW = Math.max(1, Math.floor(width / GRID_COLS));
      const cellH = Math.max(1, Math.floor(height / GRID_ROWS));
      const pixelsPerCell = cellW * cellH;
      const cellDiffs = new Uint32Array(GRID_COLS * GRID_ROWS);

      for (let i = 0; i < length; i++) {
        const diff = Math.abs(currentPixels[i] - prevFrame[i]);
        totalDiff += diff;

        const px = i % width;
        const py = (i / width) | 0;
        const col = Math.min(GRID_COLS - 1, (px / cellW) | 0);
        const row = Math.min(GRID_ROWS - 1, (py / cellH) | 0);
        cellDiffs[row * GRID_COLS + col] += diff;
      }

      const motionScore = totalDiff / length;
      lastMotionScore = motionScore;

      // Update baseline for next frame
      prevFrame.set(currentPixels);

      // Clamp elapsed time to prevent burst credit from tab throttling or lag spikes
      const effectiveDeltaMs = Math.max(0, Math.min(actualDeltaMs, maxDeltaMs));
      const isMoving = motionScore >= threshold;

      // Determine movement status
      let movementStatus = 'idle';
      if (isMoving) {
        movementStatus = 'active';
      } else if (motionScore >= LOW_MOTION_THRESHOLD) {
        movementStatus = 'low';
      } else {
        movementStatus = 'idle';
      }

      // Calculate motion regions and bounds strictly from actual frame difference
      const motionRegions = [];
      let motionBounds = null;

      if (movementStatus === 'active') {
        let minCol = GRID_COLS;
        let maxCol = -1;
        let minRow = GRID_ROWS;
        let maxRow = -1;

        for (let r = 0; r < GRID_ROWS; r++) {
          for (let c = 0; c < GRID_COLS; c++) {
            const cellMean = cellDiffs[r * GRID_COLS + c] / pixelsPerCell;
            if (cellMean >= threshold) {
              motionRegions.push({
                x: c / GRID_COLS,
                y: r / GRID_ROWS,
                width: 1 / GRID_COLS,
                height: 1 / GRID_ROWS,
                intensity: Math.min(1, cellMean / 60),
              });
              if (c < minCol) minCol = c;
              if (c > maxCol) maxCol = c;
              if (r < minRow) minRow = r;
              if (r > maxRow) maxRow = r;
            }
          }
        }

        // Safeguard: if overall motionScore >= threshold but individual cells were slightly below threshold,
        // ensure active cells are captured using proportional cell threshold
        if (motionRegions.length === 0) {
          const activeCellThreshold = Math.max(LOW_MOTION_THRESHOLD, threshold * 0.75);
          for (let r = 0; r < GRID_ROWS; r++) {
            for (let c = 0; c < GRID_COLS; c++) {
              const cellMean = cellDiffs[r * GRID_COLS + c] / pixelsPerCell;
              if (cellMean >= activeCellThreshold) {
                motionRegions.push({
                  x: c / GRID_COLS,
                  y: r / GRID_ROWS,
                  width: 1 / GRID_COLS,
                  height: 1 / GRID_ROWS,
                  intensity: Math.min(1, cellMean / 60),
                });
                if (c < minCol) minCol = c;
                if (c > maxCol) maxCol = c;
                if (r < minRow) minRow = r;
                if (r > maxRow) maxRow = r;
              }
            }
          }
        }

        if (motionRegions.length > 0) {
          motionBounds = {
            x: minCol / GRID_COLS,
            y: minRow / GRID_ROWS,
            width: (maxCol - minCol + 1) / GRID_COLS,
            height: (maxRow - minRow + 1) / GRID_ROWS,
          };
        }
      } else if (movementStatus === 'low') {
        for (let r = 0; r < GRID_ROWS; r++) {
          for (let c = 0; c < GRID_COLS; c++) {
            const cellMean = cellDiffs[r * GRID_COLS + c] / pixelsPerCell;
            if (cellMean >= LOW_MOTION_THRESHOLD) {
              motionRegions.push({
                x: c / GRID_COLS,
                y: r / GRID_ROWS,
                width: 1 / GRID_COLS,
                height: 1 / GRID_ROWS,
                intensity: Math.min(1, cellMean / 60),
              });
            }
          }
        }
        // For 'low' movement status, motionBounds remains null as per spec (no fake bounding box)
        motionBounds = null;
      }

      if (isMoving && effectiveDeltaMs > 0) {
        accumulatedActiveMs = Math.min(targetMs, accumulatedActiveMs + effectiveDeltaMs);
        if (accumulatedActiveMs >= targetMs) {
          isCompleted = true;
        }
      }

      return {
        isMoving,
        motionScore,
        movementStatus,
        motionRegions,
        motionBounds,
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
