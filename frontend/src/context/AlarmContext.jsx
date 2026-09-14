import React, { createContext, useContext, useState, useEffect, useRef, useCallback } from 'react';
import {
  calculateNextOccurrence,
  isAlarmValid,
  isValidTimezone,
} from '../utils/alarmScheduler';
import {
  startAlarmSound,
  stopAlarmSound,
  isAlarmSoundPlaying,
} from '../utils/alarmAudio';
import {
  showAlarmNotification,
  resetNotificationDeduplication,
} from '../utils/alarmNotification';

const STORAGE_KEY = 'smartwake_alarm_state_v1';

export const AlarmContext = createContext(null);

const DEFAULT_ALARM = {
  id: null,
  time: '07:00',
  selectedDays: [],
  timezone: 'UTC',
  label: 'Morning Alarm',
  enabled: false,
  status: 'idle', // 'idle' | 'armed' | 'ringing'
  nextOccurrenceMs: null,
  challengeCategory: 'math',
  challengeName: 'Quick Math',
  snoozeCount: 0,
  snoozeDuration: null,
  snoozeEndsAt: null,
};

/**
 * Hydrates and safely validates stored alarm data from localStorage.
 * Discards corrupt or malformed entries.
 *
 * @returns {typeof DEFAULT_ALARM}
 */
function loadPersistedAlarm() {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_ALARM;

    const parsed = JSON.parse(raw);
    if (!isAlarmValid(parsed)) {
      localStorage.removeItem(STORAGE_KEY);
      return DEFAULT_ALARM;
    }

    // Check if an armed alarm's time passed while the tab was closed
    if (parsed.status === 'armed' && parsed.nextOccurrenceMs) {
      if (Date.now() >= parsed.nextOccurrenceMs) {
        return {
          ...parsed,
          status: 'ringing',
          snoozeEndsAt: null,
        };
      }
    }

    return parsed;
  } catch {
    try {
      localStorage.removeItem(STORAGE_KEY);
    } catch {
      // Ignore storage access errors
    }
    return DEFAULT_ALARM;
  }
}

/**
 * Saves alarm state safely to localStorage.
 *
 * @param {typeof DEFAULT_ALARM} alarmState
 */
function persistAlarm(alarmState) {
  try {
    if (!alarmState || alarmState.status === 'idle') {
      localStorage.removeItem(STORAGE_KEY);
    } else {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(alarmState));
    }
  } catch {
    // Ignore storage write errors (e.g. private mode quota)
  }
}

/**
 * AlarmProvider component
 * Hosts global alarm state, background scheduler ticker, visibility change listener,
 * programmatic Web Audio tone synthesizer, browser notifications, and complete snooze lifecycle.
 */
export function AlarmProvider({ children }) {
  const [alarm, setAlarm] = useState(loadPersistedAlarm);
  const [isSoundPlaying, setIsSoundPlaying] = useState(false);
  const alarmRef = useRef(alarm);

  // Keep ref synchronized to allow event listeners to read latest state without reattaching
  useEffect(() => {
    alarmRef.current = alarm;
    persistAlarm(alarm);
  }, [alarm]);

  // Cleanup audio on component unmount
  useEffect(() => {
    return () => {
      stopAlarmSound();
    };
  }, []);

  /**
   * Stops only the audio playback while keeping the alarm status as ringing.
   * Cognitive challenge verification remains active and required.
   */
  const stopSound = useCallback(() => {
    stopAlarmSound();
    setIsSoundPlaying(false);
  }, []);

  /**
   * Arms an alarm configuration and calculates its next concrete occurrence.
   */
  const armAlarm = useCallback((alarmConfig) => {
    stopAlarmSound();
    setIsSoundPlaying(false);
    resetNotificationDeduplication();

    const time = alarmConfig.time || '07:00';
    const selectedDays = Array.isArray(alarmConfig.selectedDays) ? alarmConfig.selectedDays : [];
    const timezone = isValidTimezone(alarmConfig.timezone)
      ? alarmConfig.timezone
      : Intl.DateTimeFormat().resolvedOptions().timeZone || 'UTC';
    const label = (alarmConfig.label || 'Morning Alarm').trim();
    const enabled = alarmConfig.enabled !== false;
    const challengeCategory = alarmConfig.challengeCategory || 'math';
    const challengeName = alarmConfig.challengeName || 'Quick Math';

    const newAlarm = {
      id: `alarm_${Date.now()}_${Math.random().toString(36).substring(2, 8)}`,
      time,
      selectedDays,
      timezone,
      label,
      enabled,
      status: 'armed',
      nextOccurrenceMs: null,
      challengeCategory,
      challengeName,
      snoozeCount: 0,
      snoozeDuration: null,
      snoozeEndsAt: null,
    };

    const nextOccurrenceMs = calculateNextOccurrence(newAlarm, Date.now());
    newAlarm.nextOccurrenceMs = nextOccurrenceMs;

    setAlarm(newAlarm);
    return newAlarm;
  }, []);

  /**
   * Updates the selected challenge category on the active armed alarm.
   */
  const updateAlarmChallenge = useCallback((challengeCategory, challengeName) => {
    setAlarm((prev) => {
      if (!prev || prev.status === 'idle') return prev;
      return {
        ...prev,
        challengeCategory: challengeCategory || prev.challengeCategory || 'math',
        challengeName: challengeName || prev.challengeName || 'Quick Math',
      };
    });
  }, []);

  /**
   * Snoozes the ringing alarm for durationMinutes (5, 10, or 15 minutes).
   * Stops sound, increments snoozeCount, calculates target deadline timestamp,
   * transitions status from ringing to armed, and stores snooze metadata.
   *
   * @param {number} durationMinutes
   * @returns {number} The target timestamp when snooze expires.
   */
  const snoozeAlarm = useCallback((durationMinutes) => {
    const validDuration = [5, 10, 15].includes(durationMinutes) ? durationMinutes : 5;

    // 1. Stop active alarm sound
    stopAlarmSound();
    setIsSoundPlaying(false);

    // 2. Calculate next target timestamp using an absolute deadline
    const now = Date.now();
    const snoozeEndsAt = now + validDuration * 60 * 1000;

    // 3. Update alarm state: armed with nextOccurrenceMs = snoozeEndsAt
    setAlarm((prev) => {
      if (!prev) return DEFAULT_ALARM;
      const newSnoozeCount = (prev.snoozeCount || 0) + 1;
      return {
        ...prev,
        status: 'armed',
        nextOccurrenceMs: snoozeEndsAt,
        snoozeEndsAt,
        snoozeDuration: validDuration,
        snoozeCount: newSnoozeCount,
      };
    });

    return snoozeEndsAt;
  }, []);

  /**
   * Fast forwards the active snooze countdown for immediate demo or testing.
   */
  const fastForwardSnooze = useCallback(() => {
    const current = alarmRef.current;
    if (!current || !current.snoozeEndsAt) return;

    const expiredAlarm = {
      ...current,
      status: 'ringing',
      snoozeEndsAt: null,
    };
    setAlarm(expiredAlarm);
    startAlarmSound();
    setIsSoundPlaying(isAlarmSoundPlaying());
    showAlarmNotification(expiredAlarm);
  }, []);

  /**
   * Disarms the scheduled alarm, resetting state to idle.
   */
  const disarmAlarm = useCallback(() => {
    stopAlarmSound();
    setIsSoundPlaying(false);
    resetNotificationDeduplication();

    setAlarm((prev) => {
      const updated = {
        ...prev,
        enabled: false,
        status: 'idle',
        nextOccurrenceMs: null,
        snoozeCount: 0,
        snoozeDuration: null,
        snoozeEndsAt: null,
      };
      return updated;
    });
  }, []);

  /**
   * Dismisses the active ringing alarm (e.g. upon successful cognitive challenge completion).
   * For repeating alarms: calculates next valid occurrence and preserves repeating schedule.
   * For one-time alarms: transitions to idle and disables alarm.
   */
  const dismissAlarm = useCallback(() => {
    stopAlarmSound();
    setIsSoundPlaying(false);
    resetNotificationDeduplication();

    setAlarm((prev) => {
      if (!prev) return DEFAULT_ALARM;

      const isRepeating = Array.isArray(prev.selectedDays) && prev.selectedDays.length > 0;

      if (isRepeating) {
        const nextOccurrenceMs = calculateNextOccurrence(prev, Date.now());
        return {
          ...prev,
          status: 'armed',
          nextOccurrenceMs,
          snoozeCount: 0,
          snoozeDuration: null,
          snoozeEndsAt: null,
        };
      }

      return {
        ...prev,
        status: 'idle',
        enabled: false,
        nextOccurrenceMs: null,
        snoozeCount: 0,
        snoozeDuration: null,
        snoozeEndsAt: null,
      };
    });
  }, []);

  /**
   * Transition logic when scheduled alarm timestamp is reached.
   */
  const triggerAlarmRinging = useCallback((alarmToRing) => {
    setAlarm((prev) => {
      if (prev.status === 'ringing') return prev;
      return {
        ...prev,
        status: 'ringing',
        snoozeEndsAt: null, // Clear active snooze deadline on resume
      };
    });

    // Start alarm sound
    startAlarmSound();
    setIsSoundPlaying(isAlarmSoundPlaying());

    // Dispatch native browser notification if permission has been granted
    showAlarmNotification(alarmToRing);
  }, []);

  /**
   * Trigger check logic evaluating if current time reached the scheduled target.
   */
  const checkAlarmTrigger = useCallback(() => {
    const currentAlarm = alarmRef.current;
    if (!currentAlarm || currentAlarm.status !== 'armed' || !currentAlarm.nextOccurrenceMs) {
      return;
    }

    const now = Date.now();
    if (now >= currentAlarm.nextOccurrenceMs) {
      triggerAlarmRinging(currentAlarm);
    }
  }, [triggerAlarmRinging]);

  // Initial mount check: if hydrated as ringing, attempt sound playback
  useEffect(() => {
    if (alarmRef.current?.status === 'ringing') {
      startAlarmSound();
      setIsSoundPlaying(isAlarmSoundPlaying());
    }
  }, []);

  // 1. Scheduler loop (continuous 1000ms check while app is open)
  useEffect(() => {
    const timerId = setInterval(() => {
      checkAlarmTrigger();
    }, 1000);

    return () => clearInterval(timerId);
  }, [checkAlarmTrigger]);

  // 2. Visibility change handling (immediate check upon tab refocus / resume)
  useEffect(() => {
    const handleVisibilityChange = () => {
      if (document.visibilityState === 'visible') {
        checkAlarmTrigger();
      }
    };

    document.addEventListener('visibilitychange', handleVisibilityChange);
    return () => {
      document.removeEventListener('visibilitychange', handleVisibilityChange);
    };
  }, [checkAlarmTrigger]);

  const value = {
    alarm,
    armAlarm,
    disarmAlarm,
    dismissAlarm,
    snoozeAlarm,
    fastForwardSnooze,
    updateAlarmChallenge,
    checkAlarmTrigger,
    stopSound,
    isSoundPlaying,
  };

  return <AlarmContext.Provider value={value}>{children}</AlarmContext.Provider>;
}

/**
 * Hook to access the global AlarmContext.
 */
export function useAlarm() {
  const context = useContext(AlarmContext);
  if (!context) {
    throw new Error('useAlarm must be used within an AlarmProvider');
  }
  return context;
}

export default AlarmContext;

