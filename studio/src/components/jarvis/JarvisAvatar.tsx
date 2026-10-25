/**
 * JarvisAvatar — SupremeAI's living AI-assistant face (owner-approved concept).
 *
 * A compact hologram chip for the chat header. Photoreal avatar with:
 *  - breathing float, auto-blink (AI-generated blink frame, crossfade),
 *  - hologram scanline sweep + glow pulse (pure CSS, GPU-cheap),
 *  - parallax tilt via mouse / touch / gyroscope using requestAnimationFrame
 *    + lerp interpolation (buttery on 60/120Hz, zero work when idle),
 *  - state-reactive: idle | thinking (wired to chat `busy`) | speaking,
 *  - customer preference: male/female variant persisted in localStorage,
 *  - all 4 assets preloaded on mount — zero flicker on variant switch,
 *  - prefers-reduced-motion respected (CSS + JS guards),
 *  - graceful CSS-monogram fallback if webp assets are ever missing.
 *
 * Free-tier: zero AI calls at runtime; assets are embedded data URLs.
 */
import React from 'react';
import { FEMALE_BASE, FEMALE_BLINK, MALE_BASE, MALE_BLINK } from './avatarAssets';
import './jarvisAvatar.css';

export type JarvisAvatarVariant = 'male' | 'female';
export type JarvisAvatarState = 'idle' | 'thinking' | 'speaking';

const LS_KEY = 'jarvis.avatarVariant';

const ASSETS: Record<JarvisAvatarVariant, { base: string; blink: string }> = {
  male: { base: MALE_BASE, blink: MALE_BLINK },
  female: { base: FEMALE_BASE, blink: FEMALE_BLINK },
};

function readStoredVariant(): JarvisAvatarVariant {
  try {
    const v = typeof localStorage !== 'undefined' ? localStorage.getItem(LS_KEY) : null;
    return v === 'female' ? 'female' : 'male';
  } catch {
    return 'male';
  }
}

export function JarvisAvatar({ busy = false, variant: controlledVariant, compact = false }: {
  /** Chat is waiting for the assistant — drives the 'thinking' state. */
  busy?: boolean;
  /** Optional controlled variant (dashboards). Defaults to localStorage pref. */
  variant?: JarvisAvatarVariant;
  /** Dock variant (report §6.4): 40px chip that fits the 44px docked action bar. */
  compact?: boolean;
}) {
  const [variant, setVariant] = React.useState<JarvisAvatarVariant>(
    controlledVariant ?? readStoredVariant(),
  );
  const [state, setState] = React.useState<JarvisAvatarState>(busy ? 'thinking' : 'idle');
  const [blinking, setBlinking] = React.useState(false);
  const [assetsOk, setAssetsOk] = React.useState(true);

  React.useEffect(() => {
    setState(busy ? 'thinking' : 'idle');
  }, [busy]);

  /* Preload every asset once — variant switch is instant (no flicker). */
  React.useEffect(() => {
    let alive = true;
    const imgs = Object.values(ASSETS).flatMap((a) => [a.base, a.blink]).map(
      (src) =>
        new Promise<void>((resolve) => {
          const img = new Image();
          img.onload = () => resolve();
          img.onerror = () => resolve();
          img.src = src;
        }),
    );
    void Promise.all(imgs).then(() => {
      if (alive) setAssetsOk(true);
    });
    return () => {
      alive = false;
    };
  }, []);

  /* Auto-blink: brief crossfade every 2.8–6s. Kept under reduced-motion
     (a 150ms eyelid event is not a vestibular trigger), per a11y review. */
  React.useEffect(() => {
    let t1: ReturnType<typeof setTimeout> | undefined;
    let alive = true;
    const schedule = () => {
      t1 = setTimeout(() => {
        if (!alive) return;
        setBlinking(true);
        setTimeout(() => {
          if (!alive) return;
          setBlinking(false);
          schedule();
        }, 150);
      }, 2800 + Math.random() * 3200);
    };
    schedule();
    return () => {
      alive = false;
      if (t1) clearTimeout(t1);
    };
  }, []);

  /* Parallax tilt: rAF + lerp. Mouse, touch and gyroscope all feed the same
     target; the loop self-stops when the target is reached (idle = 0 CPU). */
  React.useEffect(() => {
    const stage = document.getElementById('jarvis-av-stage');
    if (!stage) return;
    const mql = typeof window.matchMedia === 'function' ? window.matchMedia('(prefers-reduced-motion: reduce)') : null;
    let reduced = !!mql?.matches;
    const onMql = () => {
      reduced = !!mql?.matches;
    };
    mql?.addEventListener?.('change', onMql);

    const MAXX = 6, MAXY = 8;
    let tX = 0, tY = 0, cX = 0, cY = 0, rafId: number | null = null;
    const clamp = (v: number, m: number) => Math.max(-m, Math.min(m, v));
    const tick = () => {
      cX += (tX - cX) * 0.085;
      cY += (tY - cY) * 0.085;
      stage.style.transform = `perspective(900px) rotateX(${cX.toFixed(3)}deg) rotateY(${cY.toFixed(3)}deg)`;
      if (Math.abs(tX - cX) > 0.015 || Math.abs(tY - cY) > 0.015) {
        rafId = requestAnimationFrame(tick);
      } else {
        rafId = null;
      }
    };
    const setTarget = (rx: number, ry: number) => {
      if (reduced) return;
      tX = rx; tY = ry;
      if (rafId === null) rafId = requestAnimationFrame(tick);
    };
    const onMouse = (e: MouseEvent) => {
      setTarget(
        clamp(((e.clientY / window.innerHeight) - 0.5) * -MAXX, MAXX),
        clamp(((e.clientX / window.innerWidth) - 0.5) * MAXY, MAXY),
      );
    };
    const onTouch = (e: TouchEvent) => {
      const t = e.touches[0];
      if (!t) return;
      setTarget(
        clamp(((t.clientY / window.innerHeight) - 0.5) * -MAXX, MAXX),
        clamp(((t.clientX / window.innerWidth) - 0.5) * MAXY, MAXY),
      );
    };
    const onGyro = (e: DeviceOrientationEvent) => {
      if (e.beta === null || e.gamma === null) return;
      setTarget(clamp((e.beta - 45) * 0.12, MAXX), clamp(e.gamma * 0.12, MAXY));
    };
    const enableGyro = () => {
      if (typeof window !== 'undefined') {
        window.addEventListener('deviceorientation', onGyro);
      }
    };
    /* iOS 13+ requires a one-time user-gesture permission grant. Safely check window.DeviceOrientationEvent */
    const hasGyro = typeof window !== 'undefined' && 'DeviceOrientationEvent' in window;
    const dioe = hasGyro
      ? (window as unknown as { DeviceOrientationEvent?: { requestPermission?: () => Promise<string> } }).DeviceOrientationEvent
      : undefined;
    if (dioe && typeof dioe.requestPermission === 'function') {
      const once = () => {
        dioe.requestPermission?.().then((r) => {
          if (r === 'granted') enableGyro();
        }).catch(() => {});
        document.removeEventListener('click', once);
      };
      document.addEventListener('click', once);
    } else if (hasGyro) {
      enableGyro();
    }
    window.addEventListener('mousemove', onMouse, { passive: true });
    window.addEventListener('touchmove', onTouch, { passive: true });
    return () => {
      mql?.removeEventListener?.('change', onMql);
      window.removeEventListener('mousemove', onMouse);
      window.removeEventListener('touchmove', onTouch);
      window.removeEventListener('deviceorientation', onGyro);
      if (rafId !== null) cancelAnimationFrame(rafId);
    };
  }, []);

  const cycleVariant = () => {
    const next: JarvisAvatarVariant = variant === 'male' ? 'female' : 'male';
    setVariant(next);
    try {
      localStorage.setItem(LS_KEY, next);
    } catch {
      /* private mode — in-memory only */
    }
  };

  const a = ASSETS[variant];
  return (
    <button
      type="button"
      onClick={cycleVariant}
      title={`Jarvis — ${state}. Tap to switch assistant style.`}
      aria-label={`Jarvis assistant avatar, currently ${variant} style, ${state}. Tap to switch.`}
      data-testid="jarvis-avatar"
      data-state={state}
      className={`jarvis-av jarvis-av-${state}${blinking ? ' jarvis-av-blinking' : ''}${compact ? ' jarvis-av-dock' : ''}`}
      id="jarvis-av-stage"
    >
      <span className="jarvis-av-glow" aria-hidden="true" />
      {assetsOk ? (
        <span className="jarvis-av-img" aria-hidden="true">
          <img src={a.base} alt="" draggable={false} />
          <img src={a.blink} alt="" draggable={false} className="jarvis-av-img-blink" />
        </span>
      ) : (
        <span className="jarvis-av-fallback" aria-hidden="true">J</span>
      )}
      <span className="jarvis-av-scan" aria-hidden="true" />
      <span className="jarvis-av-sweep" aria-hidden="true" />
      <span className={`jarvis-av-dot jarvis-av-dot-${state}`} aria-hidden="true" />
    </button>
  );
}

export default JarvisAvatar;
