/**
 * SmartWake AI — Deterministic Speech Verification Utility
 *
 * Provides offline, deterministic text normalization and bounded dual-layer similarity
 * scoring (word-level token edit distance + character-level Levenshtein distance).
 *
 * Speech verification is performed locally using deterministic text comparison
 * without an LLM or external verification service. Browser speech recognition
 * availability and processing depend on the browser/platform.
 */

export const SPEECH_MATCH_THRESHOLD = 0.85;

export const DEFAULT_TONGUE_TWISTER =
  'Peter Piper picked a peck of pickled peppers, but the peck of pickled peppers Peter Piper picked was not enough.';

/**
 * Normalizes speech text by converting to lowercase, stripping punctuation,
 * preserving alphanumeric tokens, and collapsing whitespace.
 *
 * @param {string} text
 * @returns {string}
 */
export function normalizeSpeechText(text) {
  if (typeof text !== 'string') {
    return '';
  }

  return text
    .toLowerCase()
    .replace(/[^a-z0-9\s]/g, ' ')
    .replace(/\s+/g, ' ')
    .trim();
}

/**
 * Computes Levenshtein distance between two arrays of items (characters or tokens).
 * Uses two-row memory-efficient dynamic programming.
 *
 * @param {Array<string>} a
 * @param {Array<string>} b
 * @returns {number}
 */
export function levenshteinDistance(a, b) {
  const lenA = a.length;
  const lenB = b.length;

  if (lenA === 0) return lenB;
  if (lenB === 0) return lenA;

  let prevRow = new Array(lenB + 1);
  let currRow = new Array(lenB + 1);

  for (let j = 0; j <= lenB; j++) {
    prevRow[j] = j;
  }

  for (let i = 1; i <= lenA; i++) {
    currRow[0] = i;
    const itemA = a[i - 1];

    for (let j = 1; j <= lenB; j++) {
      const itemB = b[j - 1];
      const cost = itemA === itemB ? 0 : 1;

      currRow[j] = Math.min(
        currRow[j - 1] + 1,      // insertion
        prevRow[j] + 1,          // deletion
        prevRow[j - 1] + cost    // substitution
      );
    }

    const temp = prevRow;
    prevRow = currRow;
    currRow = temp;
  }

  return prevRow[lenB];
}

/**
 * Computes bounded word-level token similarity in range [0, 1].
 *
 * @param {string[]} wordsA
 * @param {string[]} wordsB
 * @returns {number}
 */
export function calculateWordSimilarity(wordsA, wordsB) {
  if (wordsA.length === 0 && wordsB.length === 0) return 1;
  if (wordsA.length === 0 || wordsB.length === 0) return 0;

  const dist = levenshteinDistance(wordsA, wordsB);
  const maxLen = Math.max(wordsA.length, wordsB.length);

  return Math.max(0, Math.min(1, (maxLen - dist) / maxLen));
}

/**
 * Computes bounded character-level similarity in range [0, 1].
 *
 * @param {string} strA
 * @param {string} strB
 * @returns {number}
 */
export function calculateCharSimilarity(strA, strB) {
  if (strA.length === 0 && strB.length === 0) return 1;
  if (strA.length === 0 || strB.length === 0) return 0;

  const dist = levenshteinDistance(strA.split(''), strB.split(''));
  const maxLen = Math.max(strA.length, strB.length);

  return Math.max(0, Math.min(1, (maxLen - dist) / maxLen));
}

/**
 * Calculates a composite bounded similarity score between transcript and target.
 * Combines 60% word-token sequence alignment and 40% character edit distance.
 *
 * Strictly penalizes partial, truncated, or prefix-only inputs.
 *
 * @param {string} transcript
 * @param {string} target
 * @returns {number} Similarity score strictly in range [0, 1]
 */
export function calculateSimilarity(transcript, target) {
  const normTranscript = normalizeSpeechText(transcript);
  const normTarget = normalizeSpeechText(target);

  if (!normTranscript || !normTarget) {
    return 0;
  }

  const wordsTranscript = normTranscript.split(' ').filter(Boolean);
  const wordsTarget = normTarget.split(' ').filter(Boolean);

  const wordSim = calculateWordSimilarity(wordsTranscript, wordsTarget);
  const charSim = calculateCharSimilarity(normTranscript, normTarget);

  const composite = wordSim * 0.6 + charSim * 0.4;
  const bounded = Math.max(0, Math.min(1, composite));

  return Number(bounded.toFixed(4));
}

/**
 * Verifies recognized speech transcript against the expected target tongue twister.
 *
 * @param {string} transcript Recognized final transcript
 * @param {string} [targetPhrase] Expected tongue twister
 * @param {number} [threshold] Required match threshold (default: SPEECH_MATCH_THRESHOLD = 0.85)
 * @returns {{
 *   matched: boolean,
 *   score: number,
 *   target: string,
 *   transcript: string,
 *   normalizedTarget: string,
 *   normalizedTranscript: string,
 *   threshold: number
 * }}
 */
export function verifySpeech(
  transcript,
  targetPhrase = DEFAULT_TONGUE_TWISTER,
  threshold = SPEECH_MATCH_THRESHOLD
) {
  const normTarget = normalizeSpeechText(targetPhrase);
  const normTranscript = normalizeSpeechText(transcript);

  if (!normTranscript || !normTarget) {
    return {
      matched: false,
      score: 0,
      target: targetPhrase,
      transcript: typeof transcript === 'string' ? transcript : '',
      normalizedTarget: normTarget,
      normalizedTranscript: normTranscript,
      threshold,
    };
  }

  const score = calculateSimilarity(normTranscript, normTarget);
  const matched = score >= threshold;

  return {
    matched,
    score,
    target: targetPhrase,
    transcript: transcript.trim(),
    normalizedTarget: normTarget,
    normalizedTranscript: normTranscript,
    threshold,
  };
}
