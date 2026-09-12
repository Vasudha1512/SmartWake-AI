import React, { useState } from 'react';
import {
  getNotificationPermission,
  requestNotificationPermission,
  isNotificationSupported,
} from '../../utils/alarmNotification';

/**
 * AlarmSettings component
 * Controls alarm enabled toggle state, optional descriptive label,
 * and browser desktop notification permissions.
 *
 * @param {{
 *   enabled: boolean,
 *   onToggleEnabled: (enabled: boolean) => void,
 *   label: string,
 *   onChangeLabel: (label: string) => void
 * }} props
 */
export default function AlarmSettings({
  enabled,
  onToggleEnabled,
  label,
  onChangeLabel,
}) {
  const [notificationPermission, setNotificationPermission] = useState(() =>
    getNotificationPermission()
  );
  const [isRequestingNotification, setIsRequestingNotification] = useState(false);

  const handleRequestNotification = async () => {
    setIsRequestingNotification(true);
    try {
      const result = await requestNotificationPermission();
      setNotificationPermission(result);
    } finally {
      setIsRequestingNotification(false);
    }
  };

  const hasNotificationSupport = isNotificationSupported();

  return (
    <div className="space-y-6">
      {/* Alarm Enabled State Toggle */}
      <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200 flex items-center justify-between gap-4">
        <div className="space-y-0.5">
          <label htmlFor="alarm-toggle-switch" className="text-sm font-semibold text-slate-900 cursor-pointer">
            Alarm Active
          </label>
          <p className="text-xs text-slate-600">
            {enabled
              ? 'Alarm will ring when scheduled (unsaved draft)'
              : 'Alarm will remain inactive upon creation'}
          </p>
        </div>

        <button
          id="alarm-toggle-switch"
          type="button"
          role="switch"
          aria-checked={enabled}
          onClick={() => onToggleEnabled(!enabled)}
          className={`relative inline-flex h-7 w-12 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:ring-offset-2 focus:ring-offset-white ${
            enabled ? 'bg-indigo-600' : 'bg-slate-300'
          }`}
        >
          <span className="sr-only">Toggle alarm active state</span>
          <span
            aria-hidden="true"
            className={`pointer-events-none inline-block h-6 w-6 transform rounded-full bg-white shadow-xs ring-0 transition duration-200 ease-in-out ${
              enabled ? 'translate-x-5' : 'translate-x-0'
            }`}
          />
        </button>
      </div>

      {/* Optional Alarm Label */}
      <div className="space-y-2">
        <div className="flex items-center justify-between">
          <label htmlFor="alarm-label-input" className="text-sm font-semibold text-slate-900">
            Alarm Label <span className="text-xs font-normal text-slate-500">(Optional)</span>
          </label>
          <span className="text-xs text-slate-500">{label.length}/40 characters</span>
        </div>

        <div className="relative">
          <input
            id="alarm-label-input"
            type="text"
            maxLength={40}
            value={label}
            onChange={(e) => onChangeLabel(e.target.value)}
            placeholder="e.g. Morning workout, Deep work focus"
            className="w-full px-4 py-2.5 rounded-xl bg-white border border-slate-300 text-sm text-slate-900 placeholder-slate-400 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-colors shadow-2xs"
          />
          {label.length > 0 && (
            <button
              type="button"
              onClick={() => onChangeLabel('')}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-slate-400 hover:text-slate-700 p-1"
              aria-label="Clear alarm label"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
              </svg>
            </button>
          )}
        </div>
      </div>

      {/* Browser Notification Permission Control */}
      <div className="p-4 rounded-2xl bg-slate-50 border border-slate-200 space-y-3">
        <div className="flex items-center justify-between gap-4">
          <div className="space-y-0.5">
            <span className="text-sm font-semibold text-slate-900 flex items-center gap-1.5">
              <svg className="w-4 h-4 text-indigo-600" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
                />
              </svg>
              Browser Notifications
            </span>
            <p className="text-xs text-slate-600">
              {notificationPermission === 'granted'
                ? 'Desktop notifications will alert you if this tab is in the background.'
                : notificationPermission === 'denied'
                ? 'Notifications are blocked in your browser settings.'
                : 'Receive a browser popup alert when your alarm rings in the background.'}
            </p>
          </div>

          {/* Action / Status Badge */}
          <div>
            {!hasNotificationSupport ? (
              <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-slate-100 text-slate-500 border border-slate-200">
                Unavailable
              </span>
            ) : notificationPermission === 'granted' ? (
              <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2.5" d="M5 13l4 4L19 7" />
                </svg>
                Notifications Enabled
              </span>
            ) : notificationPermission === 'denied' ? (
              <span className="inline-flex items-center px-2.5 py-1 rounded-full text-xs font-medium bg-rose-50 text-rose-700 border border-rose-200">
                Permission Blocked
              </span>
            ) : (
              <button
                type="button"
                onClick={handleRequestNotification}
                disabled={isRequestingNotification}
                className="px-3 py-1.5 rounded-xl text-xs font-semibold text-indigo-700 bg-indigo-50 hover:bg-indigo-100 border border-indigo-200 shadow-2xs transition-colors cursor-pointer"
              >
                {isRequestingNotification ? 'Requesting...' : 'Enable Notifications'}
              </button>
            )}
          </div>
        </div>

        {/* Informational help note if denied */}
        {notificationPermission === 'denied' && (
          <div className="pt-2 border-t border-slate-200 text-[11px] text-slate-500 leading-relaxed">
            To enable background alerts, open your browser site settings (click the lock/controls icon next to the address bar) and allow notifications for SmartWake AI.
          </div>
        )}
      </div>
    </div>
  );
}

