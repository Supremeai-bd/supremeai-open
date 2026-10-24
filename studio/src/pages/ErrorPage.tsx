// studio/src/pages/ErrorPage.tsx
// Branded Error 404 & 500 Component with High Demand Surge Marketing Resilience
// বাংলা মন্তব্য: সুপ্রিম ব্র্যান্ডিং সম্বলিত ইউজার ফ্রেন্ডলি ৪০৪ ও ৫০০ এরর পেজ।

import React from 'react';
import { Zap, AlertTriangle, Home, RefreshCw, Activity, ShieldCheck } from 'lucide-react';
import { useNavigate } from 'react-router-dom';

interface ErrorPageProps {
  code?: 404 | 500;
  message?: string;
}

export const ErrorPage: React.FC<ErrorPageProps> = ({
  code = 404,
  message = code === 404
    ? 'The workspace route you are looking for does not exist or has been moved.'
    : 'SupremeAI is currently experiencing unprecedented demand across global neural nodes. Compute clusters are auto-scaling to allocate dedicated capacity.',
}) => {
  const navigate = useNavigate();
  const is500 = code === 500;

  return (
    <div className="flex flex-col items-center justify-center min-h-screen w-full bg-[#080B11] text-gray-100 p-6 text-center select-none relative overflow-hidden">
      {/* Ambient glows */}
      <div className="absolute -top-40 -left-40 w-96 h-96 bg-indigo-600/15 rounded-full blur-[128px] pointer-events-none" />
      <div className="absolute -bottom-40 -right-40 w-96 h-96 bg-cyan-500/15 rounded-full blur-[128px] pointer-events-none" />

      <div className="max-w-md w-full bg-[#0F1422]/90 backdrop-blur-2xl rounded-2xl shadow-[0_25px_60px_rgba(0,0,0,0.7),0_0_40px_rgba(99,102,241,0.15)] p-8 text-center border border-indigo-500/20 relative z-10">
        {/* Radiant top line */}
        <div className="absolute top-0 left-0 right-0 h-1 bg-gradient-to-r from-cyan-400 via-indigo-500 to-purple-500" />

        <div className="relative mb-5 inline-block">
          <div className="h-20 w-20 rounded-2xl bg-gradient-to-br from-indigo-500/20 via-purple-500/10 to-cyan-500/20 border border-cyan-500/30 flex items-center justify-center text-cyan-400 shadow-[0_0_25px_rgba(6,182,212,0.25)]">
            {is500 ? (
              <Zap className="h-10 w-10 animate-pulse text-cyan-400" />
            ) : (
              <AlertTriangle className="h-10 w-10 text-amber-400" />
            )}
          </div>
          <span className="absolute -bottom-2 -right-2 px-2.5 py-0.5 rounded-full bg-slate-900 border border-cyan-500/40 text-cyan-400 text-xs font-mono font-bold shadow-lg">
            {code}
          </span>
        </div>

        {is500 && (
          <div className="inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-semibold tracking-wide bg-indigo-500/10 text-indigo-300 border border-indigo-500/30 mb-4">
            <span className="relative flex h-2 w-2">
              <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-cyan-400 opacity-75" />
              <span className="relative inline-flex rounded-full h-2 w-2 bg-cyan-400" />
            </span>
            High Demand · Swarm Auto-Scaling
          </div>
        )}

        <h1 className="text-2xl font-bold tracking-tight mb-2.5 text-white">
          {code === 404 ? 'Page Not Found' : 'High Demand Across the Swarm'}
        </h1>
        <p className="text-sm text-gray-300 mb-6 leading-relaxed">
          {message}
        </p>

        {is500 && (
          <div className="grid grid-cols-2 gap-2 mb-6 text-left">
            <div className="p-2.5 rounded-lg bg-gray-900/60 border border-gray-800">
              <div className="text-[10px] uppercase tracking-wider text-gray-400 flex items-center gap-1.5 font-medium">
                <Activity className="w-3 h-3 text-cyan-400" /> Swarm Status
              </div>
              <div className="text-xs font-semibold text-gray-200 mt-0.5">
                Balancing Nodes
              </div>
            </div>
            <div className="p-2.5 rounded-lg bg-gray-900/60 border border-gray-800">
              <div className="text-[10px] uppercase tracking-wider text-gray-400 flex items-center gap-1.5 font-medium">
                <ShieldCheck className="w-3 h-3 text-emerald-400" /> Satellites
              </div>
              <div className="text-xs font-semibold text-emerald-400 mt-0.5">
                100% Operational
              </div>
            </div>
          </div>
        )}

        <div className="flex flex-col sm:flex-row items-center gap-3">
          <button
            onClick={() => navigate('/')}
            className="w-full sm:w-1/2 flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-slate-900 border border-slate-800 hover:bg-slate-800 text-slate-200 font-medium text-sm transition-colors cursor-pointer"
          >
            <Home className="h-4 w-4 text-cyan-400" /> Return Home
          </button>
          <button
            onClick={() => window.location.reload()}
            className="w-full sm:w-1/2 flex items-center justify-center gap-2 px-5 py-3 rounded-xl bg-gradient-to-r from-indigo-600 to-cyan-600 hover:from-indigo-500 hover:to-cyan-500 text-white font-semibold text-sm transition-all shadow-[0_0_20px_rgba(99,102,241,0.35)] cursor-pointer"
          >
            <RefreshCw className="h-4 w-4" /> Retry Connection
          </button>
        </div>
      </div>
    </div>
  );
};

export default ErrorPage;
