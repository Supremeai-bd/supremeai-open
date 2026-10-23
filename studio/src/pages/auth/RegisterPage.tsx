import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuthStore } from '../../store/authStore';

// ROOT-CAUSE RESTYLE (Refs #890 funnel / Cosmic auth):
// বাংলা মন্তব্য: রেজিস্ট্রেশন পেজ আগে legacy neon/--supremeai-color-* টোকেন
// ব্যবহার করত। এখন LoginPage-এর মতোই Cosmic aurora glass ডিজাইন —
// সম্পূর্ণ responsive। রেজিস্ট্রেশন লজিক ও success flow অপরিবর্তিত।
export const RegisterPage: React.FC = () => {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [isLoading, setIsLoading] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);
  const navigate = useNavigate();
  const register = useAuthStore((state) => state.register);

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (!email || !password || !name) {
      setError('দয়া করে সব ফিল্ড পূরণ করুন।');
      return;
    }

    setIsLoading(true);
    try {
      await register(email, name, password);
      navigate('/workspace');
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    } catch (err: any) {
      if (err.status === 403 || (err.message && err.message.includes('confirmation'))) {
        setIsSuccess(true);
      } else {
        const errorMsg = err.response?.data?.detail || err.message || 'রেজিস্ট্রেশন ব্যর্থ হয়েছে।';
        setError(`Error: ${errorMsg}`);
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className="relative flex min-h-screen flex-col items-center justify-center overflow-hidden bg-slate-950 px-4 py-8 text-slate-100 sm:px-6">
      {/* Cosmic aurora wash (same family as LoginPage) */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_20%,rgba(168,85,247,0.16)_0%,transparent_60%)]" />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_80%_60%,rgba(16,185,129,0.10)_0%,transparent_50%)]" />

      <div className="relative z-10 w-full max-w-md">
        <Link to="/" className="mb-6 flex items-center justify-center gap-3" aria-label="SupremeAI home">
          <span className="flex h-9 w-9 items-center justify-center rounded-xl bg-gradient-to-tr from-emerald-400 via-indigo-500 to-purple-600 text-sm font-bold text-white shadow-lg shadow-purple-500/20">S</span>
          <span className="text-lg font-semibold tracking-tight">SupremeAI</span>
        </Link>

        <div className="w-full rounded-3xl border border-white/10 bg-[var(--surface-glass,rgba(15,23,42,0.75))] p-6 shadow-[var(--glow-accent,0_0_24px_rgba(168,85,247,0.25))] backdrop-blur-md sm:p-8">
          <h1 className="mb-2 text-center text-3xl font-bold bg-gradient-to-r from-emerald-400 to-purple-500 bg-clip-text text-transparent sm:text-4xl">
            SupremeAI
          </h1>

          {isSuccess ? (
            <div className="mt-6 text-center">
              <div className="mx-auto mb-4 flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500/20">
                <svg className="h-8 w-8 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                </svg>
              </div>
              <h2 className="mb-3 text-2xl font-bold text-white">
                Check your Inbox!
              </h2>
              <p className="mb-6 text-sm leading-6 text-slate-400">
                We've sent a verification link to <span className="font-semibold text-purple-300">{email}</span>. Please click the link to activate your account before signing in.
              </p>
              <button
                onClick={() => navigate('/login')}
                className="w-full rounded-xl bg-gradient-to-r from-emerald-500 to-purple-600 py-3 font-bold text-white shadow-md shadow-emerald-500/20 transition hover:opacity-95"
              >
                Go to Login
              </button>
            </div>
          ) : (
            <>
              <p className="mb-8 text-center font-semibold tracking-wide text-emerald-400">Create Your Core</p>

              {error && <div className="mb-4 rounded-xl border border-red-500/30 bg-red-950/40 p-3 text-center text-sm font-medium text-red-300">{error}</div>}

              <form onSubmit={handleRegister} className="space-y-4">
                <div>
                  <input
                    type="text"
                    placeholder="Full Name"
                    value={name}
                    onChange={e => setName(e.target.value)}
                    className="w-full rounded-xl border border-white/10 bg-slate-900 px-4 py-3 text-slate-100 placeholder:text-slate-500 outline-none transition focus:border-purple-400/60 focus:ring-2 focus:ring-purple-500/30"
                  />
                </div>
                <div>
                  <input
                    type="email"
                    placeholder="Email address"
                    value={email}
                    onChange={e => setEmail(e.target.value)}
                    className="w-full rounded-xl border border-white/10 bg-slate-900 px-4 py-3 text-slate-100 placeholder:text-slate-500 outline-none transition focus:border-purple-400/60 focus:ring-2 focus:ring-purple-500/30"
                  />
                </div>
                <div>
                  <input
                    type="password"
                    placeholder="Password"
                    value={password}
                    onChange={e => setPassword(e.target.value)}
                    className="w-full rounded-xl border border-white/10 bg-slate-900 px-4 py-3 text-slate-100 placeholder:text-slate-500 outline-none transition focus:border-purple-400/60 focus:ring-2 focus:ring-purple-500/30"
                  />
                </div>

                <button
                  type="submit"
                  disabled={isLoading}
                  className="w-full rounded-xl bg-gradient-to-r from-emerald-500 to-purple-600 py-3 font-bold text-white shadow-md shadow-emerald-500/20 transition hover:opacity-95 disabled:pointer-events-none disabled:opacity-50"
                >
                  {isLoading ? 'CREATING...' : 'CREATE ACCOUNT'}
                </button>

                <button
                  type="button"
                  className="mt-4 w-full rounded-xl border border-white/15 py-3 font-semibold text-slate-200 transition hover:bg-white/5"
                >
                  Authenticate with Google
                </button>
              </form>

              <p className="mt-6 text-center text-sm text-slate-400">
                Already have an account?{' '}
                <Link to="/login" className="font-medium text-emerald-400 hover:underline">
                  Sign In
                </Link>
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  );
};
