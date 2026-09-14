/**
 * SmartWake AI — Push-up Challenge Pose Detector & Repetition State Machine
 *
 * Evaluates MoveNet skeletal landmarks to detect push-up posture and count valid repetitions.
 * Uses deterministic geometry (elbow angle, torso horizontal alignment) and a robust
 * temporal state machine: READY -> DOWN -> UP -> COOLDOWN -> READY.
 *
 * 100% deterministic, zero fabricated landmarks or decorative fake animations.
 */

export const TARGET_PUSHUPS = 5;
export const MIN_CONFIDENCE_THRESHOLD = 0.35;
export const ELBOW_ANGLE_UP = 150;
export const ELBOW_ANGLE_DOWN = 95;
export const REP_COOLDOWN_MS = 600;

/**
 * Standard MoveNet adjacent landmark pairs for drawing skeleton connections.
 */
export const SKELETON_PAIRS = [
  ['left_shoulder', 'left_elbow'],
  ['left_elbow', 'left_wrist'],
  ['right_shoulder', 'right_elbow'],
  ['right_elbow', 'right_wrist'],
  ['left_shoulder', 'right_shoulder'],
  ['left_shoulder', 'left_hip'],
  ['right_shoulder', 'right_hip'],
  ['left_hip', 'right_hip'],
  ['left_hip', 'left_knee'],
  ['left_knee', 'left_ankle'],
  ['right_hip', 'right_knee'],
  ['right_knee', 'right_ankle'],
];

/**
 * Calculates the interior angle in degrees at vertex pointB between vector BA and BC.
 *
 * @param {{ x: number, y: number }} pointA
 * @param {{ x: number, y: number }} pointB Vertex where angle is measured
 * @param {{ x: number, y: number }} pointC
 * @returns {number} Angle in degrees (0 to 180)
 */
export function calculateAngle(pointA, pointB, pointC) {
  if (!pointA || !pointB || !pointC) return 0;

  const v1x = pointA.x - pointB.x;
  const v1y = pointA.y - pointB.y;
  const v2x = pointC.x - pointB.x;
  const v2y = pointC.y - pointB.y;

  const mag1 = Math.hypot(v1x, v1y);
  const mag2 = Math.hypot(v2x, v2y);

  if (mag1 === 0 || mag2 === 0) return 0;

  const dot = v1x * v2x + v1y * v2y;
  const cosTheta = Math.max(-1, Math.min(1, dot / (mag1 * mag2)));
  return Math.round((Math.acos(cosTheta) * 180) / Math.PI);
}

/**
 * Finds a specific named landmark from an array of keypoints.
 *
 * @param {Array<{ name?: string, x: number, y: number, score?: number }>} keypoints
 * @param {string} name
 * @returns {{ name: string, x: number, y: number, score: number } | null}
 */
export function getLandmark(keypoints, name) {
  if (!Array.isArray(keypoints)) return null;
  const kp = keypoints.find((k) => k.name === name);
  if (!kp) return null;
  return {
    name: kp.name || name,
    x: kp.x,
    y: kp.y,
    score: typeof kp.score === 'number' ? kp.score : 1,
  };
}

/**
 * Evaluates MoveNet pose landmarks for push-up validity, horizontal posture, and arm flexion.
 *
 * @param {Array<{ name?: string, x: number, y: number, score?: number }>} keypoints
 * @param {Object} [options]
 * @param {number} [options.minConfidence]
 * @returns {{
 *   status: 'GREEN' | 'YELLOW' | 'RED',
 *   elbowAngle: number | null,
 *   position: 'DOWN' | 'UP' | 'TRANSITION',
 *   skeleton: Array<{ from: { name: string, x: number, y: number }, to: { name: string, x: number, y: number }, score: number }>,
 *   joints: Array<{ name: string, x: number, y: number, score: number }>,
 *   confidence: number,
 *   message: string
 * }}
 */
export function evaluatePushupPose(keypoints, options = {}) {
  const minConf = typeof options.minConfidence === 'number'
    ? options.minConfidence
    : MIN_CONFIDENCE_THRESHOLD;

  if (!Array.isArray(keypoints) || keypoints.length === 0) {
    return {
      status: 'RED',
      elbowAngle: null,
      position: 'TRANSITION',
      skeleton: [],
      joints: [],
      confidence: 0,
      message: 'Step into camera view',
    };
  }

  // 1. Extract key landmarks
  const leftShoulder = getLandmark(keypoints, 'left_shoulder');
  const rightShoulder = getLandmark(keypoints, 'right_shoulder');
  const leftElbow = getLandmark(keypoints, 'left_elbow');
  const rightElbow = getLandmark(keypoints, 'right_elbow');
  const leftWrist = getLandmark(keypoints, 'left_wrist');
  const rightWrist = getLandmark(keypoints, 'right_wrist');
  const leftHip = getLandmark(keypoints, 'left_hip');
  const rightHip = getLandmark(keypoints, 'right_hip');

  // Collect confident joints and skeleton lines
  const keypointMap = new Map();
  const joints = [];

  for (const kp of keypoints) {
    if (kp && typeof kp.score === 'number' && kp.score >= minConf && kp.name) {
      keypointMap.set(kp.name, kp);
      joints.push({
        name: kp.name,
        x: kp.x,
        y: kp.y,
        score: kp.score,
      });
    }
  }

  const skeleton = [];
  for (const [nameA, nameB] of SKELETON_PAIRS) {
    const pA = keypointMap.get(nameA);
    const pB = keypointMap.get(nameB);
    if (pA && pB) {
      skeleton.push({
        from: { name: nameA, x: pA.x, y: pA.y },
        to: { name: nameB, x: pB.x, y: pB.y },
        score: Math.min(pA.score, pB.score),
      });
    }
  }

  // 2. Validate arm confidence
  const leftArmValid =
    leftShoulder && leftShoulder.score >= minConf &&
    leftElbow && leftElbow.score >= minConf &&
    leftWrist && leftWrist.score >= minConf;

  const rightArmValid =
    rightShoulder && rightShoulder.score >= minConf &&
    rightElbow && rightElbow.score >= minConf &&
    rightWrist && rightWrist.score >= minConf;

  // Hip confidence is required to assess body posture
  const hasHip = (leftHip && leftHip.score >= minConf) || (rightHip && rightHip.score >= minConf);

  if ((!leftArmValid && !rightArmValid) || !hasHip) {
    const avgScore = joints.length > 0
      ? joints.reduce((acc, j) => acc + j.score, 0) / joints.length
      : 0;

    return {
      status: 'RED',
      elbowAngle: null,
      position: 'TRANSITION',
      skeleton,
      joints,
      confidence: Number(avgScore.toFixed(2)),
      message: 'Step into camera view',
    };
  }

  // 3. Validate horizontal posture (Reject upright / standing posture)
  // Compute torso vector between shoulders and hips
  let shoulderX = 0;
  let shoulderY = 0;
  let shoulderCount = 0;
  if (leftShoulder && leftShoulder.score >= minConf) {
    shoulderX += leftShoulder.x;
    shoulderY += leftShoulder.y;
    shoulderCount++;
  }
  if (rightShoulder && rightShoulder.score >= minConf) {
    shoulderX += rightShoulder.x;
    shoulderY += rightShoulder.y;
    shoulderCount++;
  }
  shoulderX /= shoulderCount;
  shoulderY /= shoulderCount;

  let hipX = 0;
  let hipY = 0;
  let hipCount = 0;
  if (leftHip && leftHip.score >= minConf) {
    hipX += leftHip.x;
    hipY += leftHip.y;
    hipCount++;
  }
  if (rightHip && rightHip.score >= minConf) {
    hipX += rightHip.x;
    hipY += rightHip.y;
    hipCount++;
  }
  hipX /= hipCount;
  hipY /= hipCount;

  const deltaX = Math.abs(hipX - shoulderX);
  const deltaY = Math.abs(hipY - shoulderY);

  // Torso inclination from horizontal: arctan(dy / dx) in degrees
  // In an upright posture (standing/sitting), dy is large and dx is small -> angle > 60°
  const torsoAngleFromHorizontal = (Math.atan2(deltaY, Math.max(1, deltaX)) * 180) / Math.PI;

  const totalArmConf = [];
  if (leftArmValid) {
    totalArmConf.push(leftShoulder.score, leftElbow.score, leftWrist.score);
  }
  if (rightArmValid) {
    totalArmConf.push(rightShoulder.score, rightElbow.score, rightWrist.score);
  }
  const armConfidence = totalArmConf.length > 0
    ? totalArmConf.reduce((a, b) => a + b, 0) / totalArmConf.length
    : 0;

  if (torsoAngleFromHorizontal > 60) {
    return {
      status: 'YELLOW',
      elbowAngle: null,
      position: 'TRANSITION',
      skeleton,
      joints,
      confidence: Number(armConfidence.toFixed(2)),
      message: 'Align body horizontally',
    };
  }

  // 4. Calculate elbow angles from confident arms
  let elbowAngle = null;
  if (leftArmValid && rightArmValid) {
    const leftAngle = calculateAngle(leftShoulder, leftElbow, leftWrist);
    const rightAngle = calculateAngle(rightShoulder, rightElbow, rightWrist);
    elbowAngle = Math.round((leftAngle + rightAngle) / 2);
  } else if (leftArmValid) {
    elbowAngle = calculateAngle(leftShoulder, leftElbow, leftWrist);
  } else if (rightArmValid) {
    elbowAngle = calculateAngle(rightShoulder, rightElbow, rightWrist);
  }

  // 5. Determine position based on elbow flexion
  let position = 'TRANSITION';
  if (elbowAngle !== null) {
    if (elbowAngle <= ELBOW_ANGLE_DOWN) {
      position = 'DOWN';
    } else if (elbowAngle >= ELBOW_ANGLE_UP) {
      position = 'UP';
    }
  }

  return {
    status: 'GREEN',
    elbowAngle,
    position,
    skeleton,
    joints,
    confidence: Number(armConfidence.toFixed(2)),
    message: position === 'DOWN' ? 'DOWN Position' : position === 'UP' ? 'UP Position — Push!' : 'Push-up tracking active',
  };
}

/**
 * Creates a deterministic repetition state machine for push-up tracking.
 *
 * State flow:
 * READY -> DOWN (elbow <= 95°) -> UP (elbow >= 150°) -> COOLDOWN -> READY
 *
 * A valid repetition is credited strictly on a confirmed DOWN -> UP transition.
 *
 * @param {Object} [options]
 * @param {number} [options.targetReps]
 * @param {number} [options.cooldownMs]
 */
export function createPushupStateMachine(options = {}) {
  const targetReps = typeof options.targetReps === 'number' ? options.targetReps : TARGET_PUSHUPS;
  const cooldownMs = typeof options.cooldownMs === 'number' ? options.cooldownMs : REP_COOLDOWN_MS;

  let state = 'READY'; // 'READY' | 'DOWN' | 'UP' | 'COOLDOWN'
  let reps = 0;
  let isCompleted = false;
  let cooldownStartTime = 0;
  let lastStateChangeTime = 0;

  return {
    get state() { return state; },
    get reps() { return reps; },
    get targetReps() { return targetReps; },
    get isCompleted() { return isCompleted; },
    get progress() { return Math.min(1, reps / targetReps); },

    /**
     * Processes a new frame evaluation and updates state machine transitions.
     *
     * @param {{
     *   status: 'GREEN' | 'YELLOW' | 'RED',
     *   position: 'DOWN' | 'UP' | 'TRANSITION',
     *   elbowAngle: number | null
     * }} evaluation
     * @param {number} [timestamp]
     * @returns {{
     *   state: 'READY' | 'DOWN' | 'UP' | 'COOLDOWN',
     *   reps: number,
     *   isCompleted: boolean,
     *   repIncremented: boolean
     * }}
     */
    process(evaluation, timestamp = Date.now()) {
      if (isCompleted) {
        return {
          state,
          reps,
          isCompleted: true,
          repIncremented: false,
        };
      }

      let repIncremented = false;

      // Check cooldown expiry
      if (state === 'COOLDOWN') {
        if (timestamp - cooldownStartTime >= cooldownMs) {
          state = 'READY';
          lastStateChangeTime = timestamp;
        }
      }

      // State transitions only occur under GREEN valid push-up posture
      if (evaluation && evaluation.status === 'GREEN') {
        if (state === 'READY') {
          if (evaluation.position === 'DOWN') {
            state = 'DOWN';
            lastStateChangeTime = timestamp;
          }
        } else if (state === 'DOWN') {
          if (evaluation.position === 'UP') {
            reps += 1;
            repIncremented = true;
            state = 'COOLDOWN';
            cooldownStartTime = timestamp;
            lastStateChangeTime = timestamp;

            if (reps >= targetReps) {
              isCompleted = true;
            }
          }
        }
      }

      return {
        state,
        reps,
        isCompleted,
        repIncremented,
      };
    },

    /**
     * Resets state machine to initial state.
     */
    reset() {
      state = 'READY';
      reps = 0;
      isCompleted = false;
      cooldownStartTime = 0;
      lastStateChangeTime = 0;
    },
  };
}
