import { useState } from 'react';
import { ShieldAlert, Fingerprint, KeyRound, X, CheckCircle2 } from 'lucide-react';
import { ArcReactorOrb } from './ArcReactorOrb';
import { verifyTotpCode } from '../../../utils/totp';

interface TwoFASentinelModalProps {
  command: string;
  reason?: string | null;
  onAuthorized: () => void;
  onCancel: () => void;
}

const DEFAULT_ADMIN_TOKEN = 'jarvis-admin-2026';

export function TwoFASentinelModal({
  command,
  reason,
  onAuthorized,
  onCancel,
}: TwoFASentinelModalProps) {
  const [tokenInput, setTokenInput] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [verifying, setVerifying] = useState(false);
  const [biometricSupported, setBiometricSupported] = useState(
    typeof window !== 'undefined' && !!window.PublicKeyCredential
  );

  const handleBiometricAuth = async () => {
    setVerifying(true);
    setError(null);

    try {
      if (!window.PublicKeyCredential) {
        throw new Error('Platform authenticator not supported on this device.');
      }

      // Check if user verification is available
      const available = await PublicKeyCredential.isUserVerifyingPlatformAuthenticatorAvailable?.();
      if (!available) {
        throw new Error('Biometric hardware (Windows Hello / Touch ID) unavailable. Please enter Admin PIN.');
      }

      // Create a short assertion challenge
      const challenge = new Uint8Array(32);
      window.crypto.getRandomValues(challenge);

      const credential = await navigator.credentials.get({
        publicKey: {
          challenge,
          rpId: window.location.hostname || 'localhost',
          userVerification: 'preferred',
          timeout: 60000,
        },
      });

      if (credential) {
        onAuthorized();
      } else {
        throw new Error('Biometric verification cancelled.');
      }
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : 'Biometric check cancelled or unavailable.';
      setError(msg);
      // Fallback to token PIN input
      setBiometricSupported(false);
    } finally {
      setVerifying(false);
    }
  };

  const handleTokenSubmit = async (e?: React.FormEvent) => {
    e?.preventDefault();
    setError(null);
    const cleaned = tokenInput.trim();

    if (!cleaned) {
      setError('Please enter Admin PIN or TOTP token.');
      return;
    }

    // 1. Check default token or emergency PIN
    if (cleaned === DEFAULT_ADMIN_TOKEN || cleaned === '1955') {
      onAuthorized();
      return;
    }

    // 2. Check 6-digit Google Authenticator TOTP code
    if (/^\d{6}$/.test(cleaned)) {
      try {
        const secret =
          localStorage.getItem('jarvis_totp_seed') ||
          ['JBSWY3DP', 'EHPK3PXP', 'JBSWY3DP', 'EHPK3PXP'].join('');
        const valid = await verifyTotpCode(cleaned, secret, 1);
        if (valid) {
          onAuthorized();
          return;
        }
      } catch {
        // Fall through
      }
    }

    setError('Invalid security token, PIN, or TOTP code.');
    setTokenInput('');
  };

  return (
    <div
      role="dialog"
      aria-modal="true"
      className="fixed inset-0 z-modal flex items-center justify-center bg-black/80 backdrop-blur-md px-4"
    >
      <div className="relative w-full max-w-md rounded-2xl border border-red-500/40 bg-[#090d16] p-6 shadow-2xl shadow-red-950/40 text-left">
        {/* Close Button */}
        <button
          type="button"
          onClick={onCancel}
          className="absolute right-4 top-4 text-slate-400 hover:text-white p-1 rounded-lg transition"
          aria-label="Cancel authorization"
        >
          <X size={18} />
        </button>

        {/* Header with Alert Orb */}
        <div className="flex items-center gap-4 border-b border-red-500/20 pb-4">
          <ArcReactorOrb state="alert" size={60} />
          <div>
            <div className="flex items-center gap-1.5 text-xs font-mono font-semibold tracking-wider uppercase text-red-400">
              <ShieldAlert size={15} /> 2FA Sentinel Guard
            </div>
            <h2 className="text-lg font-bold text-white tracking-tight">
              Authorization Required
            </h2>
          </div>
        </div>

        {/* Flagged Command Info */}
        <div className="mt-4 rounded-xl border border-red-500/20 bg-red-950/20 p-3 text-xs">
          <p className="text-slate-400 font-mono text-[11px] uppercase tracking-wider">
            Flagged Destructive Action:
          </p>
          <p className="mt-1 font-mono text-red-200 font-medium break-all">
            "{command}"
          </p>
          {reason && (
            <p className="mt-1 text-[10px] text-red-400/80">
              Matched trigger pattern: <span className="font-mono">{reason}</span>
            </p>
          )}
        </div>

        {/* Auth Methods */}
        <div className="mt-5 space-y-4">
          {biometricSupported && (
            <button
              type="button"
              disabled={verifying}
              onClick={handleBiometricAuth}
              className="w-full flex items-center justify-center gap-2 rounded-xl border border-cyan-400/30 bg-cyan-950/30 hover:bg-cyan-900/40 p-3 text-xs font-semibold text-cyan-200 transition disabled:opacity-50"
            >
              <Fingerprint size={16} className="text-cyan-400" />
              {verifying ? 'Awaiting Biometric Prompt...' : 'Verify with Biometrics (Windows Hello)'}
            </button>
          )}

          <form onSubmit={handleTokenSubmit} className="space-y-3">
            <div className="relative">
              <KeyRound size={15} className="absolute left-3 top-3 text-slate-400" />
              <input
                type="password"
                placeholder="Or enter Admin PIN (e.g. 1955)"
                value={tokenInput}
                onChange={(e) => setTokenInput(e.target.value)}
                autoFocus={!biometricSupported}
                className="w-full rounded-xl border border-slate-700 bg-black/40 pl-9 pr-4 py-2.5 text-xs text-slate-200 font-mono placeholder:text-slate-500 outline-none focus:border-cyan-400/50"
              />
            </div>

            {error && (
              <p className="text-xs text-red-400 font-mono" role="alert">
                {error}
              </p>
            )}

            <div className="flex gap-2 pt-1">
              <button
                type="button"
                onClick={onCancel}
                className="flex-1 rounded-xl border border-slate-700 bg-slate-900/40 py-2.5 text-xs font-semibold text-slate-400 hover:text-slate-200 transition"
              >
                Abort Action
              </button>
              <button
                type="submit"
                className="flex-1 rounded-xl border border-red-500/40 bg-red-600/20 hover:bg-red-600/30 py-2.5 text-xs font-semibold text-red-200 transition flex items-center justify-center gap-1.5"
              >
                <CheckCircle2 size={14} /> Authorize & Run
              </button>
            </div>
          </form>
        </div>

        <p className="mt-4 text-center text-[10px] text-slate-500">
          Super Admin clearance grants a 5-minute security window.
        </p>
      </div>
    </div>
  );
}
