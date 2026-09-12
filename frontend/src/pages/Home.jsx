import React from 'react';
import { Link } from 'react-router-dom';

export default function Home() {
  return (
    <div className="space-y-12">
      {/* Hero Section */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-indigo-50/80 via-white to-purple-50/40 border border-slate-200 p-8 sm:p-12 shadow-sm">
        <div className="max-w-3xl space-y-6">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold bg-indigo-50 text-indigo-700 border border-indigo-200">
            <span>SmartWake AI &bull; Cognitive Wake Platform</span>
          </div>

          <h1 className="text-3xl sm:text-5xl font-extrabold text-slate-900 tracking-tight leading-tight">
            Wake up with clarity. <br />
            <span className="bg-gradient-to-r from-indigo-600 via-purple-600 to-pink-600 bg-clip-text text-transparent">
              Powered by Adaptive Cognitive AI.
            </span>
          </h1>

          <p className="text-base sm:text-lg text-slate-600 leading-relaxed">
            SmartWake AI replaces standard intrusive alarms with personalized, multi-domain cognitive
            challenges. Backed by verified ML personalization, deterministic safety fallbacks, and
            dynamic GenAI challenge generation.
          </p>

          <div className="pt-2 flex flex-wrap gap-4">
            <Link
              to="/dashboard"
              className="inline-flex items-center justify-center px-5 py-3 rounded-xl font-semibold text-sm text-white bg-indigo-600 hover:bg-indigo-700 shadow-md shadow-indigo-600/20 transition-all"
            >
              Open Dashboard &rarr;
            </Link>
            <Link
              to="/alarms"
              className="inline-flex items-center justify-center px-5 py-3 rounded-xl font-semibold text-sm text-slate-700 bg-white hover:bg-slate-50 border border-slate-300 shadow-xs transition-all"
            >
              Set an Alarm
            </Link>
          </div>
        </div>
      </div>

      {/* Architecture Foundations Overview */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="p-6 rounded-xl bg-white border border-slate-200 shadow-xs space-y-3">
          <div className="w-10 h-10 rounded-lg bg-indigo-50 border border-indigo-200 flex items-center justify-center text-indigo-600 font-bold">
            01
          </div>
          <h2 className="text-lg font-semibold text-slate-900">Verified Backend</h2>
          <p className="text-sm text-slate-600">
            Complete FastAPI backend with 1,160/1,160 tests passing across ML personalization, safety
            validation, and challenge execution.
          </p>
        </div>

        <div className="p-6 rounded-xl bg-white border border-slate-200 shadow-xs space-y-3">
          <div className="w-10 h-10 rounded-lg bg-purple-50 border border-purple-200 flex items-center justify-center text-purple-600 font-bold">
            02
          </div>
          <h2 className="text-lg font-semibold text-slate-900">React + Vite Foundation</h2>
          <p className="text-sm text-slate-600">
            Lightweight, high-performance frontend architecture structured for clean state management
            and progressive Phase 5 feature delivery.
          </p>
        </div>

        <div className="p-6 rounded-xl bg-white border border-slate-200 shadow-xs space-y-3">
          <div className="w-10 h-10 rounded-lg bg-emerald-50 border border-emerald-200 flex items-center justify-center text-emerald-600 font-bold">
            03
          </div>
          <h2 className="text-lg font-semibold text-slate-900">Deterministic Safety</h2>
          <p className="text-sm text-slate-600">
            Frontend is architected to honor backend authority without duplicating ML inference or
            bypassing safety/fallback pipelines.
          </p>
        </div>
      </div>
    </div>
  );
}
