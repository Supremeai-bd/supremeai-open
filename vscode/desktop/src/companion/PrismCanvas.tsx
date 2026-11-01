import { useEffect, useRef } from 'react';

interface PrismCanvasProps {
  className?: string;
  theme?: 'prism' | 'minimal';
}

export default function PrismCanvas({ className = '', theme = 'prism' }: PrismCanvasProps) {
  const canvasRef = useRef<HTMLCanvasElement | null>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    let width = (canvas.width = canvas.parentElement?.clientWidth || window.innerWidth);
    let height = (canvas.height = canvas.parentElement?.clientHeight || window.innerHeight);

    const handleResize = () => {
      if (!canvas) return;
      width = canvas.width = canvas.parentElement?.clientWidth || window.innerWidth;
      height = canvas.height = canvas.parentElement?.clientHeight || window.innerHeight;
    };
    window.addEventListener('resize', handleResize);

    // High-tech modern glyphs & geometric sparkle particles
    const glyphs = ['✦', '✧', '◊', 'λ', '{}', '0x', '::', '◈', '01'];
    
    interface Particle {
      x: number;
      y: number;
      speedY: number;
      speedX: number;
      size: number;
      alpha: number;
      maxAlpha: number;
      fadeSpeed: number;
      glyph?: string;
      color: string;
      rotation: number;
      rotSpeed: number;
    }

    const particles: Particle[] = [];
    const particleCount = theme === 'prism' ? 38 : 18;

    const colors = [
      'rgba(0, 240, 255,',   // Cyan
      'rgba(180, 140, 255,', // Iridescent Violet
      'rgba(255, 180, 240,', // Prismatic Soft Pink
      'rgba(255, 255, 255,', // Pure Starlight White
    ];

    for (let i = 0; i < particleCount; i++) {
      particles.push({
        x: Math.random() * width,
        y: Math.random() * height,
        speedY: -(Math.random() * 0.45 + 0.15), // Slow gentle upward float
        speedX: (Math.random() - 0.5) * 0.25,
        size: Math.random() * 11 + 9,
        alpha: Math.random() * 0.5,
        maxAlpha: Math.random() * 0.45 + 0.2,
        fadeSpeed: Math.random() * 0.008 + 0.003,
        glyph: Math.random() > 0.4 ? glyphs[Math.floor(Math.random() * glyphs.length)] : undefined,
        color: colors[Math.floor(Math.random() * colors.length)],
        rotation: Math.random() * Math.PI * 2,
        rotSpeed: (Math.random() - 0.5) * 0.015,
      });
    }

    const render = () => {
      ctx.clearRect(0, 0, width, height);

      particles.forEach((p) => {
        p.y += p.speedY;
        p.x += p.speedX;
        p.rotation += p.rotSpeed;

        p.alpha += p.fadeSpeed;
        if (p.alpha > p.maxAlpha || p.alpha < 0.05) {
          p.fadeSpeed = -p.fadeSpeed;
        }

        if (p.y < -20) {
          p.y = height + 10;
          p.x = Math.random() * width;
        }

        ctx.save();
        ctx.translate(p.x, p.y);
        ctx.rotate(p.rotation);

        if (p.glyph) {
          ctx.font = `${p.size}px monospace`;
          ctx.fillStyle = `${p.color} ${p.alpha})`;
          ctx.shadowBlur = 8;
          ctx.shadowColor = 'rgba(0, 240, 255, 0.4)';
          ctx.fillText(p.glyph, 0, 0);
        } else {
          // Prism diamond sparkle
          ctx.fillStyle = `${p.color} ${p.alpha})`;
          ctx.shadowBlur = 10;
          ctx.shadowColor = 'rgba(255, 255, 255, 0.6)';
          ctx.beginPath();
          ctx.moveTo(0, -p.size / 2);
          ctx.lineTo(p.size / 3, 0);
          ctx.lineTo(0, p.size / 2);
          ctx.lineTo(-p.size / 3, 0);
          ctx.closePath();
          ctx.fill();
        }

        ctx.restore();
      });

      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      window.removeEventListener('resize', handleResize);
      cancelAnimationFrame(animationFrameId);
    };
  }, [theme]);

  return (
    <canvas
      ref={canvasRef}
      className={`holo-prism-canvas ${className}`}
      style={{
        position: 'absolute',
        top: 0,
        left: 0,
        width: '100%',
        height: '100%',
        pointerEvents: 'none',
        zIndex: 1,
        mixBlendMode: 'screen',
      }}
    />
  );
}
