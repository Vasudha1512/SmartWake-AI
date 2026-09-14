/**
 * SmartWake AI — Deterministic Math Challenge Service
 *
 * Generates arithmetic verification problems across three difficulty levels (easy, medium, hard)
 * and safely validates user numeric submissions.
 *
 * Guaranteed properties:
 * - Pure deterministic JavaScript arithmetic (100% offline, zero eval / dynamic execution, zero LLMs)
 * - Division always yields clean integer quotients ($dividend = divisor \times quotient$)
 * - Divisors are strictly non-zero ($\ge 2$)
 * - Subtraction always yields non-negative results ($num1 \ge num2$)
 * - Fully testable with optional injected random number generator (RNG)
 */

export const SUPPORTED_DIFFICULTIES = Object.freeze(['easy', 'medium', 'hard']);
export const SUPPORTED_OPERATIONS = Object.freeze(['addition', 'subtraction', 'multiplication', 'division']);

export const OPERATOR_SYMBOLS = Object.freeze({
  addition: '+',
  subtraction: '−',
  multiplication: '×',
  division: '÷',
});

/**
 * Bounds table for operands per operation and difficulty level.
 */
const DIFFICULTY_CONFIG = Object.freeze({
  easy: {
    addition: { min1: 2, max1: 20, min2: 2, max2: 20 },
    subtraction: { min1: 5, max1: 25, min2: 2, max2: 20 },
    multiplication: { min1: 2, max1: 9, min2: 2, max2: 9 },
    division: { minDivisor: 2, maxDivisor: 9, minQuotient: 2, maxQuotient: 9 },
  },
  medium: {
    addition: { min1: 15, max1: 99, min2: 15, max2: 99 },
    subtraction: { min1: 25, max1: 99, min2: 10, max2: 90 },
    multiplication: { min1: 3, max1: 12, min2: 3, max2: 15 },
    division: { minDivisor: 3, maxDivisor: 12, minQuotient: 4, maxQuotient: 15 },
  },
  hard: {
    addition: { min1: 100, max1: 500, min2: 50, max2: 400 },
    subtraction: { min1: 150, max1: 999, min2: 50, max2: 700 },
    multiplication: { min1: 12, max1: 30, min2: 4, max2: 18 },
    division: { minDivisor: 4, maxDivisor: 20, minQuotient: 12, maxQuotient: 35 },
  },
});

/**
 * Safely generates a pseudo-random integer between min and max inclusive
 * using the provided RNG function.
 *
 * @param {number} min
 * @param {number} max
 * @param {() => number} rng
 * @returns {number}
 */
function getRandomInt(min, max, rng) {
  const r = Math.max(0, Math.min(0.999999999, rng()));
  return Math.floor(r * (max - min + 1)) + min;
}

/**
 * Generates an arithmetic problem adhering to the specified difficulty and operation.
 *
 * @param {Object} [options]
 * @param {'easy' | 'medium' | 'hard'} [options.difficulty='medium']
 * @param {'addition' | 'subtraction' | 'multiplication' | 'division'} [options.operation]
 * @param {() => number} [options.rng=Math.random]
 * @returns {{
 *   operands: [number, number],
 *   operation: 'addition' | 'subtraction' | 'multiplication' | 'division',
 *   operator: '+' | '−' | '×' | '÷',
 *   displayExpression: string,
 *   correctAnswer: number,
 *   difficulty: 'easy' | 'medium' | 'hard'
 * }}
 */
export function generateMathProblem(options = {}) {
  const difficulty = options.difficulty || 'medium';
  if (!SUPPORTED_DIFFICULTIES.includes(difficulty)) {
    throw new Error(
      `Invalid difficulty "${difficulty}". Supported values: ${SUPPORTED_DIFFICULTIES.join(', ')}`
    );
  }

  let operation = options.operation;
  if (operation !== undefined && !SUPPORTED_OPERATIONS.includes(operation)) {
    throw new Error(
      `Invalid operation "${operation}". Supported values: ${SUPPORTED_OPERATIONS.join(', ')}`
    );
  }

  const rng = typeof options.rng === 'function' ? options.rng : Math.random;

  // If operation is not specified, select one randomly
  if (!operation) {
    const opIndex = getRandomInt(0, SUPPORTED_OPERATIONS.length - 1, rng);
    operation = SUPPORTED_OPERATIONS[opIndex];
  }

  const config = DIFFICULTY_CONFIG[difficulty][operation];
  const operator = OPERATOR_SYMBOLS[operation];

  let num1;
  let num2;
  let correctAnswer;

  switch (operation) {
    case 'addition': {
      num1 = getRandomInt(config.min1, config.max1, rng);
      num2 = getRandomInt(config.min2, config.max2, rng);
      correctAnswer = num1 + num2;
      break;
    }

    case 'subtraction': {
      const a = getRandomInt(config.min1, config.max1, rng);
      const b = getRandomInt(config.min2, config.max2, rng);
      // Guarantee non-negative result: num1 >= num2
      num1 = Math.max(a, b);
      num2 = Math.min(a, b);
      // Prevent trivial x - x = 0
      if (num1 === num2) {
        num1 += getRandomInt(1, 5, rng);
      }
      correctAnswer = num1 - num2;
      break;
    }

    case 'multiplication': {
      num1 = getRandomInt(config.min1, config.max1, rng);
      num2 = getRandomInt(config.min2, config.max2, rng);
      correctAnswer = num1 * num2;
      break;
    }

    case 'division': {
      // Guaranteed integer division: dividend = divisor * quotient
      const divisor = getRandomInt(config.minDivisor, config.maxDivisor, rng);
      const quotient = getRandomInt(config.minQuotient, config.maxQuotient, rng);
      const dividend = divisor * quotient;
      num1 = dividend;
      num2 = divisor;
      correctAnswer = quotient;
      break;
    }

    default: {
      // Safe fallback
      num1 = 12;
      num2 = 15;
      operation = 'addition';
      correctAnswer = 27;
      break;
    }
  }

  return {
    operands: [num1, num2],
    operation,
    operator,
    displayExpression: `${num1} ${operator} ${num2}`,
    correctAnswer,
    difficulty,
  };
}

/**
 * Validates a user's answer against the target math problem.
 *
 * Strict safety rules:
 * - Trims whitespace
 * - Rejects empty input
 * - Rejects non-numeric input (strings, letters, symbols)
 * - Rejects NaN, Infinity, -Infinity
 * - Compares strictly against problem.correctAnswer
 * - Zero eval / zero string-to-code execution
 *
 * @param {{ correctAnswer: number }} problem
 * @param {string | number} userAnswer
 * @returns {{
 *   correct: boolean,
 *   expectedAnswer: number,
 *   userAnswer: number | null,
 *   error?: string
 * }}
 */
export function validateMathAnswer(problem, userAnswer) {
  if (!problem || typeof problem.correctAnswer !== 'number') {
    throw new Error('validateMathAnswer requires a valid problem object with correctAnswer');
  }

  const expectedAnswer = problem.correctAnswer;

  if (userAnswer === null || userAnswer === undefined) {
    return {
      correct: false,
      expectedAnswer,
      userAnswer: null,
      error: 'Empty answer',
    };
  }

  const trimmed = String(userAnswer).trim();
  if (trimmed === '') {
    return {
      correct: false,
      expectedAnswer,
      userAnswer: null,
      error: 'Empty answer',
    };
  }

  // Reject NaN / Infinity literal strings
  if (/^[+-]?infinity$/i.test(trimmed) || /^nan$/i.test(trimmed)) {
    return {
      correct: false,
      expectedAnswer,
      userAnswer: null,
      error: 'Invalid non-numeric input',
    };
  }

  // Strictly accept only valid integers with optional leading sign
  if (!/^[+-]?\d+$/.test(trimmed)) {
    return {
      correct: false,
      expectedAnswer,
      userAnswer: null,
      error: 'Invalid non-numeric input',
    };
  }

  const parsed = Number(trimmed);

  if (!Number.isFinite(parsed) || Number.isNaN(parsed)) {
    return {
      correct: false,
      expectedAnswer,
      userAnswer: null,
      error: 'Invalid non-numeric input',
    };
  }

  const correct = parsed === expectedAnswer;

  return {
    correct,
    expectedAnswer,
    userAnswer: parsed,
  };
}
