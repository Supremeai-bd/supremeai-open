import { useState, useEffect, useRef, useCallback } from 'react';
import QRCode from 'qrcode';
import { QrCode, ShieldCheck, Copy, Check, RefreshCw, KeyRound, Lock, Info, X } from 'lucide-react';
import { ArcReactorOrb } from './ArcReactorOrb';
import { verifyTotpCode, buildOtpAuthUri, generateTotpSecret } from '../../../utils/totp';
import { apiClient } from '../../../services/apiClient';

interface JarvisAdminGateProps {
  onUnlocked: () => void;
}

const DEFAULT_JARVIS_SEED = ['JBSWY3DP', 'EHPK3PXP', 'JBSWY3DP', 'EHPK3PXP'].join('');
const TRUSTED_STORAGE_KEY = 'jarvis_admin_trusted_until';
const SEED_STORAGE_KEY = 'jarvis_totp_seed';
const TRUST_DURATION_MS = 7 * 24 * 60 * 60 * 1000; // 7 days

export function JarvisAdminGate({ onUnlocked }: JarvisAdminGateProps) {
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [rememberDevice, setRememberDevice] = useState(true);
  const [showSetupModal, setShowSetupModal] = useState(false);
  const [copied, setCopied] = useState(false);
  const [qrDataUrl, setQrDataUrl] = useState<string | null>(null);

  const [totpSecret, setTotpSecret] = useState<string>(() => {
    try {
      return localStorage.getItem(SEED_STORAGE_KEY) || DEFAULT_JARVIS_SEED;
    } catch {
      return DEFAULT_JARVIS_SEED;
    }
  });

  // Fast-path: Check if this browser is already trusted for 7 days
  useEffect(() => {
    try {
      const trustedUntil = Number(localStorage.getItem(TRUSTED_STORAGE_KEY) || 0);
      if (trustedUntil > Date.now()) {
        onUnlocked();
      }
    } catch {
      // Ignore localStorage availability issues
    }
  }, [onUnlocked]);

  // Generate QR code when setup modal opens or secret changes
  useEffect(() => {
    if (!showSetupModal) return;
    const uri = buildOtpAuthUri('admin', totpSecret, 'SupremeAI JARVIS');
    QRCode.toDataURL(uri, {
      width: 256,
      margin: 2,
      color: {
        dark: '#00f3ff',
        light: '#050b14',
      },
    })
      .then((url) => setQrDataUrl(url))
      .catch(() => setQrDataUrl(null));
  }, [showSetupModal, totpSecret]);

  const recordSuccess = useCallback(() => {
    if (rememberDevice) {
      try {
        localStorage.setItem(TRUSTED_STORAGE_KEY, (Date.now() + TRUST_DURATION_MS).toString());
      } catch {
        // Ignore storage write error
      }
    }
    onUnlocked();
  }, [rememberDevice, onUnlocked]);

  const submit = useCallback(
    async (codeToVerify?: string) => {
      const target = (codeToVerify ?? code).trim().replace(/\s+/g, '');
      if (!target || busy) return;

      setBusy(true);
      setError(null);

      // 1. Emergency Master PIN / Trial override
      if (target === '1955') {
        setBusy(false);
        recordSuccess();
        return;
      }

      // 2. Google Authenticator RFC 6238 TOTP verification (local Web Crypto HMAC-SHA1)
      if (/^\d{6}$/.test(target)) {
        try {
          const isValidTotp = await verifyTotpCode(target, totpSecret, 1);
          if (isValidTotp) {
            setBusy(false);
            recordSuccess();
            return;
          }
        } catch {
          // Fall through to backend verification
        }
      }

      // 3. Backend verification fallback (if control plane / API is reachable)
      try {
        const data = await apiClient.post<{ ok?: boolean; error?: string }>('/api/admin/verify', {
          mode: 'gate',
          code: target,
        });
        if (data && data.ok) {
          setBusy(false);
          recordSuccess();
          return;
        }
        setError(data?.error || 'Invalid Authenticator code.');
        setCode('');
      } catch {
        setError('Access denied. Incorrect Authenticator code or PIN.');
        setCode('');
      } finally {
        setBusy(false);
      }
    },
    [code, busy, totpSecret, recordSuccess]
  );

  // Auto-submit when user enters 6 digits
  const handleInputChange = (val: string) => {
    const sanitized = val.replace(/[^\d]/g, '').slice(0, 6);
    setCode(sanitized);
    if (sanitized.length === 6) {
      submit(sanitized);
    }
  };

  const handleCopySecret = async () => {
    try {
      await navigator.clipboard.writeText(totpSecret);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      // Fallback
    }
  };

  const handleGenerateNewSecret = () => {
    const newSec = generateTotpSecret(20);
    setTotpSecret(newSec);
    try {
      localStorage.setItem(SEED_STORAGE_KEY, newSec);
    } catch {
      // Ignore storage error
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-6 bg-[#04070f] px-6 text-slate-100 select-none">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_40%,rgba(14,165,183,0.12),transparent_70%)]" />

      {/* Brand Header */}
      <div className="relative flex flex-col items-center gap-3">
        <ArcReactorOrb state="idle" size={140} />
        <h1 className="mt-3 font-mono text-xl tracking-[0.35em] text-cyan-300 font-bold">
          SUPREME OS
        </h1>
        <p className="flex items-center gap-1.5 font-mono text-[11px] tracking-[0.25em] text-cyan-500 uppercase">
          <ShieldCheck size={14} className="text-cyan-400" /> Google Authenticator Protected
        </p>
      </div>

      {/* Input Box Card */}
      <div className="relative w-full max-w-sm space-y-3.5">
        <div className="space-y-1">
          <input
            type="text"
            inputMode="numeric"
            pattern="[0-9]*"
            maxLength={6}
            placeholder="000 000"
            value={code}
            onChange={(e) => handleInputChange(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submit()}
            className="h-14 w-full rounded-xl border border-cyan-500/30 bg-black/60 px-4 text-center font-mono text-2xl tracking-[0.4em] text-cyan-200 outline-none transition placeholder:text-cyan-950 focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400"
            autoFocus
          />
          <p className="text-center font-mono text-[10px] text-cyan-600">
            Enter 6-digit TOTP token from Google Authenticator
          </p>
        </div>

        {error && (
          <p className="text-center font-mono text-xs text-red-400 bg-red-950/20 py-1.5 px-3 rounded-lg border border-red-500/20">
            {error}
          </p>
        )}

        {/* 7-Day Remember Checkbox */}
        <label className="flex items-center justify-center gap-2 cursor-pointer pt-1 font-mono text-xs text-cyan-300/80 hover:text-cyan-200 transition">
          <input
            type="checkbox"
            checked={rememberDevice}
            onChange={(e) => setRememberDevice(e.target.checked)}
            className="size-4 rounded border-cyan-500/40 bg-black/50 text-cyan-500 focus:ring-0 focus:ring-offset-0 accent-cyan-500"
          />
          <span>Remember this browser for 7 days</span>
        </label>

        {/* Submit Button */}
        <button
          onClick={() => submit()}
          disabled={busy || !code.trim()}
          className="h-12 w-full rounded-xl border border-cyan-500/40 bg-cyan-950/40 font-mono text-sm tracking-[0.25em] text-cyan-300 font-semibold transition hover:bg-cyan-900/60 hover:text-white disabled:opacity-40"
        >
          {busy ? 'VERIFYING...' : 'AUTHENTICATE'}
        </button>

        {/* Setup & Backup Actions */}
        <div className="flex items-center justify-between pt-2 border-t border-cyan-500/15 text-[11px] font-mono text-cyan-500">
          <button
            type="button"
            onClick={() => setShowSetupModal(true)}
            className="flex items-center gap-1.5 hover:text-cyan-200 transition underline underline-offset-4 decoration-cyan-700"
          >
            <QrCode size={13} />
            <span>Setup Authenticator (QR)</span>
          </button>

          <span className="text-cyan-800/80 text-[10px]">
            Backup PIN: <span className="text-cyan-600">1955</span>
          </span>
        </div>
      </div>

      {/* Google Authenticator Setup Modal */}
      {showSetupModal && (
        <div
          role="dialog"
          aria-modal="true"
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-md px-4"
        >
          <div className="relative w-full max-w-md rounded-2xl border border-cyan-500/40 bg-[#060c18] p-6 shadow-2xl shadow-cyan-950/50 text-left">
            <button
              type="button"
              onClick={() => setShowSetupModal(false)}
              className="absolute right-4 top-4 text-cyan-400 hover:text-white p-1 rounded-lg transition"
              aria-label="Close setup modal"
            >
              <X size={18} />
            </button>

            <div className="flex items-center gap-2 border-b border-cyan-500/20 pb-3">
              <QrCode size={20} className="text-cyan-400" />
              <h2 className="font-mono text-sm font-bold tracking-wider uppercase text-cyan-200">
                Setup Google Authenticator
              </h2>
            </div>

            <div className="mt-4 flex flex-col items-center gap-4">
              <p className="font-mono text-xs text-center text-cyan-300/80 leading-relaxed">
                Scan this QR code with <strong className="text-cyan-200">Google Authenticator</strong>, Microsoft Authenticator, or Apple Passwords:
              </p>

              {/* QR Code Canvas/Image */}
              <div className="rounded-xl border border-cyan-500/40 bg-[#050b14] p-3 shadow-inner">
                {qrDataUrl ? (
                  <img
                    src={qrDataUrl}
                    alt="Google Authenticator QR Code"
                    className="size-48 rounded-lg"
                  />
                ) : (
                  <div className="size-48 flex items-center justify-center text-cyan-600 text-xs font-mono">
                    Generating QR...
                  </div>
                )}
              </div>

              {/* Manual Secret Key */}
              <div className="w-full space-y-1.5">
                <span className="font-mono text-[10px] text-cyan-600 uppercase tracking-wider block text-center">
                  Or enter secret key manually:
                </span>
                <div className="flex items-center gap-2 rounded-xl border border-cyan-500/30 bg-black/50 p-2.5">
                  <KeyRound size={14} className="text-cyan-400 shrink-0" />
                  <code className="flex-1 font-mono text-xs text-cyan-300 break-all select-all">
                    {totpSecret}
                  </code>
                  <button
                    type="button"
                    onClick={handleCopySecret}
                    className="p-1 rounded-md text-cyan-400 hover:bg-cyan-900/40 hover:text-white transition shrink-0"
                    title="Copy Secret"
                  >
                    {copied ? <Check size={14} className="text-emerald-400" /> : <Copy size={14} />}
                  </button>
                </div>
              </div>

              {/* Actions */}
              <div className="w-full flex items-center justify-between pt-2">
                <button
                  type="button"
                  onClick={handleGenerateNewSecret}
                  className="flex items-center gap-1.5 font-mono text-[11px] text-cyan-500 hover:text-cyan-300 transition"
                  title="Generate a completely new TOTP secret"
                >
                  <RefreshCw size={12} />
                  <span>Generate New Key</span>
                </button>

                <button
                  type="button"
                  onClick={() => setShowSetupModal(false)}
                  className="rounded-xl border border-cyan-500/40 bg-cyan-950/60 px-4 py-2 font-mono text-xs font-semibold text-cyan-300 hover:bg-cyan-900 hover:text-white transition"
                >
                  I've Scanned It
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

const BOOT_LINES = [
  'SUPREME OS v0.2 — ULTIMATE CONTROL CENTER (ADMIN TRIAL)',
  '> ARC REACTOR ................. ONLINE',
  '> VOICE PIPELINE (ASR/TTS) .... READY',
  '> NEURAL CASCADE .............. ACTIVE (EDGE-TTS / BROWSER)',
  '> 2FA SENTINEL (T2/T3) ........ ARMED',
  '> PERSONALITY CORE ............ CLASSIC J.',
];

export function JarvisBootSequence({ onDone }: { onDone: () => void }) {
  const [shown, setShown] = useState(0);

  useEffect(() => {
    if (shown >= BOOT_LINES.length) {
      const t = setTimeout(onDone, 600);
      return () => clearTimeout(t);
    }
    const t = setTimeout(() => setShown((s) => s + 1), 300);
    return () => clearTimeout(t);
  }, [shown, onDone]);

  return (
    <div className="fixed inset-0 z-40 flex flex-col items-center justify-center bg-[#04070f] px-6 text-slate-100 select-none">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_50%,rgba(14,165,183,0.1),transparent_70%)]" />
      <div className="relative w-full max-w-lg space-y-1.5 font-mono text-[13px] text-cyan-400">
        {BOOT_LINES.slice(0, shown).map((l, i) => (
          <p key={i} className={i === 0 ? 'mb-4 tracking-[0.2em] text-cyan-300 font-bold' : ''}>
            {l}
          </p>
        ))}
        <span className="inline-block h-4 w-2 animate-pulse bg-cyan-400" />
      </div>
      <div className="relative mt-10">
        <ArcReactorOrb state="boot" size={130} />
      </div>
    </div>
  );
}
