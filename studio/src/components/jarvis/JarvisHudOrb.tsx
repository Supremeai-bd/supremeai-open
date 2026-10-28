import React, { useRef, useEffect } from 'react';
import { Mic, Volume2, Sparkles, Terminal, Activity } from 'lucide-react';

export type JarvisState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'executing';

interface JarvisHudOrbProps {
  state: JarvisState;
  onToggleListen: () => void;
  language: 'bn' | 'en';
  isListening: boolean;
}

export const JarvisHudOrb: React.FC<JarvisHudOrbProps> = ({
  state,
  onToggleListen,
  language,
  isListening,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    let angle = 0;

    const render = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      const centerX = canvas.width / 2;
      const centerY = canvas.height / 2;

      // Color scheme based on state
      let primaryColor = 'rgba(99, 102, 241, '; // Indigo (default)
      let glowColor = 'rgba(129, 140, 248, 0.4)';
      let speed = 0.02;

      if (state === 'listening') {
        primaryColor = 'rgba(239, 68, 68, '; // Red/Coral pulse
        glowColor = 'rgba(248, 113, 113, 0.6)';
        speed = 0.05;
      } else if (state === 'thinking') {
        primaryColor = 'rgba(245, 158, 11, '; // Amber gold
        glowColor = 'rgba(251, 191, 36, 0.5)';
        speed = 0.04;
      } else if (state === 'speaking') {
        primaryColor = 'rgba(16, 185, 129, '; // Emerald green
        glowColor = 'rgba(52, 211, 153, 0.6)';
        speed = 0.035;
      } else if (state === 'executing') {
        primaryColor = 'rgba(59, 130, 246, '; // Electric blue
        glowColor = 'rgba(96, 165, 250, 0.6)';
        speed = 0.06;
      }

      // 1. Central Core Glow
      const coreGrad = ctx.createRadialGradient(centerX, centerY, 5, centerX, centerY, 55);
      coreGrad.addColorStop(0, primaryColor + '0.9)');
      coreGrad.addColorStop(0.4, primaryColor + '0.4)');
      coreGrad.addColorStop(1, 'rgba(15, 23, 42, 0)');

      ctx.fillStyle = coreGrad;
      ctx.beginPath();
      ctx.arc(centerX, centerY, 60, 0, Math.PI * 2);
      ctx.fill();

      // 2. Arc Reactor Rotating Segments (Outer Ring)
      ctx.strokeStyle = primaryColor + '0.5)';
      ctx.lineWidth = 2;
      ctx.beginPath();
      ctx.arc(centerX, centerY, 75, 0, Math.PI * 2);
      ctx.stroke();

      // Outer segmented ticks
      const ticks = 16;
      for (let i = 0; i < ticks; i++) {
        const tickAngle = angle + (i * (Math.PI * 2)) / ticks;
        const tickX1 = centerX + Math.cos(tickAngle) * 70;
        const tickY1 = centerY + Math.sin(tickAngle) * 70;
        const tickX2 = centerX + Math.cos(tickAngle) * 82;
        const tickY2 = centerY + Math.sin(tickAngle) * 82;

        ctx.strokeStyle = i % 2 === 0 ? primaryColor + '0.8)' : primaryColor + '0.2)';
        ctx.lineWidth = i % 4 === 0 ? 3 : 1.5;
        ctx.beginPath();
        ctx.moveTo(tickX1, tickY1);
        ctx.lineTo(tickX2, tickY2);
        ctx.stroke();
      }

      // 3. Counter-rotating Inner Ring
      ctx.strokeStyle = primaryColor + '0.7)';
      ctx.lineWidth = 1.5;
      ctx.beginPath();
      ctx.arc(centerX, centerY, 50, 0, Math.PI * 2);
      ctx.stroke();

      const innerTicks = 8;
      for (let j = 0; j < innerTicks; j++) {
        const inAngle = -angle * 1.5 + (j * (Math.PI * 2)) / innerTicks;
        const ix1 = centerX + Math.cos(inAngle) * 44;
        const iy1 = centerY + Math.sin(inAngle) * 44;
        const ix2 = centerX + Math.cos(inAngle) * 54;
        const iy2 = centerY + Math.sin(inAngle) * 54;

        ctx.strokeStyle = primaryColor + '0.9)';
        ctx.lineWidth = 2;
        ctx.beginPath();
        ctx.moveTo(ix1, iy1);
        ctx.lineTo(ix2, iy2);
        ctx.stroke();
      }

      // 4. Center Micro-Pulse Core
      const pulseSize = 18 + Math.sin(angle * 4) * 4;
      ctx.fillStyle = primaryColor + '0.95)';
      ctx.beginPath();
      ctx.arc(centerX, centerY, pulseSize, 0, Math.PI * 2);
      ctx.fill();

      // Core center bright white diode
      ctx.fillStyle = '#ffffff';
      ctx.beginPath();
      ctx.arc(centerX, centerY, 6, 0, Math.PI * 2);
      ctx.fill();

      angle += speed;
      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      cancelAnimationFrame(animationFrameId);
    };
  }, [state]);

  const stateLabels = {
    idle: { bn: 'স্ট্যান্ডবাই · স্ট্যান্ডিং বাই', en: 'STARK IND. // STANDBY' },
    listening: { bn: 'শুনছি... কথা বলুন', en: 'LISTENING... SPEAK NOW' },
    thinking: { bn: 'চিন্তন ও অ্যানালাইসিস চলছে...', en: 'DEEP REASONING IN PROGRESS' },
    speaking: { bn: 'জার্ভিস কথা বলছে...', en: 'JARVIS VOCAL RESPONSE ACTIVE' },
    executing: { bn: 'টাস্ক এক্সিকিউট হচ্ছে...', en: 'EXECUTING MCP AUTONOMOUS TASK' },
  };

  return (
    <div className="relative flex flex-col items-center justify-center p-6 bg-gradient-to-b from-slate-900/90 via-slate-950/80 to-slate-950 border border-indigo-900/40 rounded-2xl overflow-hidden shadow-2xl">
      {/* Cinematic Ambient Glow */}
      <div className="absolute inset-0 bg-indigo-500/5 pointer-events-none" />

      {/* Top HUD Banner */}
      <div className="relative z-10 w-full flex items-center justify-between pb-3 mb-2 border-b border-slate-800 text-[11px] font-mono text-slate-400">
        <div className="flex items-center gap-2">
          <Activity className="w-3.5 h-3.5 text-indigo-400 animate-pulse" />
          <span>MARK-VII // NEURAL CORE</span>
        </div>
        <div className="flex items-center gap-1.5 text-emerald-400">
          <span className="w-1.5 h-1.5 rounded-full bg-emerald-400 animate-ping" />
          <span>100% NOMINAL</span>
        </div>
      </div>

      {/* Arc Reactor Canvas Visualizer (Interactive) */}
      <div className="relative my-2 cursor-pointer group" onClick={onToggleListen}>
        <canvas
          ref={canvasRef}
          width={220}
          height={220}
          className="transition-transform duration-300 group-hover:scale-105"
        />

        {/* Floating Center Mic Action Button */}
        <button
          className={`absolute top-1/2 left-1/2 -translate-x-1/2 -translate-y-1/2 w-14 h-14 rounded-full flex items-center justify-center transition-all shadow-lg ${
            isListening
              ? 'bg-rose-600/90 hover:bg-rose-500 text-white shadow-rose-600/50 scale-110'
              : 'bg-indigo-600/80 hover:bg-indigo-500 text-white shadow-indigo-600/40'
          }`}
          title="Click to Speak to JARVIS"
        >
          {isListening ? (
            <Mic className="w-6 h-6 animate-pulse" />
          ) : (
            <Volume2 className="w-6 h-6" />
          )}
        </button>
      </div>

      {/* Dynamic Status Text */}
      <div className="relative z-10 text-center space-y-1 mt-2">
        <div
          className={`text-xs font-mono font-bold tracking-widest px-3 py-1 rounded-full border transition-colors inline-block ${
            state === 'listening'
              ? 'bg-rose-950/80 text-rose-300 border-rose-800'
              : state === 'thinking'
              ? 'bg-amber-950/80 text-amber-300 border-amber-800'
              : state === 'speaking'
              ? 'bg-emerald-950/80 text-emerald-300 border-emerald-800'
              : state === 'executing'
              ? 'bg-blue-950/80 text-blue-300 border-blue-800'
              : 'bg-slate-900 text-slate-300 border-slate-800'
          }`}
        >
          {language === 'bn' ? stateLabels[state].bn : stateLabels[state].en}
        </div>

        <p className="text-[11px] text-slate-400 max-w-xs">
          {language === 'bn'
            ? 'ক্লিক করে সরাসরি কথা বলুন: "সার্ভার হেলথ চেক করো", "রেন্ডার নোড অটো-হিল করো" বা "কোডবেস অডিট করো"'
            : 'Click arc reactor to speak: "Check server health", "Heal render nodes", or "Search codebase"'}
        </p>
      </div>
    </div>
  );
};
