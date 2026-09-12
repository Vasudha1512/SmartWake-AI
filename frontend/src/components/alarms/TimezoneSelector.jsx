import React, { useMemo } from 'react';

// Real-world grouped IANA timezone identifiers
const TIMEZONE_GROUPS = [
  {
    region: 'Universal',
    zones: ['UTC'],
  },
  {
    region: 'Asia',
    zones: [
      'Asia/Kolkata',
      'Asia/Dubai',
      'Asia/Singapore',
      'Asia/Tokyo',
      'Asia/Shanghai',
      'Asia/Bangkok',
      'Asia/Hong_Kong',
      'Asia/Seoul',
      'Asia/Jakarta',
      'Asia/Karachi',
      'Asia/Dhaka',
    ],
  },
  {
    region: 'Americas',
    zones: [
      'America/New_York',
      'America/Chicago',
      'America/Denver',
      'America/Los_Angeles',
      'America/Toronto',
      'America/Vancouver',
      'America/Sao_Paulo',
      'America/Buenos_Aires',
      'America/Mexico_City',
    ],
  },
  {
    region: 'Europe',
    zones: [
      'Europe/London',
      'Europe/Paris',
      'Europe/Berlin',
      'Europe/Amsterdam',
      'Europe/Madrid',
      'Europe/Rome',
      'Europe/Zurich',
      'Europe/Athens',
    ],
  },
  {
    region: 'Pacific & Oceania',
    zones: [
      'Australia/Sydney',
      'Australia/Melbourne',
      'Australia/Perth',
      'Australia/Brisbane',
      'Pacific/Auckland',
      'Pacific/Honolulu',
      'Pacific/Fiji',
    ],
  },
];

/**
 * Generates human-friendly display label with offset for any valid IANA timezone
 * using native JavaScript Intl API.
 * e.g. "Asia/Kolkata (IST, GMT+5:30)"
 */
function formatTimezoneLabel(tz) {
  try {
    const now = new Date();
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: tz,
      timeZoneName: 'shortOffset',
    }).formatToParts(now);

    const offsetPart = parts.find((p) => p.type === 'timeZoneName')?.value || '';

    const nameParts = new Intl.DateTimeFormat('en-US', {
      timeZone: tz,
      timeZoneName: 'short',
    }).formatToParts(now);

    const abbrPart = nameParts.find((p) => p.type === 'timeZoneName')?.value || '';

    const labelSuffix = abbrPart && abbrPart !== offsetPart ? `${abbrPart}, ${offsetPart}` : offsetPart;

    return labelSuffix ? `${tz} (${labelSuffix})` : tz;
  } catch {
    return tz;
  }
}

/**
 * TimezoneSelector component
 * Accessible, searchable timezone picker defaulting to browser's detected IANA timezone.
 *
 * @param {{
 *   value: string,
 *   onChange: (timezone: string) => void
 * }} props
 */
export default function TimezoneSelector({ value, onChange }) {
  // Ensure the user's detected browser timezone is available in the list
  const groups = useMemo(() => {
    const detected = Intl.DateTimeFormat().resolvedOptions().timeZone;
    const allZones = TIMEZONE_GROUPS.flatMap((g) => g.zones);

    if (detected && !allZones.includes(detected)) {
      return [
        {
          region: 'Detected Location',
          zones: [detected],
        },
        ...TIMEZONE_GROUPS,
      ];
    }
    return TIMEZONE_GROUPS;
  }, []);

  const currentLabel = useMemo(() => formatTimezoneLabel(value), [value]);

  return (
    <div className="space-y-2">
      <div className="flex items-center justify-between">
        <label htmlFor="alarm-timezone-select" className="text-sm font-semibold text-slate-900">
          Time Zone
        </label>
        <span className="text-xs text-slate-500 font-mono">
          Canonical IANA
        </span>
      </div>

      <div className="relative">
        <select
          id="alarm-timezone-select"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          className="w-full px-4 py-2.5 rounded-xl bg-white border border-slate-300 text-sm font-medium text-slate-900 focus:outline-none focus:ring-2 focus:ring-indigo-500 focus:border-transparent transition-colors shadow-2xs appearance-none cursor-pointer pr-10"
        >
          {groups.map((group) => (
            <optgroup key={group.region} label={group.region}>
              {group.zones.map((tz) => (
                <option key={tz} value={tz}>
                  {formatTimezoneLabel(tz)}
                </option>
              ))}
            </optgroup>
          ))}
        </select>

        {/* Custom Chevron Indicator */}
        <div className="pointer-events-none absolute inset-y-0 right-0 flex items-center px-3 text-slate-500">
          <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M19 9l-7 7-7-7" />
          </svg>
        </div>
      </div>

      <div className="p-2.5 rounded-xl bg-slate-50 border border-slate-200 flex items-center justify-between text-xs text-slate-600">
        <span className="text-slate-500">Selected Zone:</span>
        <span className="font-semibold text-indigo-700 font-mono">
          {currentLabel}
        </span>
      </div>
    </div>
  );
}
