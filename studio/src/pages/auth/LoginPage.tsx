import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useAuthStore, AuthStatus } from '../../store/authStore';
import { AuthShell } from '../../components/auth/AuthShell';
import { apiClient } from '../../services/apiClient';
import { Fingerprint, ArrowRight, LoaderCircle, Lock, Mail, ShieldAlert } from 'lucide-react';
import { loginWithPasskey, isPasskeySupported } from '../../services/passkeyService';
import { isRole } from '../../config/permissions';
import type { Role } from '../../config/permissions';
import { setUserToken } from '../../services/tokenStorage';
import { updateTokenCache } from '../../services/apiClient';

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
      setError('দয়া করে ইমেইল এবং পাসওয়ার্ড পূরণ করুন।');
      return;
    }

    setIsLoading(true);
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
        userMessage = '🌐 Could not reach the API — verify your network connection and retry.';
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
          ? `✅ API reachable (${resp.status}, ${ms}ms) — server is healthy.`
          : `⚠️ API responded with status ${resp.status} (${ms}ms).`,
      });
    } catch {
      setDiagnostic({
        ok: false,
        message: '❌ API unreachable — network check failed.',
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
        setUserToken(res.access_token);
        updateTokenCache(res.access_token);
        useAuthStore.setState({
          user: {
            id: res.user_id,
            email: `${res.user_id}@supremeai.local`,
            name: res.device_name || res.user_id,
          },
          role: isRole(res.role) ? (res.role as Role) : 'user',
          status: AuthStatus.LOGGED_IN,
        });
        navigate('/workspace');
      }
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (err: any) {
      setError(err?.message || 'Biometric authentication was cancelled or failed.');
      setErrorKey((k) => k + 1);
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <AuthShell>
      <div className="mb-6">
        <div className="flex items-center justify-between">
          <span className="font-mono text-[10px] uppercase tracking-[0.2em] text-cyan-400">Identity Guard</span>
          <span className="text-[11px] font-mono text-slate-500">v2.0</span>
        </div>
        <h2 className="mt-2 text-2xl font-bold tracking-tight text-white">Sign in to Federation</h2>
        <p className="mt-1.5 text-xs text-slate-400">Access your workspace, autonomous agents, and models.</p>
      </div>

      {error && (
        <motion.div
          key={errorKey}
          role="alert"
          initial={{ x: 0 }}
          animate={{ x: [0, -9, 9, -6, 6, -3, 3, 0] }}
          transition={{ duration: 0.45, ease: 'easeInOut' }}
          className="mb-5 rounded-xl border border-red-500/30 bg-red-950/40 p-3.5 text-xs text-red-300"
        >
          <div className="flex items-start gap-2">
            <ShieldAlert size={16} className="text-red-400 shrink-0 mt-0.5" />
            <div>
              <p>{error}</p>
              <button
                type="button"
                onClick={runConnectionDiagnostic}
                disabled={isDiagnosing}
                className="mt-2 inline-block rounded-md border border-red-500/40 px-2.5 py-1 text-[11px] font-medium text-red-300 transition hover:bg-red-900/40 disabled:opacity-60"
              >
                {isDiagnosing ? 'Checking…' : '🔍 Diagnose connection'}
              </button>
            </div>
          </div>
          {diagnostic && (
            <p
              className={`mt-2 font-mono text-[11px] ${diagnostic.ok ? 'text-emerald-400' : 'text-red-400'}`}
              role="status"
            >
              {diagnostic.message}
            </p>
          )}
        </motion.div>
      )}

      {/* Passkey Login */}
      {isPasskeySupported() && (
        <div className="mb-5">
          <button
            type="button"
            data-testid="passkey-login-button"
            onClick={handlePasskeyLogin}
            disabled={isLoading}
            className="flex items-center justify-center gap-2.5 w-full rounded-xl border border-cyan-500/30 bg-gradient-to-r from-cyan-950/40 via-slate-900 to-indigo-950/40 px-4 py-3 text-xs font-semibold text-cyan-300 shadow-lg shadow-cyan-500/10 transition hover:border-cyan-400 hover:text-white active:scale-[0.99] disabled:opacity-50"
          >
            <Fingerprint className="size-4 text-cyan-400" />
            <span>Sign in with Biometrics / Passkey</span>
          </button>

          <div className="relative my-5 flex items-center justify-center">
            <div className="w-full border-t border-white/10" />
            <span className="absolute bg-[#0f172a] px-3 font-mono text-[10px] text-slate-500 uppercase tracking-widest">
              or credentials
            </span>
          </div>
        </div>
      )}

      <form onSubmit={handleLogin} className="space-y-4">
        <div>
          <label className="block text-xs font-medium text-slate-300 mb-1.5" htmlFor="login-email">
            Email address
          </label>
          <div className="relative flex items-center">
            <span className="absolute left-3.5 text-slate-500 pointer-events-none">
              <Mail size={15} />
            </span>
            <input
              id="login-email"
              name="email"
              data-testid="email-input"
              autoComplete="username webauthn"
              type="email"
              placeholder="name@domain.com"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-xl border border-white/10 bg-slate-950/60 pl-10 pr-4 py-2.5 text-sm text-slate-100 placeholder-slate-600 outline-none transition focus:border-cyan-400/60 focus:ring-2 focus:ring-cyan-500/20"
            />
          </div>
        </div>

        <div>
          <div className="flex items-center justify-between mb-1.5">
            <label className="block text-xs font-medium text-slate-300" htmlFor="login-password">
              Password
            </label>
            <span className="text-[11px] text-slate-500 font-mono">Encrypted</span>
          </div>
          <div className="relative flex items-center">
            <span className="absolute left-3.5 text-slate-500 pointer-events-none">
              <Lock size={15} />
            </span>
            <input
              id="login-password"
              name="password"
              data-testid="password-input"
              autoComplete="current-password"
              type="password"
              placeholder="••••••••••••"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-xl border border-white/10 bg-slate-950/60 pl-10 pr-4 py-2.5 text-sm text-slate-100 placeholder-slate-600 outline-none transition focus:border-cyan-400/60 focus:ring-2 focus:ring-cyan-500/20"
            />
          </div>
        </div>

        <button
          type="submit"
          data-testid="login-submit"
          disabled={isLoading}
          className="flex items-center justify-center gap-2 w-full mt-2 rounded-xl bg-gradient-to-r from-cyan-500 via-indigo-500 to-purple-600 px-4 py-3 text-sm font-semibold text-white shadow-lg shadow-cyan-500/20 transition hover:opacity-95 focus:outline-none focus:ring-2 focus:ring-cyan-400/40 disabled:opacity-60"
        >
          {isLoading ? (
            <>
              <LoaderCircle size={16} className="animate-spin" />
              <span>Authenticating…</span>
            </>
          ) : (
            <>
              <span>Sign In to Workspace</span>
              <ArrowRight size={15} />
            </>
          )}
        </button>
      </form>

      <div className="mt-6 pt-5 border-t border-white/10 flex items-center justify-between text-xs text-slate-400">
        <span>Need an account?</span>
        <Link to="/register" className="font-semibold text-cyan-400 hover:text-cyan-300 transition-colors">
          Create Federation Account →
        </Link>
      </div>
    </AuthShell>
  );
};

export default LoginPage;
