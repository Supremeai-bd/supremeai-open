import React, { useEffect, useRef } from 'react';

interface ConstellationNode {
  x: number;
  y: number;
  vx: number;
  vy: number;
  radius: number;
  baseRadius: number;
  color: string;
  cluster: number;
  alpha: number;
  pulsePhase: number;
}

export const NeuralConstellationCanvas: React.FC = () => {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    let width = (canvas.width = window.innerWidth);
    let height = (canvas.height = window.innerHeight);

    const handleResize = () => {
      if (!canvas) return;
      width = canvas.width = window.innerWidth;
      height = canvas.height = window.innerHeight;
    };
    window.addEventListener('resize', handleResize);

    // Color palette based on the user screenshot: Cyan, Emerald, Violet, Gold, Rose
    const clusterColors = [
      '#00f5ff', // Cyan / Neural core
      '#10b981', // Emerald / Federation healthy
      '#a855f7', // Violet / Model orchestration
      '#f59e0b', // Gold / Hub consensus
      '#ec4899', // Rose / Activity pulse
    ];

    const NODE_COUNT = Math.min(85, Math.floor((width * height) / 16000));
    const nodes: ConstellationNode[] = [];

    // Create 3-4 cluster anchor hubs (similar to image 2 neural network)
    const clusterHubs = [
      { x: width * 0.35, y: height * 0.45, color: '#00f5ff' },
      { x: width * 0.65, y: height * 0.40, color: '#10b981' },
      { x: width * 0.50, y: height * 0.65, color: '#a855f7' },
      { x: width * 0.20, y: height * 0.55, color: '#f59e0b' },
    ];

    for (let i = 0; i < NODE_COUNT; i++) {
      const clusterIdx = Math.floor(Math.random() * clusterHubs.length);
      const hub = clusterHubs[clusterIdx];
      // Distribute nodes around hubs with Gaussian-like spread
      const angle = Math.random() * Math.PI * 2;
      const dist = Math.random() * (Math.min(width, height) * 0.32);
      const r = Math.random() * 2.2 + 1.2;

      nodes.push({
        x: Math.max(20, Math.min(width - 20, hub.x + Math.cos(angle) * dist)),
        y: Math.max(20, Math.min(height - 20, hub.y + Math.sin(angle) * dist)),
        vx: (Math.random() - 0.5) * 0.35,
        vy: (Math.random() - 0.5) * 0.35,
        radius: r,
        baseRadius: r,
        color: clusterColors[clusterIdx % clusterColors.length],
        cluster: clusterIdx,
        alpha: Math.random() * 0.45 + 0.35,
        pulsePhase: Math.random() * Math.PI * 2,
      });
    }

    let time = 0;

    const render = () => {
      time += 0.015;
      ctx.clearRect(0, 0, width, height);

      // 1. Draw subtle 3D perspective grid lines (Isometric HUD floor from image 1)
      ctx.save();
      ctx.strokeStyle = 'rgba(0, 245, 255, 0.035)';
      ctx.lineWidth = 1;
      const gridSpacing = 64;
      const startX = 0;
      const endX = width;
      for (let y = height * 0.25; y < height; y += gridSpacing * 0.7) {
        ctx.beginPath();
        ctx.moveTo(startX, y);
        ctx.lineTo(endX, y);
        ctx.stroke();
      }
      ctx.restore();

      // 2. Connect near nodes with dynamic glowing arcs
      const MAX_DIST = Math.min(130, width * 0.14);
      for (let i = 0; i < nodes.length; i++) {
        for (let j = i + 1; j < nodes.length; j++) {
          const dx = nodes[i].x - nodes[j].x;
          const dy = nodes[i].y - nodes[j].y;
          const dist = Math.hypot(dx, dy);

          if (dist < MAX_DIST) {
            const opacity = (1 - dist / MAX_DIST) * 0.22;
            ctx.beginPath();
            ctx.strokeStyle = nodes[i].cluster === nodes[j].cluster
              ? nodes[i].color
              : 'rgba(148, 163, 184, 0.15)';
            ctx.globalAlpha = opacity;
            ctx.lineWidth = 0.9;
            ctx.moveTo(nodes[i].x, nodes[i].y);
            // Gentle curved bezier connection
            const cx = (nodes[i].x + nodes[j].x) / 2 + Math.sin(time + i) * 6;
            const cy = (nodes[i].y + nodes[j].y) / 2 + Math.cos(time + j) * 6;
            ctx.quadraticCurveTo(cx, cy, nodes[j].x, nodes[j].y);
            ctx.stroke();
          }
        }
      }

      // 3. Draw nodes with pulsating halos
      for (let i = 0; i < nodes.length; i++) {
        const node = nodes[i];

        // Slight drift
        node.x += node.vx;
        node.y += node.vy;

        if (node.x < 10 || node.x > width - 10) node.vx *= -1;
        if (node.y < 10 || node.y > height - 10) node.vy *= -1;

        // Pulse calculation
        const pulse = Math.sin(time * 2 + node.pulsePhase);
        const currentR = Math.max(1, node.baseRadius + pulse * 0.6);

        // Outer glow
        ctx.globalAlpha = node.alpha * 0.35;
        const grad = ctx.createRadialGradient(node.x, node.y, 0, node.x, node.y, currentR * 4);
        grad.addColorStop(0, node.color);
        grad.addColorStop(1, 'transparent');
        ctx.fillStyle = grad;
        ctx.beginPath();
        ctx.arc(node.x, node.y, currentR * 4, 0, Math.PI * 2);
        ctx.fill();

        // Inner solid core
        ctx.globalAlpha = node.alpha;
        ctx.fillStyle = node.color;
        ctx.beginPath();
        ctx.arc(node.x, node.y, currentR, 0, Math.PI * 2);
        ctx.fill();
      }

      ctx.globalAlpha = 1.0;
      animationFrameId = requestAnimationFrame(render);
    };

    render();

    return () => {
      window.removeEventListener('resize', handleResize);
      cancelAnimationFrame(animationFrameId);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      className="pointer-events-none fixed inset-0 z-0 h-full w-full"
      style={{ opacity: 0.85 }}
      aria-hidden="true"
    />
  );
};

