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
 * programmatic Web Audio tone synthesizer, and browser notification integration.
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
   * Stops the active alarm audio while keeping the alarm status as ringing.
   * Challenge verification remains required.
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

    const newAlarm = {
      id: `alarm_${Date.now()}_${Math.random().toString(36).substring(2, 8)}`,
      time,
      selectedDays,
      timezone,
      label,
      enabled,
      status: 'armed',
      nextOccurrenceMs: null,
    };

    const nextOccurrenceMs = calculateNextOccurrence(newAlarm, Date.now());
    newAlarm.nextOccurrenceMs = nextOccurrenceMs;

    setAlarm(newAlarm);
    return newAlarm;
  }, []);

  /**
   * Disarms the active alarm and resets state to idle.
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
      };
      return updated;
    });
  }, []);

  /**
   * Dismisses the active ringing alarm.
   * For repeating alarms: calculates next valid occurrence.
   * For one-time alarms: transitions to idle.
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
        };
      }

      return {
        ...prev,
        status: 'idle',
        enabled: false,
        nextOccurrenceMs: null,
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
    checkAlarmTrigger,
    stopSound,
    stopAlarmSound: stopSound,
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

