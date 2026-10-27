import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useAuthStore, AuthStatus } from '../../store/authStore';
import { AuthShell } from '../../components/auth/AuthShell';
import { apiClient } from '../../services/apiClient';
import { Fingerprint } from 'lucide-react';
import { loginWithPasskey, isPasskeySupported } from '../../services/passkeyService';

// ROOT-CAUSE UNIFY (Refs #890 funnel / owner request "2 rokom na ase"):
// বাংলা মন্তব্য: লগইন পেজের সব shell (header, hero, health bar, card, footer)
// এখন শেয়ার্ড AuthShell কম্পোনেন্টে — RegisterPage-ও একই shell ব্যবহার করে,
// তাই দুটো পেজ আর কখনো আলাদা দেখাবে না। কার্ডের ভেতরের কনটেন্ট আগের মতোই।
// লগইন লজিক, error handling, diagnostic, test IDs — সব অপরিবর্তিত।
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

  const handlePasskeyLogin = async () => {
    setError('');
    setIsLoading(true);
    try {
      const res = await loginWithPasskey('user');
      if (res && res.access_token) {
        useAuthStore.setState({
          token: res.access_token,
          user: {
            id: res.user_id,
            email: `${res.user_id}@supremeai.local`,
            role: res.role,
          },
          status: AuthStatus.LOGGED_IN,
        });
        navigate('/workspace');
      }
    } catch (err: any) {
      setError(err?.message || 'Biometric authentication was cancelled or failed.');
      setErrorKey((k) => k + 1);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <AuthShell>
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

      {/* One-Click Passkey / Fingerprint Sign In */}
      {isPasskeySupported() && (
        <div className="mb-6">
          <button
            type="button"
            data-testid="passkey-login-button"
            onClick={handlePasskeyLogin}
            disabled={isLoading}
            className="flex items-center justify-center gap-3 w-full rounded-xl border border-cyan-500/40 bg-gradient-to-r from-cyan-950/50 via-slate-900 to-purple-950/40 px-4 py-3.5 font-medium text-cyan-300 shadow-md shadow-cyan-500/10 transition hover:border-cyan-400 hover:text-white hover:shadow-cyan-500/20 active:scale-[0.99] disabled:opacity-50"
          >
            <Fingerprint className="size-5 text-cyan-400 animate-pulse" />
            <span>Sign in with Fingerprint / Passkey</span>
          </button>

          <div className="relative my-6 flex items-center justify-center">
            <div className="w-full border-t border-white/10" />
            <span className="absolute bg-[#0f172a] px-3 font-mono text-[11px] text-slate-500 uppercase tracking-widest">
              or password
            </span>
          </div>
        </div>
      )}

      <form onSubmit={handleLogin} className="space-y-5">
        <label className="block text-sm font-medium text-slate-300" htmlFor="login-email">Email address<input id="login-email" name="email" data-testid="email-input" autoComplete="username webauthn" type="email" placeholder="you@company.com" value={email} onChange={e => setEmail(e.target.value)} className="mt-2 w-full rounded-xl border border-white/10 bg-slate-900 px-4 py-3 text-slate-100 outline-none transition focus:border-purple-400/60 focus:ring-2 focus:ring-purple-500/30" /></label>
        <label className="block text-sm font-medium text-slate-300" htmlFor="login-password">Password<input id="login-password" name="password" data-testid="password-input" autoComplete="current-password" type="password" placeholder="Enter your password" value={password} onChange={e => setPassword(e.target.value)} className="mt-2 w-full rounded-xl border border-white/10 bg-slate-900 px-4 py-3 text-slate-100 outline-none transition focus:border-purple-400/60 focus:ring-2 focus:ring-purple-500/30" /></label>
        <button type="submit" data-testid="login-submit" disabled={isLoading} className="w-full rounded-xl bg-gradient-to-r from-emerald-500 to-purple-600 px-4 py-3 font-semibold text-white shadow-md shadow-emerald-500/20 transition hover:opacity-95 focus:outline-none focus:ring-2 focus:ring-purple-500/40 disabled:cursor-not-allowed disabled:opacity-60">{isLoading ? 'Signing in…' : 'Sign in'}</button>
        <button type="button" disabled title="Google sign-in is coming soon" className="w-full cursor-not-allowed rounded-xl border border-white/10 px-4 py-3 text-sm font-medium text-slate-500/70 transition">Continue with Google (coming soon)</button>
      </form>

      <p className="mt-7 text-center text-sm text-slate-400">Don&apos;t have an account? <Link to="/register" className="font-semibold text-emerald-400 hover:underline">Create one</Link></p>
    </AuthShell>
  );

};
