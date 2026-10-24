import { useEffect, useRef } from 'react';
export type { OrbState } from './jarvisPersona';
import type { OrbState } from './jarvisPersona';

const STATE_COLORS: Record<OrbState, string> = {
  boot: '#0ea5b7',
  idle: '#22d3ee',
  listening: '#2ff3a6',
  thinking: '#fbbf24',
  speaking: '#38bdf8',
  alert: '#ff2d40',
};

const STATE_LABELS: Record<OrbState, string> = {
  boot: 'INITIALIZING',
  idle: 'STANDBY',
  listening: 'LISTENING',
  thinking: 'PROCESSING',
  speaking: 'RESPONDING',
  alert: 'AUTHORIZATION REQUIRED',
};

export function orbColor(state: OrbState): string {
  return STATE_COLORS[state] ?? STATE_COLORS.idle;
}

export function orbLabel(state: OrbState): string {
  return STATE_LABELS[state] ?? STATE_LABELS.idle;
}

interface OrbProps {
  state: OrbState;
  size?: number;
  onClick?: () => void;
  className?: string;
}

export function ArcReactorOrb({ state, size = 180, onClick, className = '' }: OrbProps) {
  const color = STATE_COLORS[state] ?? STATE_COLORS.idle;
  const booting = state === 'boot';

  return (
    <div
      onClick={onClick}
      className={`jarvis-orb relative select-none cursor-pointer inline-flex items-center justify-center ${className}`}
      data-state={state}
      style={{ width: size, height: size, ['--orb' as string]: color }}
      title={`JARVIS Core: ${orbLabel(state)}`}
      aria-label={`JARVIS Core: ${orbLabel(state)}`}
    >
      <style>{`
        @keyframes orb-breathe {
          0%, 100% { transform: scale(1); opacity: 0.85; }
          50% { transform: scale(1.045); opacity: 1; }
        }
        @keyframes orb-speak {
          0%, 100% { transform: scale(0.96); }
          50% { transform: scale(1.06); }
        }
        @keyframes orb-alert {
          0%, 100% { transform: scale(1); box-shadow: 0 0 30px rgba(255, 45, 64, 0.75); }
          50% { transform: scale(1.08); box-shadow: 0 0 46px rgba(255, 45, 64, 0.95); }
        }
        @keyframes spin-cw {
          to { transform: rotate(360deg); }
        }
        @keyframes spin-ccw {
          to { transform: rotate(-360deg); }
        }
        @keyframes boot-flicker {
          0% { opacity: 0.15; }
          50% { opacity: 0.5; }
          100% { opacity: 0.15; }
        }
        .orb-halo {
          position: absolute;
          inset: -18%;
          border-radius: 9999px;
          background: radial-gradient(circle, color-mix(in srgb, var(--orb) 30%, transparent) 0%, transparent 62%);
          filter: blur(14px);
          animation: orb-breathe 3.4s ease-in-out infinite;
          transition: background 0.5s ease;
        }
        .orb-ring {
          position: absolute;
          inset: 0;
          width: 100%;
          height: 100%;
        }
        .orb-ring-outer {
          animation: spin-cw 14s linear infinite;
        }
        .orb-ring-mid {
          animation: spin-ccw 9s linear infinite;
        }
        .orb-ring-inner {
          animation: spin-cw 5.5s linear infinite;
        }
        .jarvis-orb[data-state="boot"] .orb-ring-inner {
          animation-duration: 1.6s;
        }
        .jarvis-orb[data-state="listening"] .orb-ring-outer {
          animation-duration: 6s;
        }
        .jarvis-orb[data-state="alert"] .orb-ring-outer {
          animation-duration: 3s;
        }
        .orb-core {
          position: absolute;
          inset: 30%;
          border-radius: 9999px;
          background: radial-gradient(circle at 42% 38%, #ffffff 0%, var(--orb) 34%, rgba(2, 12, 24, 0.9) 78%);
          box-shadow:
            0 0 26px color-mix(in srgb, var(--orb) 65%, transparent),
            inset 0 0 18px color-mix(in srgb, var(--orb) 45%, transparent);
          animation: orb-breathe 2.8s ease-in-out infinite;
          transition: background 0.4s ease, box-shadow 0.4s ease;
        }
        .orb-core-inner {
          position: absolute;
          inset: 22%;
          border-radius: 9999px;
          background: radial-gradient(circle at 45% 40%, #ffffff 0%, color-mix(in srgb, var(--orb) 80%, white) 55%, transparent 100%);
          opacity: 0.9;
        }
        .orb-core-triangle {
          position: absolute;
          inset: 38%;
          clip-path: polygon(50% 8%, 93% 82%, 7% 82%);
          background: linear-gradient(160deg, rgba(255, 255, 255, 0.95), color-mix(in srgb, var(--orb) 70%, transparent));
          opacity: 0.55;
        }
        .jarvis-orb[data-state="speaking"] .orb-core {
          animation: orb-speak 0.55s ease-in-out infinite;
        }
        .jarvis-orb[data-state="listening"] .orb-core {
          animation: orb-speak 0.9s ease-in-out infinite;
        }
        .jarvis-orb[data-state="alert"] .orb-core {
          animation: orb-alert 0.8s ease-in-out infinite;
        }
        .orb-boot-flicker {
          position: absolute;
          inset: 0;
          border-radius: 9999px;
          background: color-mix(in srgb, var(--orb) 16%, transparent);
          animation: boot-flicker 0.9s steps(2, end) infinite;
        }
      `}</style>

      {/* ambient halo */}
      <div className="orb-halo" />

      {/* outer dashed ring */}
      <svg className="orb-ring orb-ring-outer" viewBox="0 0 200 200">
        <circle
          cx="100"
          cy="100"
          r="94"
          fill="none"
          stroke={color}
          strokeWidth="1.5"
          strokeDasharray="4 7"
          opacity="0.75"
        />
        <circle
          cx="100"
          cy="100"
          r="86"
          fill="none"
          stroke={color}
          strokeWidth="0.6"
          strokeDasharray="30 46"
          opacity="0.4"
        />
      </svg>

      {/* middle counter-rotating tick ring */}
      <svg className="orb-ring orb-ring-mid" viewBox="0 0 200 200">
        <circle
          cx="100"
          cy="100"
          r="72"
          fill="none"
          stroke={color}
          strokeWidth="4"
          strokeDasharray="2 18"
          opacity="0.55"
        />
      </svg>

      {/* inner arc segments */}
      <svg className="orb-ring orb-ring-inner" viewBox="0 0 200 200">
        <circle
          cx="100"
          cy="100"
          r="58"
          fill="none"
          stroke={color}
          strokeWidth="2.5"
          strokeDasharray="80 120"
          strokeLinecap="round"
          opacity="0.9"
        />
        <circle
          cx="100"
          cy="100"
          r="50"
          fill="none"
          stroke={color}
          strokeWidth="1"
          strokeDasharray="20 90"
          opacity="0.5"
        />
      </svg>

      {/* reactor core */}
      <div className="orb-core">
        <div className="orb-core-inner" />
        <div className="orb-core-triangle" />
      </div>

      {booting && <div className="orb-boot-flicker" />}
    </div>
  );
}

// ------------------------------------------------------------
// Real-time canvas waveform visualizer
// ------------------------------------------------------------
interface WaveformProps {
  state: OrbState;
  height?: number;
  barCount?: number;
}

export function LiveWaveform({
  state,
  height = 36,
  barCount = 32,
}: WaveformProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const rafRef = useRef<number>(0);
  const levelsRef = useRef<number[]>(new Array(barCount).fill(0.04));
  const stateRef = useRef<OrbState>(state);

  useEffect(() => {
    stateRef.current = state;
  }, [state]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let frame = 0;
    const draw = () => {
      frame++;
      const dpr = window.devicePixelRatio || 1;
      const w = canvas.clientWidth;
      const h = canvas.clientHeight;
      if (canvas.width !== w * dpr || canvas.height !== h * dpr) {
        canvas.width = w * dpr;
        canvas.height = h * dpr;
      }
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, w, h);

      const s = stateRef.current;
      const color = STATE_COLORS[s] ?? STATE_COLORS.idle;
      const levels = levelsRef.current;

      if (s === 'speaking') {
        for (let i = 0; i < barCount; i++) {
          const wave =
            0.35 +
            0.3 * Math.sin(frame * 0.12 + i * 0.55) +
            0.25 * Math.sin(frame * 0.25 + i * 1.3);
          const target = Math.abs(wave) * (0.75 + 0.25 * Math.sin(frame * 0.08));
          levels[i] = levels[i] * 0.7 + Math.max(0.06, target) * 0.3;
        }
      } else if (s === 'listening') {
        for (let i = 0; i < barCount; i++) {
          const wave = 0.25 + 0.2 * Math.sin(frame * 0.18 + i * 0.9);
          levels[i] = levels[i] * 0.75 + Math.max(0.05, wave) * 0.25;
        }
      } else if (s === 'thinking') {
        for (let i = 0; i < barCount; i++) {
          const wave = 0.15 + 0.12 * Math.sin(frame * 0.1 + i * 0.8) * Math.sin(frame * 0.05);
          levels[i] = levels[i] * 0.85 + Math.max(0.04, wave) * 0.15;
        }
      } else {
        for (let i = 0; i < barCount; i++) {
          const wave = 0.04 + 0.02 * Math.sin(frame * 0.05 + i * 0.35);
          levels[i] = levels[i] * 0.92 + wave * 0.08;
        }
      }

      const barW = w / barCount;
      const mid = h / 2;
      ctx.fillStyle = color;
      ctx.shadowColor = color;
      ctx.shadowBlur = 6;
      for (let i = 0; i < barCount; i++) {
        const lh = Math.max(2, levels[i] * (h * 0.9));
        const x = i * barW + barW * 0.2;
        const bw = barW * 0.6;
        ctx.globalAlpha = 0.35 + levels[i] * 0.65;
        ctx.fillRect(x, mid - lh / 2, bw, lh);
      }
      ctx.globalAlpha = 1;
      ctx.shadowBlur = 0;

      rafRef.current = requestAnimationFrame(draw);
    };

    rafRef.current = requestAnimationFrame(draw);
    return () => cancelAnimationFrame(rafRef.current);
  }, [barCount]);

  return (
    <canvas
      ref={canvasRef}
      className="w-full"
      style={{ height }}
      aria-hidden="true"
    />
  );
}
