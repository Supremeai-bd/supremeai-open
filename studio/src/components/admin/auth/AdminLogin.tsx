import { useState, useRef, useEffect } from 'react';
// FINAL-TEST SECURITY FIX: the TOTP provisioning URI embeds the 2FA secret.
// It used to be rendered by sending that secret to third-party QR services
// (chart.googleapis.com — a deprecated Google Charts endpoint — with a fallback
// to api.qrserver.com), leaking the admin's TOTP secret to external hosts.
// The QR code is now generated fully client-side with the `qrcode` package.
import QRCode from 'qrcode';

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

  const handleSubmit = (e: React.FormEvent) => {
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
      handleAdminLogin(localPassword);
      if (!otpRequired) {
        setLocalPassword('');
      }
    } catch (err) {
      // Increment attempt counter for rate limiting
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

  return (
    <div className="flex-1 flex items-center justify-center p-6">
      <div className="w-full max-w-md glass-card text-center flex flex-col gap-6 relative overflow-hidden">
        <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-[#00f3ff] to-[#bc13fe]"></div>
        <div>
          <span className="text-5xl block mb-2 drop-shadow-[0_0_12px_#bc13fe]">👑</span>
          <h2 className="text-xl font-bold font-['Space_Grotesk'] tracking-widest uppercase">
            SupremeAI <span className="text-[#00f3ff]">Admin Gate</span>
          </h2>
          <p className="text-slate-400 text-xs mt-1">Authorized access only. Authentication protocol required.</p>
        </div>

        <form
          className="flex flex-col gap-3.5"
          onSubmit={handleSubmit}
          aria-label="Admin authentication form"
        >
          <button type="button" onClick={onAuthorize} className="self-end text-[10px] font-mono text-[#00f3ff] underline underline-offset-2 hover:text-white">
            AUTHORIZE
          </button>
          {!otpRequired && (
            <>
              <div>
                <label htmlFor="admin-email" className="sr-only">Admin Email</label>
                <input
                  id="admin-email"
                  data-testid="admin-email-input"
                  type="email"
                  placeholder="Admin Email"
                  value={adminEmail}
                  onChange={e => setAdminEmail(e.target.value)}
                  className="w-full text-center bg-[#07090f] border border-slate-800 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-[#00f3ff] transition-all font-mono tracking-widest"
                  required
                  autoComplete="email"
                  aria-required="true"
                  aria-invalid={localError ? 'true' : 'false'}
                />
              </div>
              <div>
                <label htmlFor="admin-password" className="sr-only">Password</label>
                <input
                  id="admin-password"
                  data-testid="admin-password-input"
                  type="password"
                  placeholder="Password"
                  value={localPassword}
                  onChange={e => setLocalPassword(e.target.value)}
                  className="w-full text-center bg-[#07090f] border border-slate-800 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-[#00f3ff] transition-all font-mono tracking-widest"
                  required
                  autoComplete="current-password"
                  aria-required="true"
                  aria-invalid={localError ? 'true' : 'false'}
                />
              </div>
              <label className="flex items-center gap-2 text-[11px] text-slate-400 font-mono cursor-pointer select-none">
                <input
                  type="checkbox"
                  checked={rememberBrowser}
                  onChange={(e) => setRememberBrowser(e.target.checked)}
                  className="accent-cyan-400"
                />
                Remember me (Trust this browser for 7 days)
              </label>
            </>
          )}

          {totpSetupRequired && (
            <div className="flex flex-col items-center gap-2 mb-2 bg-[#07090f] border border-slate-800 rounded-xl p-4">
              <p className="text-xs text-[#00f3ff] font-mono mb-1 text-center">SCAN TO SETUP 2FA (TOTP)</p>

              {provisioningUri ? (
                <>
                  {/* SECURITY: rendered from a locally generated data URL — the
                      provisioning URI (and the TOTP secret inside it) never
                      leaves the browser. */}
                  {qrDataUrl && (
                    <img
                      src={qrDataUrl}
                      alt="TOTP QR Code"
                      className="rounded-lg w-40 h-40"
                    />
                  )}
                  {qrFailed && (
                    <p className="text-[10px] text-amber-400 font-mono text-center">
                      QR rendering failed — use the manual secret below.
                    </p>
                  )}
                </>
              ) : (
                <p className="text-[10px] text-amber-400 font-mono text-center">
                  No QR available yet — use the manual secret below.
                </p>
              )}

              {totpSecret && (
                <div className="w-full text-center">
                  <p className="text-[10px] text-slate-500 font-mono mb-1">OR ENTER SECRET MANUALLY</p>
                  <code className="text-[11px] text-[#00ff66] font-mono bg-slate-900 border border-slate-800 rounded px-2 py-1 block break-all select-all">
                    {totpSecret}
                  </code>
                </div>
              )}

              <button
                type="button"
                onClick={onResetTotp}
                className="text-[10px] font-mono text-[#00f3ff] underline underline-offset-2 hover:text-white"
              >
                {provisioningUri ? 'Generate New QR Code' : 'Generate QR Code'}
              </button>

              <p className="text-[10px] text-slate-500 font-mono mt-1 text-center">Scan with Google Authenticator or Authy</p>
            </div>
          )}

          {recoveryCodes.length > 0 && (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 p-3 text-left">
              <p className="text-[10px] font-mono text-amber-300">Save these one-time recovery codes securely:</p>
              <code className="mt-2 block select-all break-words text-[10px] text-amber-200">{recoveryCodes.join(' · ')}</code>
            </div>
          )}

          {otpRequired && !totpSetupRequired && (
            <>
            <div className="flex gap-2">
              <input aria-label="Recovery code" value={recoveryCode} onChange={(e) => setRecoveryCode(e.target.value)} placeholder="Recovery code" className="flex-1 rounded-xl border border-slate-800 bg-[#07090f] px-3 py-2 text-xs text-white font-mono" />
              <button type="button" onClick={recoverTotp} className="rounded-xl border border-[#00f3ff]/40 px-3 text-[10px] text-[#00f3ff]">Recover</button>
            </div>
            <button
              type="button"
              onClick={onResetTotp}
              className="text-[10px] font-mono text-[#00f3ff] underline underline-offset-2 hover:text-white mb-1"
            >
              Lost your authenticator? Generate a new QR code
            </button>
            </>
          )}

          {otpRequired && (
            <>
            <div>
              <label htmlFor="admin-otp" className="sr-only">Enter 6-digit OTP</label>
              <input
                id="admin-otp"
                data-testid="otp-input"
                type="text"
                inputMode="numeric"
                pattern="[0-9]{6}"
                maxLength={6}
                placeholder="Enter 6-digit OTP"
                value={adminOtp}
                onChange={e => setAdminOtp(e.target.value.replace(/\D/g, ''))}
                className="w-full text-center bg-[#07090f] border border-slate-800 rounded-xl px-4 py-3 text-sm text-white focus:outline-none focus:border-[#00f3ff] transition-all font-mono tracking-widest"
                required
                aria-required="true"
                aria-invalid={localError ? 'true' : 'false'}
              />
            </div>
            {!totpSetupRequired && (
              <label className="flex items-center gap-2 text-[11px] text-slate-400 font-mono cursor-pointer">
                <input type="checkbox" checked={rememberBrowser} onChange={(e) => setRememberBrowser(e.target.checked)} className="accent-cyan-400" />
                Trust this browser for 7 days
              </label>
            )}
            </>
          )}

          {(adminError || localError) && (
            <div className="text-[#ff4d4f] text-xs mt-1 font-mono" role="alert">
              {localError ? (typeof localError === 'string' ? localError : JSON.stringify(localError)) : 
               (typeof adminError === 'string' ? adminError : JSON.stringify(adminError))}
            </div>
          )}

          {isLocked && (
            <div className="text-amber-400 text-xs mt-1 font-mono" role="alert">
              🔒 Account temporarily locked. Retry in {lockoutRemaining}s.
            </div>
          )}

          <button
            type="submit"
            data-testid={otpRequired ? 'otp-submit' : 'admin-login-submit'}
            disabled={isSubmitting || isLocked}
            className="cyber-button w-full uppercase py-3 text-xs tracking-wider font-mono font-bold mt-2 disabled:opacity-50 disabled:cursor-not-allowed"
          >
            {isSubmitting ? 'Verifying...' : otpRequired ? 'Verify OTP' : 'Authorize Access'}
          </button>
        </form>
        
        {/* 
          বাংলা মন্তব্য: প্রোডাকশনে লেটেস্ট বিল্ড ডিপ্লয় হয়েছে কিনা তা সহজে চেক করার জন্য 
          এই Build Timestamp টি অ্যাডমিন গেটেও দেখানো হচ্ছে। 
        */}
        <div className="absolute bottom-2 right-4 text-[9px] text-slate-600 font-mono">
          SupremeAI v2.0
        </div>
      </div>
    </div>
  );
}
