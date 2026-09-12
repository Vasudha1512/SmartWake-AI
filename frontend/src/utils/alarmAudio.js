/**
 * SmartWake AI — Alarm Audio Service
 *
 * Programmatic Web Audio API synthesizer for alarm tone generation.
 * Generates rhythmic dual-tone alert patterns without external audio assets.
 */

let audioCtx = null;
let masterGain = null;
let intervalId = null;
let isPlaying = false;
const activeOscillators = new Set();

/**
 * Checks whether the Web Audio API is supported in the current environment.
 *
 * @returns {boolean}
 */
export function isAudioSupported() {
  return typeof window !== 'undefined' && Boolean(window.AudioContext || window.webkitAudioContext);
}

/**
 * Returns whether alarm audio is currently playing.
 *
 * @returns {boolean}
 */
export function isAlarmSoundPlaying() {
  return isPlaying;
}

/**
 * Initiates the alarm tone playback.
 * Idempotent: repeated calls will not spawn duplicate sounds or intervals.
 * Gracefully handles autoplay restrictions and suspended contexts.
 *
 * @returns {boolean} true if audio was initiated or already playing; false if unsupported or failed.
 */
export function startAlarmSound() {
  if (isPlaying) {
    return true;
  }

  if (!isAudioSupported()) {
    return false;
  }

  try {
    const AudioCtxClass = window.AudioContext || window.webkitAudioContext;

    if (!audioCtx || audioCtx.state === 'closed') {
      audioCtx = new AudioCtxClass();
    }

    // Attempt to resume context if suspended by browser autoplay policy
    if (audioCtx.state === 'suspended') {
      audioCtx.resume().catch(() => {
        // Autoplay policy may reject until user gesture occurs.
      });
    }

    masterGain = audioCtx.createGain();
    masterGain.gain.setValueAtTime(0.3, audioCtx.currentTime);
    masterGain.connect(audioCtx.destination);

    isPlaying = true;

    const playPulse = () => {
      if (!isPlaying || !audioCtx || audioCtx.state === 'closed') {
        return;
      }

      try {
        if (audioCtx.state === 'suspended') {
          audioCtx.resume().catch(() => {});
        }

        const now = audioCtx.currentTime;

        // Double-beep sequence: 880 Hz (A5) then 1046.5 Hz (C6)
        const beeps = [
          { freq: 880, offset: 0, duration: 0.16 },
          { freq: 1046.5, offset: 0.2, duration: 0.16 },
        ];

        beeps.forEach(({ freq, offset, duration }) => {
          const osc = audioCtx.createOscillator();
          const noteGain = audioCtx.createGain();

          osc.type = 'sine';
          osc.frequency.setValueAtTime(freq, now + offset);

          // Fast attack and exponential decay to prevent clicks/pops
          noteGain.gain.setValueAtTime(0.001, now + offset);
          noteGain.gain.linearRampToValueAtTime(0.35, now + offset + 0.02);
          noteGain.gain.exponentialRampToValueAtTime(0.001, now + offset + duration);

          osc.connect(noteGain);
          noteGain.connect(masterGain);

          osc.start(now + offset);
          osc.stop(now + offset + duration + 0.02);

          activeOscillators.add(osc);

          osc.onended = () => {
            activeOscillators.delete(osc);
            try {
              osc.disconnect();
            } catch {
              // Ignore already disconnected nodes
            }
            try {
              noteGain.disconnect();
            } catch {
              // Ignore already disconnected nodes
            }
          };
        });
      } catch {
        // Silently capture any scheduled node exceptions
      }
    };

    // Play first pulse immediately, then repeat every 850ms
    playPulse();
    intervalId = setInterval(playPulse, 850);

    return true;
  } catch {
    isPlaying = false;
    return false;
  }
}

/**
 * Safely stops all active oscillators, cleans up gain nodes,
 * clears intervals, and resets playback state while keeping
 * the AudioContext instance reusable for future alarm cycles.
 *
 * @returns {boolean} true on completion.
 */
export function stopAlarmSound() {
  isPlaying = false;

  if (intervalId) {
    clearInterval(intervalId);
    intervalId = null;
  }

  for (const osc of activeOscillators) {
    try {
      osc.stop();
      osc.disconnect();
    } catch {
      // Ignore cleanup errors on individual nodes
    }
  }
  activeOscillators.clear();

  if (masterGain) {
    try {
      masterGain.disconnect();
    } catch {
      // Ignore disconnect error
    }
    masterGain = null;
  }

  // Suspend context to pause hardware/CPU utilization while preserving
  // the user-gesture unlocked state for subsequent alarm cycles.
  if (audioCtx && audioCtx.state === 'running') {
    try {
      audioCtx.suspend().catch(() => {});
    } catch {
      // Ignore suspend error
    }
  }

  return true;
}

