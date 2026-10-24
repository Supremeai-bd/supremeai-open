import React, { useState } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
import { useAuthStore, AuthStatus } from '../../store/authStore';
import { AuthShell } from '../../components/auth/AuthShell';

// ROOT-CAUSE UNIFY FIX (Refs #890 funnel / owner request "2 rokom na ase"):
// বাংলা মন্তব্য: রেজিস্ট্রেশন পেজ আগে মাঝখানে সিঙ্গেল সেন্টার্ড কার্ড ছিল, কিন্তু
// লগইন ছিল split-screen — দুটো পেজ দেখতে সম্পূর্ণ আলাদা লাগত। এখন দুটোই একই
// AuthShell শেয়ার করে (header + hero + health bar + card + footer) — পার্থক্য
// শুধু কার্ডের ভেতরের লেখা আর ইনপুট বক্স (owner: "sudu likha and box change hobe")।
// কার্ড স্টাইলও লগইনের সাথে হুবহু মিলানো: label-wrapped inputs, sentence-case
// বাটন, একই error shake, একই Google বাটন। রেজিস্ট্রেশন লজিক ও success flow
// সম্পূর্ণ অপরিবর্তিত।
export const RegisterPage: React.FC = () => {
  const [name, setName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [error, setError] = useState('');
  const [errorKey, setErrorKey] = useState(0);
  const [isLoading, setIsLoading] = useState(false);
  const [isSuccess, setIsSuccess] = useState(false);
  const navigate = useNavigate();
  const register = useAuthStore((state) => state.register);
  const status = useAuthStore((state) => state.status);

  // Non-blocking redirect: If already logged in, navigate to workspace in background without spinner
  React.useEffect(() => {
    if (status === AuthStatus.LOGGED_IN) {
      navigate('/workspace', { replace: true });
    }
  }, [status, navigate]);

  const handleRegister = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    if (!email || !password || !name) {
      setError('দয়া করে সব ফিল্ড পূরণ করুন।');
      setErrorKey((k) => k + 1);
      return;
    }

    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      setErrorKey((k) => k + 1);
      return;
    }

    if (password.length < 8) {
      setError('Password must be at least 8 characters.');
      setErrorKey((k) => k + 1);
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
        setErrorKey((k) => k + 1);
      }
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <AuthShell>
      <div className="mb-8">
        <p className="font-mono text-[10px] uppercase tracking-[0.18em] text-slate-500">Create your core</p>
        <h2 className="mt-2 text-2xl font-semibold tracking-tight text-white">Create your account</h2>
        <p className="mt-2 text-sm text-slate-400">Set up your identity and claim your workspace.</p>
      </div>

      {isSuccess ? (
        <div>
          <div className="mb-4 flex h-14 w-14 items-center justify-center rounded-2xl bg-emerald-500/15">
            <svg className="h-7 w-7 text-emerald-400" fill="none" stroke="currentColor" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
            </svg>
          </div>
          <h2 className="mb-3 text-2xl font-semibold tracking-tight text-white">
            Check your Inbox!
          </h2>
          <p className="mb-6 text-sm leading-6 text-slate-400">
            We&apos;ve sent a verification link to <span className="font-semibold text-purple-300">{email}</span>. Please click the link to activate your account before signing in.
          </p>
          <button
            onClick={() => navigate('/login')}
            className="w-full rounded-xl bg-gradient-to-r from-emerald-500 to-purple-600 px-4 py-3 font-semibold text-white shadow-md shadow-emerald-500/20 transition hover:opacity-95"
          >
            Go to Login
          </button>
        </div>
      ) : (
        <>
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
            </motion.div>
          )}

          <form onSubmit={handleRegister} className="space-y-5">
            <label className="block text-sm font-medium text-slate-300" htmlFor="register-name">Full name<input id="register-name" name="name" data-testid="name-input" autoComplete="name" type="text" placeholder="Your full name" value={name} onChange={e => setName(e.target.value)} className="mt-2 w-full rounded-xl border border-white/10 bg-slate-900 px-4 py-3 text-slate-100 outline-none transition focus:border-purple-400/60 focus:ring-2 focus:ring-purple-500/30" /></label>
            <label className="block text-sm font-medium text-slate-300" htmlFor="register-email">Email address<input id="register-email" name="email" data-testid="email-input" autoComplete="email" type="email" placeholder="you@company.com" value={email} onChange={e => setEmail(e.target.value)} className="mt-2 w-full rounded-xl border border-white/10 bg-slate-900 px-4 py-3 text-slate-100 outline-none transition focus:border-purple-400/60 focus:ring-2 focus:ring-purple-500/30" /></label>
            <label className="block text-sm font-medium text-slate-300" htmlFor="register-password">Password<input id="register-password" name="password" data-testid="password-input" autoComplete="new-password" type="password" placeholder="At least 8 characters" value={password} onChange={e => setPassword(e.target.value)} className="mt-2 w-full rounded-xl border border-white/10 bg-slate-900 px-4 py-3 text-slate-100 outline-none transition focus:border-purple-400/60 focus:ring-2 focus:ring-purple-500/30" /></label>
            <label className="block text-sm font-medium text-slate-300" htmlFor="register-confirm">Confirm password<input id="register-confirm" name="confirmPassword" data-testid="confirm-password-input" autoComplete="new-password" type="password" placeholder="Repeat your password" value={confirmPassword} onChange={e => setConfirmPassword(e.target.value)} className="mt-2 w-full rounded-xl border border-white/10 bg-slate-900 px-4 py-3 text-slate-100 outline-none transition focus:border-purple-400/60 focus:ring-2 focus:ring-purple-500/30" /></label>
            <button type="submit" data-testid="register-submit" disabled={isLoading} className="w-full rounded-xl bg-gradient-to-r from-emerald-500 to-purple-600 px-4 py-3 font-semibold text-white shadow-md shadow-emerald-500/20 transition hover:opacity-95 focus:outline-none focus:ring-2 focus:ring-purple-500/40 disabled:cursor-not-allowed disabled:opacity-60">{isLoading ? 'Creating account…' : 'Create account'}</button>
            <button type="button" disabled title="Google sign-up is coming soon" className="w-full cursor-not-allowed rounded-xl border border-white/10 px-4 py-3 text-sm font-medium text-slate-500/70 transition">Continue with Google (coming soon)</button>
          </form>

          <p className="mt-7 text-center text-sm text-slate-400">Already have an account? <Link to="/login" className="font-semibold text-emerald-400 hover:underline">Sign in</Link></p>
        </>
      )}
    </AuthShell>
  );
};
