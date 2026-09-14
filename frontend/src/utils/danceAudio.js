/**
 * SmartWake AI — Dance Challenge Music Synthesizer
 *
 * Programmatic Web Audio API music synthesizer for the Dance challenge.
 * Generates an upbeat, dynamic 124 BPM electronic dance rhythm without external audio dependencies.
 *
 * Completely isolated from the alarm audio system (alarmAudio.js).
 */

let audioCtx = null;
let masterGain = null;
let intervalId = null;
let isPlaying = false;
const activeOscillators = new Set();

/**
 * Checks whether Web Audio API is supported in the current environment.
 *
 * @returns {boolean}
 */
export function isDanceAudioSupported() {
  return typeof window !== 'undefined' && Boolean(window.AudioContext || window.webkitAudioContext);
}

/**
 * Returns whether Dance challenge music is currently playing.
 *
 * @returns {boolean}
 */
export function isDanceMusicPlaying() {
  return isPlaying;
}

/**
 * Initiates the procedural upbeat dance music loop.
 * Rhythmic 124 BPM electronic groove featuring four-on-the-floor kick,
 * crisp hi-hat accents, and syncopated melodic bass line.
 *
 * @returns {boolean} true if music started or already playing; false if unsupported
 */
export function startDanceMusic() {
  if (isPlaying) {
    return true;
  }

  if (!isDanceAudioSupported()) {
    return false;
  }

  try {
    const AudioCtxClass = window.AudioContext || window.webkitAudioContext;

    if (!audioCtx || audioCtx.state === 'closed') {
      audioCtx = new AudioCtxClass();
    }

    if (audioCtx.state === 'suspended') {
      audioCtx.resume().catch(() => {});
    }

    masterGain = audioCtx.createGain();
    masterGain.gain.setValueAtTime(0.28, audioCtx.currentTime);
    masterGain.connect(audioCtx.destination);

    isPlaying = true;

    // 124 BPM timing: 1 beat = 60/124 ≈ 0.4838s, 16th step ≈ 0.121s
    const stepDuration = 60 / 124 / 4;
    let currentStep = 0;

    // Pentatonic energetic bass line notes (Hz)
    const bassNotes = [110, 110, 130.81, 146.83, 110, 164.81, 146.83, 130.81];

    const playStep = () => {
      if (!isPlaying || !audioCtx || audioCtx.state === 'closed') {
        return;
      }

      try {
        if (audioCtx.state === 'suspended') {
          audioCtx.resume().catch(() => {});
        }

        const now = audioCtx.currentTime;
        const step16 = currentStep % 16;
        currentStep++;

        // 1. Four-on-the-floor Kick Drum (steps 0, 4, 8, 12)
        if (step16 % 4 === 0) {
          const kickOsc = audioCtx.createOscillator();
          const kickGain = audioCtx.createGain();

          kickOsc.type = 'sine';
          kickOsc.frequency.setValueAtTime(140, now);
          kickOsc.frequency.exponentialRampToValueAtTime(38, now + 0.11);

          kickGain.gain.setValueAtTime(0.7, now);
          kickGain.gain.exponentialRampToValueAtTime(0.001, now + 0.14);

          kickOsc.connect(kickGain);
          kickGain.connect(masterGain);

          kickOsc.start(now);
          kickOsc.stop(now + 0.15);

          activeOscillators.add(kickOsc);
          kickOsc.onended = () => {
            activeOscillators.delete(kickOsc);
            try { kickOsc.disconnect(); } catch {}
            try { kickGain.disconnect(); } catch {}
          };
        }

        // 2. Off-beat Crisp Hi-Hat (steps 2, 6, 10, 14)
        if (step16 % 4 === 2) {
          const hatOsc = audioCtx.createOscillator();
          const hatGain = audioCtx.createGain();

          // High metallic ring using high-frequency triangle wave
          hatOsc.type = 'triangle';
          hatOsc.frequency.setValueAtTime(8500, now);

          hatGain.gain.setValueAtTime(0.18, now);
          hatGain.gain.exponentialRampToValueAtTime(0.001, now + 0.05);

          hatOsc.connect(hatGain);
          hatGain.connect(masterGain);

          hatOsc.start(now);
          hatOsc.stop(now + 0.06);

          activeOscillators.add(hatOsc);
          hatOsc.onended = () => {
            activeOscillators.delete(hatOsc);
            try { hatOsc.disconnect(); } catch {}
            try { hatGain.disconnect(); } catch {}
          };
        }

        // 3. Melodic Synth Bass (syncopated steps: 0, 3, 6, 8, 10, 12, 14)
        const bassTriggerSteps = [0, 3, 6, 8, 10, 12, 14];
        if (bassTriggerSteps.includes(step16)) {
          const bassOsc = audioCtx.createOscillator();
          const bassGain = audioCtx.createGain();

          const noteIndex = (Math.floor(currentStep / 2)) % bassNotes.length;
          const freq = bassNotes[noteIndex];

          bassOsc.type = 'sawtooth';
          bassOsc.frequency.setValueAtTime(freq, now);

          bassGain.gain.setValueAtTime(0.22, now);
          bassGain.gain.linearRampToValueAtTime(0.18, now + 0.02);
          bassGain.gain.exponentialRampToValueAtTime(0.001, now + stepDuration * 1.5);

          bassOsc.connect(bassGain);
          bassGain.connect(masterGain);

          bassOsc.start(now);
          bassOsc.stop(now + stepDuration * 1.6);

          activeOscillators.add(bassOsc);
          bassOsc.onended = () => {
            activeOscillators.delete(bassOsc);
            try { bassOsc.disconnect(); } catch {}
            try { bassGain.disconnect(); } catch {}
          };
        }
      } catch {
        // Silently capture scheduling errors
      }
    };

    playStep();
    intervalId = setInterval(playStep, stepDuration * 1000);

    return true;
  } catch {
    isPlaying = false;
    return false;
  }
}

/**
 * Safely stops Dance challenge music, clears intervals,
 * and releases active Web Audio nodes.
 *
 * @returns {boolean} true on completion.
 */
export function stopDanceMusic() {
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
      // Ignore individual cleanup errors
    }
  }
  activeOscillators.clear();

  if (masterGain) {
    try {
      masterGain.disconnect();
    } catch {
      // Ignore disconnect errors
    }
    masterGain = null;
  }

  if (audioCtx && audioCtx.state === 'running') {
    try {
      audioCtx.suspend().catch(() => {});
    } catch {
      // Ignore suspend errors
    }
  }

  return true;
}
