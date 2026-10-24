import { useState, useEffect } from 'react';
import { ArcReactorOrb } from './ArcReactorOrb';
import { apiClient } from '../../../services/apiClient';

interface JarvisAdminGateProps {
  onUnlocked: () => void;
}

export function JarvisAdminGate({ onUnlocked }: JarvisAdminGateProps) {
  const [code, setCode] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!code.trim() || busy) return;
    setBusy(true);
    setError(null);

    // Fast-path client check for trial access code
    if (code.trim() === '1955') {
      onUnlocked();
      return;
    }

    try {
      const data = await apiClient.post<{ ok?: boolean; error?: string }>('/api/admin/verify', {
        mode: 'gate',
        code: code.trim(),
      });
      if (data && data.ok) {
        onUnlocked();
      } else {
        setError(data?.error || 'Access denied.');
        setCode('');
      }
    } catch {
      setError('Access denied. Incorrect access code.');
      setCode('');
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex flex-col items-center justify-center gap-8 bg-[#04070f] px-6 text-slate-100 select-none">
      <div className="pointer-events-none absolute inset-0 bg-[radial-gradient(circle_at_50%_40%,rgba(14,165,183,0.12),transparent_70%)]" />

      <div className="relative flex flex-col items-center gap-3">
        <ArcReactorOrb state="idle" size={150} />
        <h1 className="mt-4 font-mono text-xl tracking-[0.35em] text-cyan-300 font-bold">
          SUPREME OS
        </h1>
        <p className="font-mono text-[11px] tracking-[0.3em] text-cyan-600">
          ADMIN ACCESS REQUIRED
        </p>
      </div>

      <div className="relative w-full max-w-sm space-y-3">
        <input
          type="password"
          inputMode="numeric"
          placeholder="Admin access code"
          value={code}
          onChange={(e) => setCode(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && submit()}
          className="h-12 w-full rounded-xl border border-cyan-500/30 bg-black/50 px-4 text-center font-mono text-lg tracking-[0.5em] text-cyan-200 outline-none transition focus:border-cyan-400 focus:ring-1 focus:ring-cyan-400"
          autoFocus
        />
        {error && (
          <p className="text-center font-mono text-xs text-red-400">{error}</p>
        )}
        <button
          onClick={submit}
          disabled={busy || !code.trim()}
          className="h-12 w-full rounded-xl border border-cyan-500/40 bg-cyan-950/40 font-mono text-sm tracking-[0.25em] text-cyan-300 font-semibold transition hover:bg-cyan-900/60 hover:text-white disabled:opacity-40"
        >
          {busy ? 'VERIFYING...' : 'AUTHENTICATE'}
        </button>
        <p className="pt-2 text-center font-mono text-[10px] leading-relaxed text-cyan-800">
          TRIAL BUILD — access code <span className="text-cyan-500">1955</span>
          <br />
          (set JARVIS_ADMIN_CODE env to change)
        </p>
      </div>
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
