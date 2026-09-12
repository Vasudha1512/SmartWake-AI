/**
 * SmartWake AI — Alarm Scheduler Utility
 *
 * Provides timezone-aware, drift-free next occurrence calculation
 * using native JavaScript Intl and Date APIs.
 */

export const DAYS_ORDER = ['sun', 'mon', 'tue', 'wed', 'thu', 'fri', 'sat'];

/**
 * Extracts civil date and time components for a given epoch timestamp in a specific IANA timezone.
 *
 * @param {Date|number} date
 * @param {string} timeZone - Valid IANA timezone identifier (e.g. 'Asia/Kolkata', 'UTC')
 * @returns {{
 *   year: number,
 *   month: number,
 *   day: number,
 *   hour: number,
 *   minute: number,
 *   second: number,
 *   weekday: 'sun' | 'mon' | 'tue' | 'wed' | 'thu' | 'fri' | 'sat'
 * }}
 */
export function getTimezoneParts(date, timeZone = 'UTC') {
  const targetDate = typeof date === 'number' ? new Date(date) : date;
  const safeTz = isValidTimezone(timeZone) ? timeZone : 'UTC';

  const formatter = new Intl.DateTimeFormat('en-US', {
    timeZone: safeTz,
    year: 'numeric',
    month: 'numeric',
    day: 'numeric',
    hour: 'numeric',
    minute: 'numeric',
    second: 'numeric',
    hour12: false,
    weekday: 'short',
  });

  const parts = formatter.formatToParts(targetDate);
  const partMap = {};
  for (const part of parts) {
    partMap[part.type] = part.value;
  }

  const rawHour = parseInt(partMap.hour, 10);
  const hour = rawHour === 24 ? 0 : rawHour;

  return {
    year: parseInt(partMap.year, 10),
    month: parseInt(partMap.month, 10),
    day: parseInt(partMap.day, 10),
    hour,
    minute: parseInt(partMap.minute, 10),
    second: parseInt(partMap.second, 10),
    weekday: (partMap.weekday || 'sun').toLowerCase(),
  };
}

/**
 * Converts a target civil wall-clock date and time in an IANA timezone
 * into exact UTC epoch milliseconds.
 *
 * Uses iterative offset adjustment to handle daylight saving time (DST)
 * boundaries seamlessly without external libraries.
 *
 * @param {number} year
 * @param {number} month (1-12)
 * @param {number} day (1-31)
 * @param {number} hour (0-23)
 * @param {number} minute (0-59)
 * @param {string} timeZone
 * @returns {number} UTC epoch milliseconds
 */
export function zonedDateTimeToUtc(year, month, day, hour, minute, timeZone = 'UTC') {
  const safeTz = isValidTimezone(timeZone) ? timeZone : 'UTC';
  const targetWallMs = Date.UTC(year, month - 1, day, hour, minute, 0, 0);
  let estimateUtc = targetWallMs;

  for (let i = 0; i < 3; i++) {
    const tzParts = getTimezoneParts(estimateUtc, safeTz);
    const tzWallMs = Date.UTC(
      tzParts.year,
      tzParts.month - 1,
      tzParts.day,
      tzParts.hour,
      tzParts.minute,
      tzParts.second,
      0
    );
    const offset = tzWallMs - estimateUtc;
    estimateUtc = targetWallMs - offset;
  }

  return estimateUtc;
}

/**
 * Checks whether an IANA timezone string is recognized by the environment.
 *
 * @param {string} timeZone
 * @returns {boolean}
 */
export function isValidTimezone(timeZone) {
  if (!timeZone || typeof timeZone !== 'string') return false;
  try {
    Intl.DateTimeFormat(undefined, { timeZone });
    return true;
  } catch {
    return false;
  }
}

/**
 * Calculates the exact future epoch timestamp for the next occurrence of an alarm.
 *
 * Supports:
 * - One-time alarm (`selectedDays` is empty): schedules for today if time is future, else tomorrow.
 * - Repeating alarm: checks current and subsequent days matching selected repeat days.
 *
 * @param {{
 *   time: string, // canonical 'HH:mm' format
 *   selectedDays?: string[], // e.g. ['mon', 'tue', ...], [] for Once
 *   timezone?: string // IANA timezone
 * }} alarm
 * @param {number} [fromMs=Date.now()] - Base timestamp to calculate from
 * @returns {number | null} Next occurrence timestamp in epoch milliseconds, or null if invalid
 */
export function calculateNextOccurrence(alarm, fromMs = Date.now()) {
  if (!alarm || typeof alarm.time !== 'string' || !alarm.time.includes(':')) {
    return null;
  }

  const [hStr, mStr] = alarm.time.split(':');
  const targetHour = parseInt(hStr, 10);
  const targetMinute = parseInt(mStr, 10);

  if (
    isNaN(targetHour) ||
    isNaN(targetMinute) ||
    targetHour < 0 ||
    targetHour > 23 ||
    targetMinute < 0 ||
    targetMinute > 59
  ) {
    return null;
  }

  const timeZone = isValidTimezone(alarm.timezone)
    ? alarm.timezone
    : Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';

  const selectedDays = Array.isArray(alarm.selectedDays)
    ? alarm.selectedDays.map((d) => String(d).toLowerCase())
    : [];

  const isOneTime = selectedDays.length === 0;

  // Search through today and up to 8 days ahead to guarantee finding the next match
  for (let dayOffset = 0; dayOffset <= 8; dayOffset++) {
    const probeDate = new Date(fromMs + dayOffset * 24 * 60 * 60 * 1000);
    const probeTz = getTimezoneParts(probeDate, timeZone);

    if (isOneTime || selectedDays.includes(probeTz.weekday)) {
      const candidateMs = zonedDateTimeToUtc(
        probeTz.year,
        probeTz.month,
        probeTz.day,
        targetHour,
        targetMinute,
        timeZone
      );

      // Must be strictly in the future (with 1000ms threshold to prevent instant double-trigger)
      if (candidateMs > fromMs + 1000) {
        return candidateMs;
      }
    }
  }

  return null;
}

/**
 * Validates the structure of an alarm object (e.g. from localStorage).
 *
 * @param {any} alarm
 * @returns {boolean}
 */
export function isAlarmValid(alarm) {
  if (!alarm || typeof alarm !== 'object') return false;

  const validStatus = ['idle', 'armed', 'ringing'].includes(alarm.status);
  const validTime = typeof alarm.time === 'string' && /^([01]\d|2[0-3]):([0-5]\d)$/.test(alarm.time);
  const validDays = Array.isArray(alarm.selectedDays);
  const validTz = typeof alarm.timezone === 'string' && isValidTimezone(alarm.timezone);

  return validStatus && validTime && validDays && validTz;
}

/**
 * Human-friendly string representation of the duration until next alarm.
 *
 * @param {number} targetMs
 * @param {number} [fromMs=Date.now()]
 * @returns {string}
 */
export function formatRingInDuration(targetMs, fromMs = Date.now()) {
  if (!targetMs || typeof targetMs !== 'number') return '';

  const diffMs = targetMs - fromMs;
  if (diffMs <= 0) return 'Ringing now';

  const totalMinutes = Math.round(diffMs / 60000);
  const hours = Math.floor(totalMinutes / 60);
  const mins = totalMinutes % 60;

  if (hours === 0 && mins === 0) {
    return 'Rings in less than a minute';
  }
  if (hours === 0) {
    return `Rings in ${mins} minute${mins === 1 ? '' : 's'}`;
  }
  if (mins === 0) {
    return `Rings in ${hours} hour${hours === 1 ? '' : 's'}`;
  }
  return `Rings in ${hours} hr ${mins} min`;
}
