import React from 'react';
import { Link } from 'react-router-dom';

/**
 * AlarmSummary component
 * Displays a clean, read-only overview of the alarm draft configured in Step 3.
 *
 * @param {{
 *   alarmDraft?: {
 *     time?: string,
 *     selectedDays?: string[],
 *     isRecurring?: boolean,
 *     enabled?: boolean,
 *     label?: string
 *   } | null
 * }} props
 */
export default function AlarmSummary({ alarmDraft = null }) {
  const formatTime = (timeStr) => {
    if (!timeStr) return 'Not specified';
    const [hoursStr, minutesStr] = timeStr.split(':');
    const hours = parseInt(hoursStr, 10);
    if (isNaN(hours)) return timeStr;
    const period = hours >= 12 ? 'PM' : 'AM';
    const displayHours = hours % 12 === 0 ? 12 : hours % 12;
    const formattedHours = displayHours < 10 ? `0${displayHours}` : `${displayHours}`;
    return `${formattedHours}:${minutesStr || '00'} ${period}`;
  };

  const formatSchedule = (days) => {
    if (!days || days.length === 0) return 'One-time ring (No repeat)';
    if (days.length === 7) return 'Every day';
    const dayMap = {
      mon: 'Mon',
      tue: 'Tue',
      wed: 'Wed',
      thu: 'Thu',
      fri: 'Fri',
      sat: 'Sat',
      sun: 'Sun',
    };
    const weekdays = ['mon', 'tue', 'wed', 'thu', 'fri'];
    const weekends = ['sat', 'sun'];

    const isWeekdays = weekdays.every((d) => days.includes(d)) && days.length === 5;
    if (isWeekdays) return 'Weekdays (Mon–Fri)';

    const isWeekends = weekends.every((d) => days.includes(d)) && days.length === 2;
    if (isWeekends) return 'Weekends (Sat–Sun)';

    return days.map((d) => dayMap[d] || d).join(', ');
  };

  const displayTime = alarmDraft?.time ? formatTime(alarmDraft.time) : 'Not specified';
  const displaySchedule = formatSchedule(alarmDraft?.selectedDays);
  const displayLabel = alarmDraft?.label?.trim() ? alarmDraft.label : 'Not specified';

  return (
    <div className="p-5 rounded-2xl bg-slate-900/60 border border-slate-800 shadow-md">
      <div className="flex items-center justify-between pb-3 border-b border-slate-800/80 mb-3">
        <div className="flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-indigo-400"></span>
          <h2 className="text-xs font-bold uppercase tracking-wider text-slate-300">
            Alarm Draft Summary
          </h2>
        </div>
        <Link
          to="/alarms"
          className="text-xs font-medium text-indigo-400 hover:text-indigo-300 transition-colors"
        >
          Edit Alarm &rarr;
        </Link>
      </div>

      <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-xs">
        <div className="space-y-1">
          <span className="text-slate-400 block">Wake Time</span>
          <span className="text-sm font-bold text-white font-mono block">
            {displayTime}
          </span>
        </div>

        <div className="space-y-1">
          <span className="text-slate-400 block">Schedule</span>
          <span className="text-sm font-medium text-slate-200 block truncate">
            {displaySchedule}
          </span>
        </div>

        <div className="space-y-1">
          <span className="text-slate-400 block">Label</span>
          <span className="text-sm font-medium text-slate-200 block truncate">
            {displayLabel}
          </span>
        </div>
      </div>
    </div>
  );
}
