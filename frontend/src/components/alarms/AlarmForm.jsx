import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import TimeSelector from './TimeSelector';
import RepeatDaySelector from './RepeatDaySelector';
import AlarmSettings from './AlarmSettings';
import ChallengePreview from './ChallengePreview';

/**
 * AlarmForm component
 * Manages alarm creation form state, client-side validation, and navigation
 * to the upcoming Challenge Selection step.
 */
export default function AlarmForm() {
  const navigate = useNavigate();

  // Form state
  const [time, setTime] = useState('07:00');
  const [selectedDays, setSelectedDays] = useState([]);
  const [enabled, setEnabled] = useState(true);
  const [label, setLabel] = useState('');

  // Validation state
  const [errors, setErrors] = useState({});
  const [submittedValid, setSubmittedValid] = useState(false);

  const validate = () => {
    const newErrors = {};

    if (!time || time.trim() === '') {
      newErrors.time = 'Alarm time is required.';
    }

    setErrors(newErrors);
    return Object.keys(newErrors).length === 0;
  };

  const handleContinue = (e) => {
    if (e && e.preventDefault) e.preventDefault();

    if (!validate()) {
      setSubmittedValid(false);
      return;
    }

    setSubmittedValid(true);

    const alarmDraft = {
      time,
      selectedDays,
      isRecurring: selectedDays.length > 0,
      enabled,
      label: label.trim() || 'Morning Alarm',
    };

    // Navigate to challenge selection with draft configuration
    navigate('/challenge', { state: { alarmDraft } });
  };

  return (
    <form onSubmit={handleContinue} noValidate className="space-y-8">
      {/* Schedule Mode Banner */}
      <div className="p-4 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-between text-xs">
        <span className="text-slate-600">Alarm Configuration</span>
        <span className="font-semibold text-indigo-700 bg-indigo-50 px-2.5 py-1 rounded-full border border-indigo-200">
          {selectedDays.length === 0 ? 'One-time Ring' : 'Recurring Schedule'}
        </span>
      </div>

      {/* 1. Time Input */}
      <TimeSelector
        time={time}
        onChange={(newTime) => {
          setTime(newTime);
          if (errors.time) setErrors((prev) => ({ ...prev, time: null }));
        }}
        error={errors.time}
      />

      {/* 2. Repeat Days */}
      <RepeatDaySelector
        selectedDays={selectedDays}
        onChange={(days) => {
          setSelectedDays(days);
          if (errors.days) setErrors((prev) => ({ ...prev, days: null }));
        }}
        error={errors.days}
      />

      {/* 3. Settings: Toggle & Optional Label */}
      <AlarmSettings
        enabled={enabled}
        onToggleEnabled={setEnabled}
        label={label}
        onChangeLabel={setLabel}
      />

      {/* 4. Challenge Preview & Next Step CTA */}
      <ChallengePreview onContinue={handleContinue} isSubmitting={submittedValid} />
    </form>
  );
}
