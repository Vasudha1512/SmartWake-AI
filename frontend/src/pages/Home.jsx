import React from 'react';
import { Link } from 'react-router-dom';

export default function Home() {
  return (
    <div className="space-y-12">
      {/* Hero Section */}
      <div className="relative overflow-hidden rounded-2xl bg-gradient-to-br from-indigo-950/50 via-slate-900 to-slate-900 border border-slate-800 p-8 sm:p-12 shadow-2xl">
        <div className="max-w-3xl space-y-6">
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
            <span>Phase 5 &mdash; Frontend Foundation</span>
          </div>

          <h1 className="text-3xl sm:text-5xl font-extrabold text-white tracking-tight leading-tight">
            Wake up with clarity. <br />
            <span className="bg-gradient-to-r from-indigo-400 via-purple-400 to-pink-400 bg-clip-text text-transparent">
              Powered by Adaptive Cognitive AI.
            </span>
          </h1>

          <p className="text-base sm:text-lg text-slate-300 leading-relaxed">
            SmartWake AI replaces standard intrusive alarms with personalized, multi-domain cognitive
            challenges. Backed by verified ML personalization, deterministic safety fallbacks, and
            dynamic GenAI challenge generation.
          </p>

          <div className="pt-2 flex flex-wrap gap-4">
            <Link
              to="/dashboard"
              className="inline-flex items-center justify-center px-5 py-3 rounded-xl font-semibold text-sm text-white bg-indigo-600 hover:bg-indigo-500 shadow-lg shadow-indigo-600/30 transition-all"
            >
              Open Dashboard Placeholder &rarr;
            </Link>
            <Link
              to="/alarms"
              className="inline-flex items-center justify-center px-5 py-3 rounded-xl font-semibold text-sm text-slate-300 bg-slate-800/80 hover:bg-slate-700/80 hover:text-white border border-slate-700 transition-all"
            >
              View Alarms Route
            </Link>
          </div>
        </div>
      </div>

      {/* Architecture Foundations Overview */}
      <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
        <div className="p-6 rounded-xl bg-slate-900/60 border border-slate-800/80 space-y-3">
          <div className="w-10 h-10 rounded-lg bg-indigo-500/10 border border-indigo-500/20 flex items-center justify-center text-indigo-400 font-bold">
            01
          </div>
          <h2 className="text-lg font-semibold text-white">Verified Backend</h2>
          <p className="text-sm text-slate-400">
            Complete FastAPI backend with 1,160/1,160 tests passing across ML personalization, safety
            validation, and challenge execution.
          </p>
        </div>

        <div className="p-6 rounded-xl bg-slate-900/60 border border-slate-800/80 space-y-3">
          <div className="w-10 h-10 rounded-lg bg-purple-500/10 border border-purple-500/20 flex items-center justify-center text-purple-400 font-bold">
            02
          </div>
          <h2 className="text-lg font-semibold text-white">React + Vite Foundation</h2>
          <p className="text-sm text-slate-400">
            Lightweight, high-performance frontend architecture structured for clean state management
            and progressive Phase 5 feature delivery.
          </p>
        </div>

        <div className="p-6 rounded-xl bg-slate-900/60 border border-slate-800/80 space-y-3">
          <div className="w-10 h-10 rounded-lg bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center text-emerald-400 font-bold">
            03
          </div>
          <h2 className="text-lg font-semibold text-white">Deterministic Safety</h2>
          <p className="text-sm text-slate-400">
            Frontend is architected to honor backend authority without duplicating ML inference or
            bypassing safety/fallback pipelines.
          </p>
        </div>
      </div>
    </div>
  );
}
