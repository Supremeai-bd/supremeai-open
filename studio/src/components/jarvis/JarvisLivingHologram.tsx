import React, { useRef, useEffect, useState, useCallback } from 'react';
import { 
  Mic, MicOff, Volume2, VolumeX, Maximize2, Minimize2, X, Sparkles, 
  Terminal, ShieldCheck, Activity, Cpu, Zap, Radio, PhoneOff, 
  Play, RefreshCw, Send, CheckCircle2, AlertTriangle, ArrowUpRight,
  Smile, UserCheck, Heart
} from 'lucide-react';

export type HoloState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'executing' | 'celebrating';

interface JarvisLivingHologramProps {
  isOpen: boolean;
  onClose: () => void;
  language?: 'bn' | 'en';
  personaName?: string;
  onSendMessage?: (msg: string) => void;
  onJumpToPreview?: () => void;
}

/**
 * JarvisLivingHologram:
 * Image-free pure mathematical 3D cybernetic mesh hologram with:
 * - Natural saccadic eye micro-movement & gaze tracking
 * - Randomized biological blinking (2-4s)
 * - Phonetic speech-reactive lip-sync visemes (mouth opening, curvature)
 * - Head nod & tilt physics with Spring dynamics
 * - Volumetric depth-grid, holographic scanlines & starlight aura
 */
export const JarvisLivingHologram: React.FC<JarvisLivingHologramProps> = ({
  isOpen,
  onClose,
  language = 'bn',
  personaName = 'Jarvis Cyber Core',
  onSendMessage,
  onJumpToPreview,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [holoState, setHoloState] = useState<HoloState>('idle');
  const [isMicActive, setIsMicActive] = useState<boolean>(false);
  const [isMuted, setIsMuted] = useState<boolean>(false);
  const [subtitles, setSubtitles] = useState<string>(
    language === 'bn' 
      ? 'অনলাইন এবং সম্পূর্ণ জীবন্ত, স্যার। আপনার চিন্তাভাবনা আমাকে বলুন, আমরা একসাথে গড়ে তুলব।'
      : 'Online and fully conscious, sir. Speak your thoughts and we shall build together.'
  );
  const [inputMsg, setInputMsg] = useState<string>('');
  const [speechVolume, setSpeechVolume] = useState<number>(0);

  // Mouse & Gaze Tracking
  const mouse = useRef({ x: 0, y: 0, targetX: 0, targetY: 0 });
  const headRotation = useRef({ x: 0, y: 0, targetX: 0, targetY: 0 });
  const eyeGaze = useRef({ x: 0, y: 0, targetX: 0, targetY: 0, saccadeTimer: 0 });
  
  // Biological Blinking
  const blink = useRef({ value: 1, timer: 0, nextBlink: 140, isBlinking: false });

  // Lip-Sync Visemes (Mouth Openness & Curve)
  const lipSync = useRef({ open: 0, width: 1, targetOpen: 0 });

  // Floating particles
  const particles = useRef<Array<{ x: number; y: number; z: number; speed: number; alpha: number }>>([]);

  // Setup initial particles
  useEffect(() => {
    const pArr = [];
    for (let i = 0; i < 90; i++) {
      pArr.push({
        x: (Math.random() - 0.5) * 800,
        y: (Math.random() - 0.5) * 600,
        z: Math.random() * 400,
        speed: 0.3 + Math.random() * 0.7,
        alpha: 0.2 + Math.random() * 0.7,
      });
    }
    particles.current = pArr;
  }, []);

  // Track Mouse Movement for Head Tilt and Gaze
  useEffect(() => {
    const handleMouseMove = (e: MouseEvent) => {
      const width = window.innerWidth;
      const height = window.innerHeight;
      mouse.current.targetX = (e.clientX - width / 2) / (width / 2); // -1 to 1
      mouse.current.targetY = (e.clientY - height / 2) / (height / 2); // -1 to 1
    };
    window.addEventListener('mousemove', handleMouseMove);
    return () => window.removeEventListener('mousemove', handleMouseMove);
  }, []);

  // Interactive Voice / Simulated Speech Visemes
  useEffect(() => {
    let interval: NodeJS.Timeout;
    if (holoState === 'speaking') {
      interval = setInterval(() => {
        // Natural speech phoneme oscillations
        const energy = 0.3 + Math.random() * 0.7;
        lipSync.current.targetOpen = energy;
        setSpeechVolume(Math.floor(energy * 100));
      }, 90);
    } else {
      lipSync.current.targetOpen = 0;
      setSpeechVolume(0);
    }
    return () => clearInterval(interval);
  }, [holoState]);

  // Main 3D Canvas Rendering Loop
  useEffect(() => {
    if (!isOpen) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animId: number;
    let time = 0;

    const render = () => {
      time += 0.02;

      // Ensure crisp high-DPI canvas
      if (canvas.width !== canvas.clientWidth || canvas.height !== canvas.clientHeight) {
        canvas.width = canvas.clientWidth;
        canvas.height = canvas.clientHeight;
      }

      const w = canvas.width;
      const h = canvas.height;
      const cx = w / 2;
      const cy = h / 2 - 20;

      ctx.clearRect(0, 0, w, h);

      // ─── 1. Deep Space Obsidian Hologram Gradient ───
      const bgGrad = ctx.createRadialGradient(cx, cy, 20, cx, cy, Math.max(w, h) * 0.7);
      bgGrad.addColorStop(0, '#060d1f');
      bgGrad.addColorStop(0.5, '#020612');
      bgGrad.addColorStop(1, '#000207');
      ctx.fillStyle = bgGrad;
      ctx.fillRect(0, 0, w, h);

      // ─── 2. State Color Themes ───
      let primaryColor = '0, 229, 255'; // Cyan Hologram (Idle/Normal)
      let accentColor = '99, 102, 241';  // Indigo
      if (holoState === 'listening') {
        primaryColor = '255, 75, 110';   // Coral / Pinkish Red pulse
        accentColor = '244, 63, 94';
      } else if (holoState === 'thinking') {
        primaryColor = '251, 191, 36';   // Amber gold synapse
        accentColor = '217, 119, 6';
      } else if (holoState === 'speaking') {
        primaryColor = '16, 185, 129';   // Emerald / Living energy
        accentColor = '52, 211, 153';
      } else if (holoState === 'celebrating') {
        primaryColor = '168, 85, 247';   // Purple triumphant glow
        accentColor = '236, 72, 153';
      }

      // ─── 3. Animated Floating Starlight & Neural Dust ───
      particles.current.forEach((p) => {
        p.y -= p.speed;
        if (p.y < -300) p.y = 300;
        const pScale = 300 / (300 + p.z);
        const px = cx + p.x * pScale;
        const py = cy + p.y * pScale;
        ctx.fillStyle = `rgba(${primaryColor}, ${p.alpha * 0.6})`;
        ctx.beginPath();
        ctx.arc(px, py, 1.2 * pScale, 0, Math.PI * 2);
        ctx.fill();
      });

      // ─── 4. Head Tilt & Saccadic Eye Physics ───
      // Spring lerp head towards mouse cursor
      headRotation.current.x += (mouse.current.targetX * 0.25 - headRotation.current.x) * 0.05;
      headRotation.current.y += (mouse.current.targetY * 0.18 - headRotation.current.y) * 0.05;

      // Biological Saccade (quick tiny eye movements)
      eyeGaze.current.saccadeTimer++;
      if (eyeGaze.current.saccadeTimer > 80 + Math.random() * 120) {
        eyeGaze.current.saccadeTimer = 0;
        eyeGaze.current.targetX = (Math.random() - 0.5) * 6;
        eyeGaze.current.targetY = (Math.random() - 0.5) * 4;
      }
      eyeGaze.current.x += (eyeGaze.current.targetX - eyeGaze.current.x) * 0.1;
      eyeGaze.current.y += (eyeGaze.current.targetY - eyeGaze.current.y) * 0.1;

      // Natural Eye Blink Timer
      blink.current.timer++;
      if (blink.current.timer > blink.current.nextBlink) {
        blink.current.isBlinking = true;
        blink.current.value -= 0.25;
        if (blink.current.value <= 0.05) {
          blink.current.value = 0.05;
          blink.current.timer = 0;
          blink.current.nextBlink = 100 + Math.floor(Math.random() * 160); // 2-4s random blink
          blink.current.isBlinking = false;
        }
      } else if (blink.current.value < 1) {
        blink.current.value += 0.25;
        if (blink.current.value > 1) blink.current.value = 1;
      }

      // Smooth Lip-sync Mouth Open
      lipSync.current.open += (lipSync.current.targetOpen - lipSync.current.open) * 0.25;

      // Center offset from head tilt
      const hx = cx + headRotation.current.x * 60;
      const hy = cy + headRotation.current.y * 40;

      // ─── 5. Gyroscopic Hologram Rings (Neural Halo) ───
      ctx.save();
      ctx.translate(hx, hy);
      for (let r = 0; r < 3; r++) {
        const ringAngle = time * (r % 2 === 0 ? 0.8 : -0.6) + r * 1.5;
        const radius = 170 + r * 18;
        ctx.beginPath();
        ctx.ellipse(0, 0, radius, radius * 0.35, ringAngle, 0, Math.PI * 2);
        ctx.strokeStyle = `rgba(${primaryColor}, ${0.15 + r * 0.08})`;
        ctx.lineWidth = 1.2;
        ctx.stroke();

        // Little data nodes on the rings
        const dotX = Math.cos(ringAngle * 2) * radius;
        const dotY = Math.sin(ringAngle * 2) * radius * 0.35;
        ctx.fillStyle = `rgba(${primaryColor}, 0.9)`;
        ctx.beginPath();
        ctx.arc(dotX, dotY, 2.5, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.restore();

      // ─── 6. Mathematical 3D Facial Mesh (Clean Wireframe Silhouette) ───
      const headWidth = 90;
      const headHeight = 120;

      // Head Outer Holographic Glow
      const headGlow = ctx.createRadialGradient(hx, hy - 10, 10, hx, hy, 130);
      headGlow.addColorStop(0, `rgba(${primaryColor}, 0.2)`);
      headGlow.addColorStop(0.6, `rgba(${accentColor}, 0.08)`);
      headGlow.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = headGlow;
      ctx.beginPath();
      ctx.ellipse(hx, hy, headWidth * 1.3, headHeight * 1.2, headRotation.current.x * 0.1, 0, Math.PI * 2);
      ctx.fill();

      // Draw Volumetric Contour Lines (Head Geometry)
      ctx.lineWidth = 1.2;
      for (let lat = -4; lat <= 4; lat++) {
        const latRatio = lat / 5;
        const latY = hy + latRatio * headHeight;
        const latRadius = Math.sqrt(Math.max(0, 1 - latRatio * latRatio)) * headWidth;

        ctx.strokeStyle = `rgba(${primaryColor}, ${0.2 + (1 - Math.abs(latRatio)) * 0.3})`;
        ctx.beginPath();
        ctx.ellipse(
          hx + headRotation.current.x * 15 * (1 - Math.abs(latRatio)),
          latY,
          latRadius,
          latRadius * 0.3,
          headRotation.current.x * 0.15,
          0,
          Math.PI * 2
        );
        ctx.stroke();
      }

      // Vertical Cranium Meridians
      for (let lon = -3; lon <= 3; lon++) {
        const lonRatio = lon / 4;
        const lonX = hx + lonRatio * headWidth + headRotation.current.x * 25;
        ctx.strokeStyle = `rgba(${primaryColor}, 0.18)`;
        ctx.beginPath();
        ctx.ellipse(
          lonX,
          hy,
          Math.abs(lonRatio) * 15 + 4,
          headHeight,
          0,
          Math.PI * 0.2,
          Math.PI * 0.8
        );
        ctx.stroke();
      }

      // ─── 7. LIVING EYES (Micro-Blink + Natural Gaze Tracking) ───
      const eyeSpacing = 32;
      const eyeY = hy - 10 + headRotation.current.y * 12;

      [-1, 1].forEach((side) => {
        const eyeX = hx + side * eyeSpacing + headRotation.current.x * 18;
        const blinkH = Math.max(1, 12 * blink.current.value);

        // Eye Socket Ethereal Glow
        const eyeGlow = ctx.createRadialGradient(eyeX, eyeY, 1, eyeX, eyeY, 20);
        eyeGlow.addColorStop(0, `rgba(${primaryColor}, 0.8)`);
        eyeGlow.addColorStop(0.5, `rgba(${accentColor}, 0.3)`);
        eyeGlow.addColorStop(1, 'rgba(0,0,0,0)');
        ctx.fillStyle = eyeGlow;
        ctx.beginPath();
        ctx.ellipse(eyeX, eyeY, 16, blinkH + 4, 0, 0, Math.PI * 2);
        ctx.fill();

        // Eye Outline
        ctx.strokeStyle = `rgba(${primaryColor}, 0.9)`;
        ctx.lineWidth = 1.8;
        ctx.beginPath();
        ctx.ellipse(eyeX, eyeY, 14, blinkH, 0, 0, Math.PI * 2);
        ctx.stroke();

        // Pupil / Iris with Gaze Tracking
        if (blink.current.value > 0.2) {
          const pupilX = eyeX + eyeGaze.current.x + mouse.current.targetX * 3;
          const pupilY = eyeY + eyeGaze.current.y + mouse.current.targetY * 2;

          ctx.fillStyle = '#ffffff';
          ctx.beginPath();
          ctx.arc(pupilX, pupilY, 3.5, 0, Math.PI * 2);
          ctx.fill();

          // Outer Iris ring
          ctx.strokeStyle = `rgba(${primaryColor}, 0.95)`;
          ctx.lineWidth = 1.2;
          ctx.beginPath();
          ctx.arc(pupilX, pupilY, 6.5, 0, Math.PI * 2);
          ctx.stroke();
        }
      });

      // ─── 8. LIVING LIPS & MOUTH (Phonetic Viseme Movements) ───
      const mouthY = hy + 48 + headRotation.current.y * 15;
      const mouthX = hx + headRotation.current.x * 12;
      const mouthOpenH = Math.max(1.5, lipSync.current.open * 16);
      const mouthWidth = 24 + lipSync.current.open * 8;

      // Mouth Aperture
      ctx.strokeStyle = `rgba(${primaryColor}, 0.95)`;
      ctx.lineWidth = 2;
      ctx.beginPath();
      // Upper lip
      ctx.moveTo(mouthX - mouthWidth, mouthY);
      ctx.quadraticCurveTo(mouthX, mouthY - mouthOpenH * 0.4 - 2, mouthX + mouthWidth, mouthY);
      // Lower lip
      ctx.quadraticCurveTo(mouthX, mouthY + mouthOpenH + 2, mouthX - mouthWidth, mouthY);
      ctx.stroke();

      // Voice Acoustic Glow inside mouth when speaking
      if (lipSync.current.open > 0.1) {
        ctx.fillStyle = `rgba(${primaryColor}, ${lipSync.current.open * 0.5})`;
        ctx.fill();
      }

      // ─── 9. ARC REACTOR CYBER CORE (Chest Heartbeat) ───
      const chestY = hy + 155;
      const chestGrad = ctx.createRadialGradient(hx, chestY, 2, hx, chestY, 40);
      chestGrad.addColorStop(0, `rgba(${primaryColor}, 0.95)`);
      chestGrad.addColorStop(0.4, `rgba(${accentColor}, 0.4)`);
      chestGrad.addColorStop(1, 'rgba(0,0,0,0)');
      ctx.fillStyle = chestGrad;
      ctx.beginPath();
      ctx.arc(hx, chestY, 45, 0, Math.PI * 2);
      ctx.fill();

      // Chest Geometric Ticks
      ctx.strokeStyle = `rgba(${primaryColor}, 0.7)`;
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.arc(hx, chestY, 28, 0, Math.PI * 2);
      ctx.stroke();

      // Horizontal Scanline Sweep (Pure Cyber Sci-Fi Texture)
      const scanY = (time * 120) % h;
      ctx.fillStyle = `rgba(${primaryColor}, 0.04)`;
      ctx.fillRect(0, scanY, w, 3);

      animId = requestAnimationFrame(render);
    };

    render();
    return () => cancelAnimationFrame(animId);
  }, [isOpen, holoState]);

  if (!isOpen) return null;

  const handleSimulateTalk = (text: string, state: HoloState = 'speaking') => {
    setHoloState(state);
    setSubtitles(text);
    setTimeout(() => {
      setHoloState('idle');
    }, 4500);
  };

  const handleSendPrompt = (e: React.FormEvent) => {
    e.preventDefault();
    if (!inputMsg.trim()) return;
    const msg = inputMsg;
    setInputMsg('');
    setSubtitles(`"${msg}"`);
    setHoloState('thinking');
    if (onSendMessage) onSendMessage(msg);

    // Simulate intelligent response after thinking
    setTimeout(() => {
      handleSimulateTalk(
        language === 'bn'
          ? `অবশ্যই, স্যার! আমি আর্কিটেকচার বিশ্লেষণ করে আপনার সিস্টেমের জন্য সর্বোচ্চ কোড তৈরি করছি।`
          : `Affirmative, sir! Analyzing project requirements and deploying optimal code solution.`
      );
    }, 1800);
  };

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-slate-950/95 backdrop-blur-xl animate-fadeIn overflow-hidden select-none font-sans">
      {/* ─── Top Control Bar ─── */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-white/[0.08] bg-slate-900/40 z-20">
        <div className="flex items-center gap-3">
          <div className="relative flex items-center justify-center w-8 h-8 rounded-xl bg-cyan-950/80 border border-cyan-500/40 text-cyan-300 shadow-[0_0_15px_rgba(6,182,212,0.3)]">
            <Sparkles className="w-4 h-4 animate-pulse" />
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-bold text-white tracking-wide">{personaName}</h2>
              <span className="flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-mono bg-emerald-950/80 text-emerald-400 border border-emerald-800">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
                LIVING 3D HOLO
              </span>
            </div>
            <p className="text-[11px] text-slate-400">
              {holoState === 'idle' && (language === 'bn' ? 'মনোযোগ দিয়ে আপনার কথা শুনছি' : 'Attentive & Conscious')}
              {holoState === 'listening' && (language === 'bn' ? 'ভয়েস শুনছি...' : 'Awaiting your voice...')}
              {holoState === 'thinking' && (language === 'bn' ? 'গভীর বিশ্লেষণ চলছে...' : 'Synthesizing neural logic...')}
              {holoState === 'speaking' && (language === 'bn' ? 'কথা বলছি...' : 'Articulating response...')}
            </p>
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2">
          {onJumpToPreview && (
            <button
              onClick={onJumpToPreview}
              className="px-3 py-1.5 text-xs font-medium text-slate-300 hover:text-white bg-slate-800/80 hover:bg-slate-700/80 rounded-xl border border-white/10 transition-all flex items-center gap-1.5 shadow-sm"
            >
              <span>{language === 'bn' ? 'স্প্লিট প্রিভিউতে যান' : 'Split Workspace'}</span>
              <ArrowUpRight className="w-3.5 h-3.5 text-cyan-400" />
            </button>
          )}

          <button
            onClick={onClose}
            className="p-2 text-slate-400 hover:text-white hover:bg-white/10 rounded-xl transition-colors"
            title="End Video Call"
          >
            <PhoneOff className="w-4 h-4 text-red-400" />
          </button>
        </div>
      </div>

      {/* ─── Main Living 3D Hologram Stage ─── */}
      <div className="relative flex-1 w-full h-full flex items-center justify-center overflow-hidden">
        {/* Living Canvas */}
        <canvas ref={canvasRef} className="absolute inset-0 w-full h-full cursor-crosshair" />

        {/* Emotional State Indicator Pills */}
        <div className="absolute top-6 left-6 z-10 flex flex-wrap gap-2">
          <button
            onClick={() => handleSimulateTalk('আমি সম্পূর্ণ প্রস্তুত, স্যার। বলুন কোন ফিচারটি তৈরি করব?', 'speaking')}
            className="px-2.5 py-1 text-[11px] font-mono rounded-lg bg-cyan-950/60 border border-cyan-800/60 text-cyan-300 hover:bg-cyan-900/60 transition"
          >
            🗣️ Talk
          </button>
          <button
            onClick={() => {
              setHoloState('thinking');
              setSubtitles(language === 'bn' ? 'সিস্টেম আর্কিটেকচার অপটিমাইজ করছি...' : 'Optimizing system neural graph...');
            }}
            className="px-2.5 py-1 text-[11px] font-mono rounded-lg bg-amber-950/60 border border-amber-800/60 text-amber-300 hover:bg-amber-900/60 transition"
          >
            🧠 Think
          </button>
          <button
            onClick={() => {
              setHoloState('celebrating');
              setSubtitles(language === 'bn' ? 'দারুণ! সবগুলো টেস্ট ১০০% সফলভাবে সম্পন্ন হয়েছে!' : 'Brilliant! All tests and benchmarks passed with zero anomalies!');
            }}
            className="px-2.5 py-1 text-[11px] font-mono rounded-lg bg-purple-950/60 border border-purple-800/60 text-purple-300 hover:bg-purple-900/60 transition"
          >
            🎉 Celebrate
          </button>
        </div>

        {/* Live Audio Visualizer Bar */}
        {holoState === 'speaking' && (
          <div className="absolute bottom-28 z-10 flex items-center gap-1.5 px-4 py-2 rounded-full bg-slate-900/80 border border-cyan-500/40 backdrop-blur-md">
            <Volume2 className="w-4 h-4 text-cyan-400 animate-pulse" />
            <div className="flex items-center gap-1 h-3">
              {[40, 80, 60, 100, 70, 90, 50, 85].map((val, i) => (
                <div
                  key={i}
                  className="w-1 bg-cyan-400 rounded-full transition-all duration-75"
                  style={{
                    height: `${Math.max(3, (val * speechVolume) / 100)}px`,
                  }}
                />
              ))}
            </div>
          </div>
        )}

        {/* ─── Dynamic Subtitles / Speech Bubble ─── */}
        <div className="absolute bottom-16 inset-x-4 max-w-2xl mx-auto z-10 text-center animate-slideUp">
          <div className="inline-block px-6 py-3 rounded-2xl bg-slate-900/80 border border-white/10 backdrop-blur-xl shadow-2xl text-slate-100 text-sm font-medium leading-relaxed">
            {subtitles}
          </div>
        </div>
      </div>

      {/* ─── Bottom Interactive Communication Dock ─── */}
      <div className="p-4 sm:p-5 border-t border-white/[0.08] bg-slate-900/50 backdrop-blur-xl z-20">
        <div className="max-w-2xl mx-auto flex items-center gap-3">
          {/* Mic Toggle Button */}
          <button
            onClick={() => {
              const nextState = !isMicActive;
              setIsMicActive(nextState);
              if (nextState) {
                setHoloState('listening');
                setSubtitles(language === 'bn' ? 'আমি শুনছি, বলুন স্যার...' : 'Listening attentively, please speak...');
              } else {
                setHoloState('idle');
              }
            }}
            className={`p-3 rounded-2xl transition-all shadow-lg flex items-center justify-center ${
              isMicActive
                ? 'bg-rose-600 text-white shadow-rose-600/40 scale-105 animate-pulse'
                : 'bg-slate-800 text-slate-300 hover:text-white hover:bg-slate-700'
            }`}
            title="Toggle Live Voice Call"
          >
            {isMicActive ? <Mic className="w-5 h-5" /> : <MicOff className="w-5 h-5" />}
          </button>

          {/* Quick Chat Input */}
          <form onSubmit={handleSendPrompt} className="flex-1 flex items-center gap-2">
            <input
              type="text"
              value={inputMsg}
              onChange={(e) => setInputMsg(e.target.value)}
              placeholder={
                language === 'bn'
                  ? 'কথা বলুন অথবা সরাসরি কমান্ড লিখুন (যেমন: এই পেজে একটি ডার্ক থিম যোগ করো)...'
                  : 'Speak or type any directive (e.g. Add a glassmorphism navbar to this preview)...'
              }
              className="flex-1 px-4 py-2.5 rounded-2xl bg-slate-950/80 border border-white/10 text-white placeholder-slate-500 text-xs focus:outline-none focus:border-cyan-500 transition-colors"
            />
            <button
              type="submit"
              disabled={!inputMsg.trim()}
              className="p-2.5 rounded-2xl bg-cyan-600 hover:bg-cyan-500 disabled:opacity-40 disabled:cursor-not-allowed text-white transition-colors"
            >
              <Send className="w-4 h-4" />
            </button>
          </form>

          {/* End Call Button */}
          <button
            onClick={onClose}
            className="px-4 py-2.5 rounded-2xl bg-rose-600/20 hover:bg-rose-600 text-rose-300 hover:text-white border border-rose-500/30 transition-all text-xs font-semibold flex items-center gap-2"
          >
            <PhoneOff className="w-4 h-4" />
            <span className="hidden sm:inline">{language === 'bn' ? 'কল সমাপ্ত' : 'End Call'}</span>
          </button>
        </div>
      </div>
    </div>
  );
};
