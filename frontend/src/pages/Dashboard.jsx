import React from 'react';
import DashboardHeader from '../components/dashboard/DashboardHeader';
import NextAlarmCard from '../components/dashboard/NextAlarmCard';
import AlarmOverviewCard from '../components/dashboard/AlarmOverviewCard';
import StatsCard from '../components/dashboard/StatsCard';
import RecentWakeUps from '../components/dashboard/RecentWakeUps';
import QuickActions from '../components/dashboard/QuickActions';

/**
 * Dashboard Page
 * SmartWake AI main overview hub.
 * Displays scheduled alarm status, cognitive metrics, wake logs, and action shortcuts.
 * Structured cleanly for Phase 6 backend API consumption while presenting
 * authentic, non-fabricated empty states during Phase 5.
 */
export default function Dashboard() {
  return (
    <div className="space-y-8 max-w-7xl mx-auto">
      {/* 1. Dashboard Header */}
      <DashboardHeader />

      {/* 2 & 3. Next Alarm & Alarm Overview */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-stretch">
        <div className="lg:col-span-7 flex flex-col">
          <NextAlarmCard />
        </div>
        <div className="lg:col-span-5 flex flex-col">
          <AlarmOverviewCard />
        </div>
      </div>

      {/* 4. Wake-up Statistics */}
      <StatsCard />

      {/* 5. Recent Wake-ups */}
      <RecentWakeUps />

      {/* 6. Quick Actions */}
      <QuickActions />
    </div>
  );
}
