import React from 'react';
import { Link } from 'react-router-dom';

export default function NotFound() {
  return (
    <div className="py-16 text-center space-y-6">
      <div className="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-rose-500/10 text-rose-400 border border-rose-500/20 text-2xl font-bold">
        404
      </div>
      <h1 className="text-3xl font-bold text-white tracking-tight">Page Not Found</h1>
      <p className="text-sm text-slate-400 max-w-md mx-auto">
        The requested route does not exist in SmartWake AI.
      </p>
      <div>
        <Link
          to="/"
          className="inline-flex items-center justify-center px-4 py-2 rounded-xl text-sm font-semibold text-white bg-indigo-600 hover:bg-indigo-500 transition-colors shadow-lg shadow-indigo-600/30"
        >
          &larr; Return to Home
        </Link>
      </div>
    </div>
  );
}
