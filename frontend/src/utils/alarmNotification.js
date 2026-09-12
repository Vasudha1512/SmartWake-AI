/**
 * SmartWake AI — Alarm Notification Service
 *
 * Safe wrapper around the browser Notification API.
 * Provides user-permission checks and deduplicated notification dispatch.
 */

// Tracks the last notified event key (e.g. alarmId + occurrenceMs) to avoid duplicates
let lastNotifiedEventKey = null;

/**
 * Checks whether the browser Notification API is available in this environment.
 *
 * @returns {boolean}
 */
export function isNotificationSupported() {
  return typeof window !== 'undefined' && 'Notification' in window;
}

/**
 * Retrieves the current permission state.
 *
 * @returns {'granted' | 'denied' | 'default' | 'unsupported'}
 */
export function getNotificationPermission() {
  if (!isNotificationSupported()) {
    return 'unsupported';
  }
  return Notification.permission;
}

/**
 * Requests notification permission from the user.
 * Must be triggered by an explicit user gesture (e.g. clicking a button).
 *
 * @returns {Promise<'granted' | 'denied' | 'default' | 'unsupported'>}
 */
export async function requestNotificationPermission() {
  if (!isNotificationSupported()) {
    return 'unsupported';
  }

  try {
    const permission = await Notification.requestPermission();
    return permission;
  } catch {
    // Older browsers might use callback style or throw
    return Notification.permission || 'denied';
  }
}

/**
 * Dispatches a native browser notification when an alarm rings.
 * Only fires if permission is 'granted' and has not already fired for this event.
 *
 * @param {Object} alarm
 * @param {string} [alarm.id]
 * @param {string} [alarm.label]
 * @param {string} [alarm.time]
 * @param {number} [alarm.nextOccurrenceMs]
 * @returns {Notification|null} The created Notification instance, or null if omitted.
 */
export function showAlarmNotification(alarm) {
  if (!isNotificationSupported()) {
    return null;
  }

  if (Notification.permission !== 'granted') {
    return null;
  }

  if (!alarm) {
    return null;
  }

  // Deduplication key based on alarm ID and occurrence timestamp
  const eventKey = `${alarm.id || 'default'}_${alarm.nextOccurrenceMs || 'now'}`;
  if (lastNotifiedEventKey === eventKey) {
    return null;
  }

  try {
    const title = 'SmartWake AI — Alarm Ringing!';
    const label = alarm.label ? alarm.label.trim() : 'Scheduled Alarm';
    const timeStr = alarm.time || '';

    const options = {
      body: `"${label}" (${timeStr}) is ringing! Complete your cognitive challenge to wake up.`,
      tag: `smartwake-alarm-${alarm.id || 'active'}`,
      requireInteraction: true,
      silent: false,
    };

    const notification = new Notification(title, options);
    lastNotifiedEventKey = eventKey;

    notification.onclick = () => {
      try {
        if (typeof window !== 'undefined') {
          window.focus();
        }
      } catch {
        // Ignore focus error
      }
      notification.close();
    };

    return notification;
  } catch {
    return null;
  }
}

/**
 * Resets the notification deduplication tracker.
 * Useful for testing or when alarms are disarmed/re-armed.
 */
export function resetNotificationDeduplication() {
  lastNotifiedEventKey = null;
}
