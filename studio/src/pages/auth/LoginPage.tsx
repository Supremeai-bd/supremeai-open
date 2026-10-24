import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useAuthStore, AuthStatus } from '../../store/authStore';
import { ServiceHealthBar } from '../../components/auth/ServiceHealthBar';
import { apiClient } from '../../services/apiClient';

// ROOT-CAUSE RESTYLE (Refs #890 funnel / Cosmic WO2 split-screen auth):
// বাংলা মন্তব্য: সাইন-ইন পেজ আগে legacy --supremeai-color-* টোকেন সিস্টেম
// ব্যবহার করত — Cosmic aurora ডিজাইনের সাথে মিলত না। এখন ল্যান্ডিং/গেস্ট-চ্যাটের
// মতো aurora green/purple + glass split-screen ডিজাইন, সম্পূর্ণ responsive।
// লগইন লজিক, error handling, diagnostic, test IDs — সব অপরিবর্ত���ত।
export const LoginPage: React.FC = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [errorKey, setErrorKey] = useState(0);
  const [diagnostic, setDiagnostic] = useState<{ ok: boolean; message: string } | null>(null);
  const [isDiagnosing, setIsDiagnosing] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const navigate = useNavigate();
  const login = useAuthStore((state) => state.login);
  const status = useAuthStore((state) => state.status);

  // Non-blocking redirect: If already logged in, navigate to workspace in background without spinner
  React.useEffect(() => {
    if (status === AuthStatus.LOGGED_IN) {
      navigate('/workspace', { replace: true });
    }
  }, [status, navigate]);

  const handleLogin = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setDiagnostic(null);
    if (!email || !password) {
      setError('দয়া করে সব ফিল্ড পূরণ করুন।');
      return;
    }

    setIsLoading(true);
    // LIVE-002/003 FIX: Add 30s timeout so login doesn't hang forever.
    const LOGIN_TIMEOUT = 30000;
    let timeoutId: ReturnType<typeof setTimeout> | undefined;
    try {
      const loginPromise = login(email, password);
      await Promise.race([
        loginPromise,
        new Promise<never>((_, reject) => {
          timeoutId = setTimeout(
            () => reject(new Error('Connection timeout. Server may be starting up — please retry in 30s.')),
            LOGIN_TIMEOUT
          );
        }),
      ]);
      navigate('/workspace');
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (err: any) {
      let userMessage = 'লগইন ব্যর্থ হয়েছে।';

      if (err?.message?.includes('timed out') || err?.message?.includes('timeout')) {
        userMessage = '⏰ Server response timeout — Backend may be starting up (cold start). Please retry in 30s.';
      } else if (err?.message?.includes('Failed to fetch') || err?.message?.includes('NetworkError')) {
        userMessage = '🌐 Could not reach the API — this is usually a temporary server issue (or a deployment/CORS misconfiguration). Retrying often helps; if it persists, contact support.';
      } else if (err?.status === 503 || err?.status === 502 || err?.status === 504) {
        userMessage = '🔧 Server temporarily unavailable (maintenance/cold start). Please wait 1-2 minutes.';
      } else if (err?.status === 401 || err?.status === 403) {
        userMessage = '🔑 Invalid credentials. Check your email/password and try again.';
      } else if (err?.status === 400) {
        const detail400 = err?.response?.data?.detail ?? err?.data?.detail ?? err?.detail;
        if (detail400) {
          const text = typeof detail400 === 'string' ? detail400 : JSON.stringify(detail400);
          userMessage = text.includes('database') || text.includes('Database')
            ? '🗄️ Database service unavailable — Our team has been notified.'
            : `⚠️ ${text}`;
        } else {
          userMessage = '⚠️ The sign-in request was rejected (400). Check the entered fields and try again.';
        }
      } else if (err?.response?.data?.detail) {
        const detail = typeof err.response.data.detail === 'string'
          ? err.response.data.detail
          : JSON.stringify(err.response.data.detail);
        userMessage = detail.includes('database') || detail.includes('Database')
          ? '🗄️ Database service unavailable — Our team has been notified.'
          : `Error: ${detail}`;
      } else if (err instanceof Error && err.message) {
        userMessage = `⚠️ ${err.message}`;
      }

      setError(userMessage);
      setErrorKey((k) => k + 1);
    } finally {
      if (timeoutId) clearTimeout(timeoutId);
      setIsLoading(false);
    }
  };

  // Issue #1456: one-click diagnostic — pings the public health contract.
  const runConnectionDiagnostic = async () => {
    setIsDiagnosing(true);
    setDiagnostic(null);
    const started = performance.now();
    try {
      const controller = new AbortController();
      const timer = setTimeout(() => controller.abort(), 10000);
      const resp = await apiClient.stream('/api/v1/health', {
        method: 'GET',
        signal: controller.signal,
      });
      clearTimeout(timer);
      const ms = Math.round(performance.now() - started);
      setDiagnostic({
        ok: resp.ok,
        message: resp.ok
          ? `✅ API reachable (${resp.status}, ${ms}ms) — the server is up, so the problem is likely your credentials.`
          : `⚠️ API responded with status ${resp.status} (${ms}ms).`,
      });
    } catch {
      setDiagnostic({
        ok: false,
        message:
          '❌ API unreachable — no response at all. This points to the server being down or a network/CORS problem on this connection.',
      });
    } finally {
      setIsDiagnosing(false);
    }
  };

  return (
    <main className="relative min-h-screen overflow-hidden bg-slate-950 px-4 py-6 text-slate-100 sm:px-6 lg:px-12">
      {/* Cosmic aurora wash (same family as LandingPage / guest chat) */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_20%,rgba(168,85,247,0.16)_0%,transparent_60%)]" />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_80%_60%,rgba(16,185,129,0.10)_0%,transparent_50%)]" />

      <div className="relative mx-auto flex min-h-[calc(100vh-3rem)] max-w-6xl flex-col">
        <header className="flex items-center justify-between gap-4 py-2">
          <Link to="/" className="flex items-center gap-3" aria-label="SupremeAI home">
            <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-tr from-emerald-400 via-indigo-500 to-purple-600 text-sm font-bold text-white shadow-lg shadow-purple-500/20">S</span>
            <span className="font-semibold tracking-tight">SupremeAI</span>
          </Link>
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-slate-500">Secure workspace access</span>
        </header>

        <div className="grid flex-1 items-center gap-8 py-8 lg:grid-cols-[1fr_minmax(0,26rem)] lg:gap-16 lg:py-12">
          <section className="hidden max-w-xl lg:block">
            <p className="mb-5 font-mono text-xs uppercase tracking-[0.2em] text-emerald-400">Your command center</p>
            <h1 className="max-w-lg text-3xl font-semibold leading-tight tracking-[-0.04em] bg-gradient-to-b from-white via-slate-100 to-slate-400 bg-clip-text text-transparent xl:text-5xl">Turn intent into reliable action.</h1>
            <p className="mt-6 max-w-md text-base leading-7 text-slate-400">Coordinate agents, automate repeatable work, and keep every important decision in view.</p>
            <div className="mt-10 grid max-w-md grid-cols-3 gap-3" aria-label="SupremeAI capabilities">
              {['Agents', 'Automations', 'Oversight'].map((item) => <div key={item} className="rounded-2xl border border-white/10 bg-[var(--surface-glass,rgba(15,23,42,0.6))] p-4 text-xs font-medium text-slate-300 backdrop-blur-md">{item}</div>)}
            </div>
          </section>

          <section className="w-full">
            <div className="mb-4"><ServiceHealthBar /></div>
            <div className="rounded-3xl border border-white/10 bg-[var(--surface-glass,rgba(15,23,42,0.75))] p-6 shadow-[var(--glow-accent,0_0_24px_rgba(168,85,247,0.25))] backdrop-blur-md sm:p-9">
              <div className="mb-8">
                <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-slate-500">Welcome back</p>
                <h2 className="mt-2 text-2xl font-semibold tracking-tight text-white">Sign in to continue</h2>
                <p className="mt-2 text-sm text-slate-400">Access your workspace and active tasks.</p>
              </div>

              {error && (
                <motion.div
                  key={errorKey}
                  role="alert"
                  initial={{ x: 0 }}
                  animate={{ x: [0, -9, 9, -6, 6, -3, 3, 0] }}
                  transition={{ duration: 0.45, ease: 'easeInOut' }}
                  className="mb-5 rounded-xl border border-red-500/30 bg-red-950/40 p-3 text-sm text-red-300"
                >
                  {error}
                  <button
                    type="button"
                    onClick={runConnectionDiagnostic}
                    disabled={isDiagnosing}
                    className="mt-2 block rounded-lg border border-red-500/40 px-3 py-1.5 text-xs font-semibold text-red-300 transition hover:bg-red-900/40 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {isDiagnosing ? 'Checking…' : '🔍 Check connection'}
                  </button>
                  {diagnostic && (
                    <p
                      className={`mt-2 text-xs ${diagnostic.ok ? 'text-emerald-400' : 'text-red-400'}`}
                      role="status"
                    >
                      {diagnostic.message}
                    </p>
                  )}
                </motion.div>
              )}

              <form onSubmit={handleLogin} className="space-y-5">
                <label className="block text-sm font-medium text-slate-300" htmlFor="login-email">Email address<input id="login-email" name="email" data-testid="email-input" autoComplete="email" type="email" placeholder="you@company.com" value={email} onChange={e => setEmail(e.target.value)} className="mt-2 w-full rounded-xl border border-white/10 bg-slate-900 px-4 py-3 text-slate-100 outline-none transition focus:border-purple-400/60 focus:ring-2 focus:ring-purple-500/30" /></label>
                <label className="block text-sm font-medium text-slate-300" htmlFor="login-password">Password<input id="login-password" name="password" data-testid="password-input" autoComplete="current-password" type="password" placeholder="Enter your password" value={password} onChange={e => setPassword(e.target.value)} className="mt-2 w-full rounded-xl border border-white/10 bg-slate-900 px-4 py-3 text-slate-100 outline-none transition focus:border-purple-400/60 focus:ring-2 focus:ring-purple-500/30" /></label>
                <button type="submit" data-testid="login-submit" disabled={isLoading} className="w-full rounded-xl bg-gradient-to-r from-emerald-500 to-purple-600 px-4 py-3 font-semibold text-white shadow-md shadow-emerald-500/20 transition hover:opacity-95 focus:outline-none focus:ring-2 focus:ring-purple-500/40 disabled:cursor-not-allowed disabled:opacity-60">{isLoading ? 'Signing in…' : 'Sign in'}</button>
                <button type="button" disabled title="Google sign-in is coming soon" className="w-full cursor-not-allowed rounded-xl border border-white/10 px-4 py-3 text-sm font-medium text-slate-500/70 transition">Continue with Google (coming soon)</button>
              </form>

              <p className="mt-7 text-center text-sm text-slate-400">Don&apos;t have an account? <Link to="/register" className="font-semibold text-emerald-400 hover:underline">Create one</Link></p>
            </div>
          </section>
        </div>
        <footer className="flex flex-wrap items-center justify-between gap-2 border-t border-white/10 py-5 text-[10px] text-slate-500"><span>Private by design.</span><span className="font-mono">Build {typeof __APP_BUILD_TIME__ !== 'undefined' ? __APP_BUILD_TIME__ : 'Dev'}</span></footer>
      </div>
    </main>
  );
};
