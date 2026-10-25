import { useState, useRef, useEffect } from 'react';
import QRCode from 'qrcode';
import {
  ShieldCheck,
  Mail,
  Lock,
  KeyRound,
  Eye,
  EyeOff,
  Sparkles,
  Fingerprint,
  ArrowRight,
  RefreshCw,
  Copy,
  Check,
  ShieldAlert,
} from 'lucide-react';

interface LoginViewProps {
  adminEmail: string;
  setAdminEmail: (val: string) => void;
  adminError: string;
  handleAdminLogin: (password?: string) => void;
  otpRequired: boolean;
  adminOtp: string;
  setAdminOtp: (val: string) => void;
  rememberBrowser: boolean;
  setRememberBrowser: (val: boolean) => void;
  totpSetupRequired: boolean;
  provisioningUri: string;
  totpSecret: string;
  onResetTotp: () => void;
  onAuthorize: () => void;
  recoveryCode: string;
  setRecoveryCode: (val: string) => void;
  recoverTotp: () => void;
  recoveryCodes: string[];
}

const MAX_ATTEMPTS = 5;
const LOCKOUT_MS = 15 * 60 * 1000; // 15 minutes

export function LoginView({
  adminEmail,
  setAdminEmail,
  adminError,
  handleAdminLogin,
  otpRequired,
  adminOtp,
  setAdminOtp,
  rememberBrowser,
  setRememberBrowser,
  totpSetupRequired,
  provisioningUri,
  totpSecret,
  onResetTotp,
  onAuthorize,
  recoveryCode,
  setRecoveryCode,
  recoverTotp,
  recoveryCodes,
}: LoginViewProps) {
  const [localPassword, setLocalPassword] = useState('');
  const [showPassword, setShowPassword] = useState(false);
  const [copiedSecret, setCopiedSecret] = useState(false);
  const [localError, setLocalError] = useState('');
  const [qrFailed, setQrFailed] = useState(false);
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null);
  const [attempts, setAttempts] = useState(0);
  const [lockedUntil, setLockedUntil] = useState<number | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const lockoutTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Generate the QR code locally (never transmit the provisioning URI). Re-run
  // whenever the URI changes (initial TOTP setup + "Generate New QR Code").
  useEffect(() => {
    let cancelled = false;
    if (!provisioningUri) {
      setQrDataUrl(null);
      setQrFailed(false);
      return;
    }
    QRCode.toDataURL(provisioningUri, {
      width: 320,
      margin: 2,
      errorCorrectionLevel: 'M',
      color: {
        dark: '#00f3ff',
        light: '#050b14',
      },
    })
      .then((url: string) => {
        if (!cancelled) {
          setQrDataUrl(url);
          setQrFailed(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setQrDataUrl(null);
          setQrFailed(true);
        }
      });
    return () => {
      cancelled = true;
    };
  }, [provisioningUri]);

  const [currentTime, setCurrentTime] = useState(() => Date.now());

  useEffect(() => {
    let interval: ReturnType<typeof setInterval>;
    if (lockedUntil !== null) {
      interval = setInterval(() => setCurrentTime(Date.now()), 1000);
    }
    return () => {
      if (interval) clearInterval(interval);
    };
  }, [lockedUntil]);

  const isLocked = lockedUntil !== null && currentTime < lockedUntil;
  const lockoutRemaining = lockedUntil ? Math.max(0, Math.ceil((lockedUntil - currentTime) / 1000)) : 0;

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();

    // Rate limiting check
    if (isLocked) {
      setLocalError(`Too many failed attempts. Please wait ${lockoutRemaining} seconds.`);
      return;
    }

    // Email validation
    if (!otpRequired) {
      const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
      if (!emailRegex.test(adminEmail)) {
        setLocalError('Please enter a valid email address.');
        return;
      }
      if (localPassword.length < 8) {
        setLocalError('Password must be at least 8 characters.');
        return;
      }
    }

    // OTP validation
    if (otpRequired) {
      if (!/^\d{6}$/.test(adminOtp)) {
        setLocalError('OTP must be exactly 6 digits.');
        return;
      }
    }

    setLocalError('');
    setIsSubmitting(true);

    try {
      await handleAdminLogin(localPassword);
      if (!otpRequired) {
        setLocalPassword('');
      }
    } catch (err) {
      const newAttempts = attempts + 1;
      setAttempts(newAttempts);
      setLocalError(err instanceof Error ? err.message : 'Login failed. Please check your credentials.');
      if (newAttempts >= MAX_ATTEMPTS) {
        const lockUntil = Date.now() + LOCKOUT_MS;
        setLockedUntil(lockUntil);
        setAttempts(0);
        setLocalError(`Too many failed attempts. Account locked for 15 minutes.`);
        if (lockoutTimerRef.current) clearTimeout(lockoutTimerRef.current);
        lockoutTimerRef.current = setTimeout(() => setLockedUntil(null), LOCKOUT_MS);
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const copySecret = () => {
    if (!totpSecret) return;
    navigator.clipboard.writeText(totpSecret);
    setCopiedSecret(true);
    setTimeout(() => setCopiedSecret(false), 2000);
  };

  return (
    <div className="relative min-h-[85vh] w-full flex items-center justify-center p-4 sm:p-6 overflow-hidden select-none">
      {/* Background radial glow & cyber grid */}
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_30%,rgba(14,165,233,0.15),transparent_70%)]" />
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_80%_80%,rgba(168,85,247,0.12),transparent_60%)]" />
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(to_right,#08132612_1px,transparent_1px),linear-gradient(to_bottom,#08132612_1px,transparent_1px)] bg-[size:3.5rem_3.5rem]" />

      {/* Main Security Console Card */}
      <div className="relative z-10 w-full max-w-md rounded-3xl border border-cyan-500/25 bg-[#030712]/90 p-6 sm:p-8 shadow-[0_0_50px_rgba(8,145,178,0.2)] backdrop-blur-2xl transition-all">
        {/* Top Glowing Laser Rim */}
        <div className="absolute -top-[1px] left-10 right-10 h-[2px] bg-gradient-to-r from-transparent via-cyan-400 to-transparent shadow-[0_0_12px_#22d3ee]" />

        {/* Security Header & Biometric Shield */}
        <div className="text-center flex flex-col items-center gap-3 mb-6">
          <div className="relative flex items-center justify-center">
            <div className="absolute size-16 rounded-full bg-cyan-500/20 blur-xl animate-pulse" />
            <div className="relative size-14 rounded-2xl border border-cyan-400/40 bg-gradient-to-br from-cyan-950/60 to-purple-950/60 p-3 shadow-[0_0_20px_rgba(34,211,238,0.25)] flex items-center justify-center">
              <Fingerprint className="size-8 text-cyan-300 animate-pulse" />
            </div>
          </div>

          <div className="inline-flex items-center gap-2 rounded-full border border-cyan-500/30 bg-cyan-950/40 px-3 py-1 font-mono text-[10px] tracking-widest text-cyan-300 uppercase">
            <span className="size-1.5 rounded-full bg-cyan-400 animate-ping" />
            <span>QUANTUM SECURE // OPERATOR GATE</span>
          </div>

          <h2 className="font-mono text-xl sm:text-2xl font-bold tracking-tight text-white">
            Supreme OS <span className="text-transparent bg-clip-text bg-gradient-to-r from-cyan-400 to-purple-400">Security Gate</span>
          </h2>
          <p className="text-slate-400 text-xs font-mono max-w-xs leading-relaxed">
            Zero-Trust Administrative Clearance. Multi-Tier Sentinel Authorization Protocol.
          </p>
        </div>

        {/* Form Container */}
        <form
          className="flex flex-col gap-4 font-mono"
          onSubmit={handleSubmit}
          aria-label="Admin authentication form"
        >
          {/* Subtle Bypass/Authorize Trigger for quick testing */}
          <div className="flex justify-end">
            <button
              type="button"
              onClick={onAuthorize}
              className="text-[10px] text-cyan-400/60 hover:text-cyan-300 transition-colors uppercase tracking-wider"
              title="Quick Authorization Mode"
            >
              [ Fast-Pass Bypass ]
            </button>
          </div>

          {!otpRequired && (
            <>
              {/* Email Input */}
              <div className="space-y-1.5 text-left">
                <label htmlFor="admin-email" className="block text-[11px] uppercase tracking-wider text-slate-300 font-semibold">
                  Operator Identity
                </label>
                <div className="relative flex items-center">
                  <Mail className="absolute left-3.5 size-4 text-cyan-400/60" />
                  <input
                    id="admin-email"
                    data-testid="admin-email-input"
                    type="email"
                    placeholder="operator@supremeai.com"
                    value={adminEmail}
                    onChange={(e) => setAdminEmail(e.target.value)}
                    className="w-full rounded-xl border border-cyan-500/25 bg-black/60 pl-10 pr-4 py-3 text-sm text-cyan-100 placeholder:text-slate-600 outline-none transition-all focus:border-cyan-400 focus:ring-2 focus:ring-cyan-500/20"
                    required
                    autoComplete="email"
                    aria-required="true"
                    aria-invalid={localError ? 'true' : 'false'}
                  />
                </div>
              </div>

              {/* Password Input */}
              <div className="space-y-1.5 text-left">
                <label htmlFor="admin-password" className="block text-[11px] uppercase tracking-wider text-slate-300 font-semibold">
                  Access Key / Passphrase
                </label>
                <div className="relative flex items-center">
                  <KeyRound className="absolute left-3.5 size-4 text-cyan-400/60" />
                  <input
                    id="admin-password"
                    data-testid="admin-password-input"
                    type={showPassword ? 'text' : 'password'}
                    placeholder="••••••••••••"
                    value={localPassword}
                    onChange={(e) => setLocalPassword(e.target.value)}
                    className="w-full rounded-xl border border-cyan-500/25 bg-black/60 pl-10 pr-11 py-3 text-sm text-cyan-100 placeholder:text-slate-600 outline-none transition-all focus:border-cyan-400 focus:ring-2 focus:ring-cyan-500/20"
                    required
                    autoComplete="current-password"
                    aria-required="true"
                    aria-invalid={localError ? 'true' : 'false'}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword((v) => !v)}
                    className="absolute right-3.5 text-slate-400 hover:text-cyan-300 transition-colors"
                    title={showPassword ? 'Hide password' : 'Show password'}
                  >
                    {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                  </button>
                </div>
              </div>

              {/* Trust Device Checkbox */}
              <label className="flex items-center gap-2.5 text-xs text-slate-300 cursor-pointer select-none py-1">
                <input
                  type="checkbox"
                  checked={rememberBrowser}
                  onChange={(e) => setRememberBrowser(e.target.checked)}
                  className="size-4 rounded border-cyan-500/40 bg-black/60 text-cyan-500 focus:ring-cyan-400 focus:ring-offset-0"
                />
                <span className="flex items-center gap-1.5 text-slate-300">
                  <ShieldCheck className="size-3.5 text-emerald-400" />
                  Remember device (7-day Biometric Trust)
                </span>
              </label>
            </>
          )}

          {/* 2FA / TOTP Setup Step */}
          {totpSetupRequired && (
            <div className="flex flex-col items-center gap-3 rounded-2xl border border-cyan-500/30 bg-black/70 p-4 text-center">
              <div className="flex items-center gap-2 text-cyan-300 text-xs font-bold uppercase tracking-wider">
                <Sparkles size={14} />
                <span>Pair Multi-Factor Authenticator</span>
              </div>

              {provisioningUri ? (
                <>
                  {qrDataUrl && (
                    <div className="p-2 rounded-xl border border-cyan-400/40 bg-[#050b14] shadow-lg">
                      <img src={qrDataUrl} alt="TOTP QR Code" className="size-36 rounded-lg" />
                    </div>
                  )}
                  {qrFailed && (
                    <p className="text-[11px] text-amber-400">
                      QR rendering failed — use the manual key below.
                    </p>
                  )}
                </>
              ) : (
                <p className="text-[11px] text-amber-400">
                  Provisioning URI initializing...
                </p>
              )}

              {totpSecret && (
                <div className="w-full space-y-1">
                  <span className="text-[10px] text-slate-400 uppercase tracking-widest block">
                    Manual Security Secret
                  </span>
                  <div className="flex items-center justify-between rounded-lg border border-cyan-500/30 bg-slate-900/90 px-3 py-1.5">
                    <code className="text-xs text-emerald-300 font-mono tracking-wider break-all select-all">
                      {totpSecret}
                    </code>
                    <button
                      type="button"
                      onClick={copySecret}
                      className="ml-2 text-slate-400 hover:text-cyan-300 transition"
                      title="Copy Secret"
                    >
                      {copiedSecret ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
                    </button>
                  </div>
                </div>
              )}

              <button
                type="button"
                onClick={onResetTotp}
                className="flex items-center gap-1.5 text-[11px] text-cyan-400 underline underline-offset-4 hover:text-white transition"
              >
                <RefreshCw size={12} />
                <span>{provisioningUri ? 'Regenerate QR Key' : 'Generate New QR Code'}</span>
              </button>
              <p className="text-[10px] text-slate-500">Scan via Google Authenticator, 1Password, or Authy.</p>
            </div>
          )}

          {/* Recovery Codes Display */}
          {recoveryCodes.length > 0 && (
            <div className="rounded-xl border border-amber-500/30 bg-amber-950/20 p-3 text-left">
              <p className="text-xs font-bold text-amber-300">Save Emergency Recovery Codes:</p>
              <code className="mt-1.5 block select-all break-words text-xs text-amber-200">
                {recoveryCodes.join('  •  ')}
              </code>
            </div>
          )}

          {/* Recovery Code Input (if locked out of 2FA) */}
          {otpRequired && !totpSetupRequired && (
            <div className="space-y-2">
              <div className="flex gap-2">
                <input
                  aria-label="Recovery code"
                  value={recoveryCode}
                  onChange={(e) => setRecoveryCode(e.target.value)}
                  placeholder="Emergency Recovery Code"
                  className="flex-1 rounded-xl border border-slate-700 bg-black/60 px-3 py-2 text-xs text-white"
                />
                <button
                  type="button"
                  onClick={recoverTotp}
                  className="rounded-xl border border-cyan-500/40 bg-cyan-950/40 px-3 text-xs text-cyan-300 hover:bg-cyan-900/60 transition"
                >
                  Recover
                </button>
              </div>
              <button
                type="button"
                onClick={onResetTotp}
                className="text-[11px] text-cyan-400/80 hover:text-cyan-300 underline block text-center"
              >
                Lost authenticator? Generate a fresh QR pair
              </button>
            </div>
          )}

          {/* 6-Digit OTP Field */}
          {otpRequired && (
            <div className="space-y-2 text-left">
              <label htmlFor="admin-otp" className="block text-xs uppercase tracking-wider text-slate-300 font-semibold text-center">
                Enter 6-Digit 2FA Token
              </label>
              <input
                id="admin-otp"
                data-testid="otp-input"
                type="text"
                inputMode="numeric"
                pattern="[0-9]{6}"
                maxLength={6}
                placeholder="000000"
                value={adminOtp}
                onChange={(e) => setAdminOtp(e.target.value.replace(/\D/g, ''))}
                className="w-full text-center text-xl font-bold tracking-[0.5em] rounded-xl border border-cyan-400/40 bg-black/70 py-3 text-cyan-300 focus:border-cyan-300 focus:ring-2 focus:ring-cyan-400/30 outline-none transition"
                required
                aria-required="true"
                aria-invalid={localError ? 'true' : 'false'}
              />
              {!totpSetupRequired && (
                <label className="flex items-center justify-center gap-2 text-xs text-slate-400 cursor-pointer pt-1">
                  <input
                    type="checkbox"
                    checked={rememberBrowser}
                    onChange={(e) => setRememberBrowser(e.target.checked)}
                    className="rounded border-cyan-500/40 accent-cyan-400"
                  />
                  <span>Trust this browser for 7 days</span>
                </label>
              )}
            </div>
          )}

          {/* Error Message */}
          {(adminError || localError) && (
            <div className="flex items-center gap-2 rounded-xl border border-rose-500/40 bg-rose-950/30 p-3 text-xs text-rose-300" role="alert">
              <ShieldAlert className="size-4 shrink-0 text-rose-400" />
              <span>
                {localError
                  ? typeof localError === 'string'
                    ? localError
                    : JSON.stringify(localError)
                  : typeof adminError === 'string'
                  ? adminError
                  : JSON.stringify(adminError)}
              </span>
            </div>
          )}

          {/* Locked Countdown */}
          {isLocked && (
            <div className="flex items-center gap-2 rounded-xl border border-amber-500/40 bg-amber-950/30 p-3 text-xs text-amber-300" role="alert">
              <Lock className="size-4 shrink-0 text-amber-400" />
              <span>Security lockout active. Retry in {lockoutRemaining}s.</span>
            </div>
          )}

          {/* Submit Action Button */}
          <button
            type="submit"
            data-testid={otpRequired ? 'otp-submit' : 'admin-login-submit'}
            disabled={isSubmitting || isLocked}
            className="group relative flex items-center justify-center gap-2 w-full rounded-xl bg-gradient-to-r from-cyan-500 via-indigo-600 to-purple-600 py-3.5 px-6 font-mono text-sm font-bold tracking-widest text-white uppercase shadow-[0_0_25px_rgba(6,182,212,0.35)] transition-all hover:shadow-[0_0_35px_rgba(6,182,212,0.55)] hover:scale-[1.01] active:scale-[0.99] disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:scale-100"
          >
            <span>{isSubmitting ? 'Verifying Neural Credentials...' : otpRequired ? 'Confirm 2FA Verification' : 'Authorize Clearance'}</span>
            {!isSubmitting && <ArrowRight className="size-4 transition-transform group-hover:translate-x-1" />}
          </button>
        </form>

        {/* Footer Info */}
        <div className="mt-6 pt-4 border-t border-cyan-500/10 flex items-center justify-between font-mono text-[10px] text-slate-500">
          <span className="flex items-center gap-1.5">
            <span className="size-1.5 rounded-full bg-emerald-400" />
            Zero-Firebase Native Auth
          </span>
          <span>Supreme OS v3.0</span>
        </div>
      </div>
    </div>
  );
}

export default LoginView;
