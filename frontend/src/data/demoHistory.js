/**
 * Demo Wake Session History Dataset
 *
 * Frontend-only demonstration data for Phase 5.
 * Structured to cleanly mirror future FastAPI / SQLite WakeSession models
 * without requiring API calls or fake persistence.
 */

export const CHALLENGE_META = {
  dance: { name: 'Dance', icon: '🕺' },
  math: { name: 'Math', icon: '🧮' },
  memory: { name: 'Memory', icon: '🧠' },
  tongue_twister: { name: 'Tongue Twister', icon: '👅' },
  pushups: { name: 'Push-ups', icon: '💪' },
};

export const DEMO_HISTORY = [
  {
    id: 'session-1',
    date: 'Today, Sep 12, 2026',
    alarmTime: '07:00 AM',
    challengeType: 'math',
    status: 'completed',
    snoozeCount: 1,
    completionDurationSeconds: 34,
    difficulty: 'ML Adaptive',
  },
  {
    id: 'session-2',
    date: 'Yesterday, Sep 11, 2026',
    alarmTime: '06:45 AM',
    challengeType: 'memory',
    status: 'completed',
    snoozeCount: 0,
    completionDurationSeconds: 42,
    difficulty: 'Medium',
  },
  {
    id: 'session-3',
    date: 'Wed, Sep 10, 2026',
    alarmTime: '07:30 AM',
    challengeType: 'pushups',
    status: 'completed',
    snoozeCount: 2,
    completionDurationSeconds: 58,
    difficulty: 'Hard',
  },
  {
    id: 'session-4',
    date: 'Tue, Sep 9, 2026',
    alarmTime: '07:00 AM',
    challengeType: 'tongue_twister',
    status: 'failed',
    snoozeCount: 1,
    completionDurationSeconds: 65,
    difficulty: 'Easy',
  },
  {
    id: 'session-5',
    date: 'Mon, Sep 8, 2026',
    alarmTime: '06:30 AM',
    challengeType: 'dance',
    status: 'completed',
    snoozeCount: 0,
    completionDurationSeconds: 28,
    difficulty: 'ML Adaptive',
  },
];

/**
 * Dynamically computes summary metrics from any array of history records.
 * Safely handles empty arrays returning zeroes.
 *
 * @param {Array<{
 *   status: 'completed' | 'failed',
 *   snoozeCount?: number
 * }>} records
 * @returns {{
 *   totalWakeUps: number,
 *   successful: number,
 *   failed: number,
 *   averageSnoozes: string
 * }}
 */
export function calculateHistorySummary(records = []) {
  if (!records || records.length === 0) {
    return {
      totalWakeUps: 0,
      successful: 0,
      failed: 0,
      averageSnoozes: '0',
    };
  }

  const totalWakeUps = records.length;
  const successful = records.filter((r) => r.status === 'completed').length;
  const failed = records.filter((r) => r.status === 'failed').length;
  const totalSnoozes = records.reduce((sum, r) => sum + (Number(r.snoozeCount) || 0), 0);
  const avg = totalSnoozes / totalWakeUps;
  const averageSnoozes = Number.isInteger(avg) ? avg.toString() : avg.toFixed(1);

  return {
    totalWakeUps,
    successful,
    failed,
    averageSnoozes,
  };
}
