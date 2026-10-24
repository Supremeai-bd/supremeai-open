import type { ReactNode } from 'react';
import { LiveSimulator } from './LiveSimulator';
import { useAuthStore, AuthStatus } from '../../store/authStore';
import { Link } from 'react-router-dom';
import { AlertCircle } from 'lucide-react';

interface LivingDashboardShellProps {
  // বাংলা মন্তব্য: কেন্দ্রীয় চ্যাট ইন্টারফেস — বিদ্যমান OperatorStudio/ChatPanel এখানে ইনজেক্ট হবে
  chatPanel: ReactNode;
}


export function LivingDashboardShell({ chatPanel }: LivingDashboardShellProps) {
  const isAuthenticated = useAuthStore((s) => s.status === AuthStatus.LOGGED_IN);
  
  return (
    <div className="surface-0 relative flex-1 w-full flex overflow-hidden">
      {/* কেন্দ্র: চ্যাট */}
      <div className="flex-1 flex flex-col min-w-0 relative">
        {!isAuthenticated && (
            <div className="shrink-0 bg-rose-500/10 border-b border-rose-500/20 px-4 py-2 flex items-center justify-center gap-3 shadow-sm z-10">
              <AlertCircle className="w-4 h-4 text-rose-400" />
              <span className="text-xs font-medium text-slate-300">
                You are exploring in <span className="text-rose-400">Guest Mode</span>.
              </span>
              <div className="h-3 w-px bg-slate-700"></div>
              <Link to="/login" className="text-xs font-semibold text-indigo-400 hover:text-indigo-300 hover:underline transition-colors">
                Login / Sign Up
              </Link>
              <span className="text-xs text-slate-500 hidden sm:inline">to save your progress.</span>
            </div>
          )}

        <main className="flex-1 overflow-y-auto">{chatPanel}</main>
      </div>

      {/* ডান দিক: সবসময়-দৃশ্যমান Magic Window (Live Simulator) */}
      <aside
        data-testid="magic-window"
        className="surface-1 hidden lg:flex shrink-0 w-96 border-l border-border flex-col"
      >
        <div className="px-4 py-3 border-b border-border text-xs font-semibold text-text">
          Live Simulator — Transformation Map
        </div>
        <div className="flex-1 flex items-center justify-center text-xs text-slate-500">
          <LiveSimulator state={'idle'} nodeStatus={{}} enabledIntegrations={[]} />
        </div>
      </aside>
    </div>
  );
}
