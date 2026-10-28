import React, { useRef, useEffect, useState, useCallback } from 'react';
import { 
  Mic, MicOff, Volume2, VolumeX, Maximize2, Minimize2, X, Sparkles, 
  Terminal, ShieldCheck, Activity, Cpu, Zap, Radio, PhoneOff, 
  Play, RefreshCw, Send, CheckCircle2, AlertTriangle, ArrowUpRight, 
  User, Heart, Smile, Image as ImageIcon
} from 'lucide-react';
import { jarvisAudio } from '../../utils/audioFx';
import { 
  DEFAULT_AVATAR_SETTINGS, 
  AVATAR_PERSONAS, 
  type AvatarSettings,
  type AvatarPersonaId,
  type HologramMode 
} from '../../types/avatar';

export type HoloState = 'idle' | 'listening' | 'thinking' | 'speaking' | 'executing' | 'error';

interface JarvisHoloCallProps {
  isOpen: boolean;
  onClose: () => void;
  language: 'bn' | 'en';
  currentState?: HoloState;
  onSendMessage?: (message: string) => void;
  onJumpToPreview?: () => void;
  latestAssistantMessage?: string;
  initialMode?: 'fullscreen' | 'pip';
  avatarSettings?: AvatarSettings;
  onUpdateAvatarSettings?: (settings: AvatarSettings) => void;
}

export const JarvisHoloCall: React.FC<JarvisHoloCallProps> = ({
  isOpen,
  onClose,
  language,
  currentState = 'idle',
  onSendMessage,
  onJumpToPreview,
  latestAssistantMessage,
  initialMode = 'fullscreen',
  avatarSettings: initialAvatarSettings,
  onUpdateAvatarSettings,
}) => {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [viewMode, setViewMode] = useState<'fullscreen' | 'pip'>(initialMode);
  const [internalState, setInternalState] = useState<HoloState>(currentState);
  const [isMicActive, setIsMicActive] = useState<boolean>(false);
  const [isSpeakerMuted, setIsSpeakerMuted] = useState<boolean>(false);
  const [speechTranscript, setSpeechTranscript] = useState<string>('');
  const [activeSubtitle, setActiveSubtitle] = useState<string>('');
  const [quickInput, setQuickInput] = useState<string>('');

  // Avatar Freedom State
  const [currentAvatar, setCurrentAvatar] = useState<AvatarSettings>(() => {
    if (initialAvatarSettings) return initialAvatarSettings;
    try {
      const saved = localStorage.getItem('supremeai_avatar_settings');
      if (saved) return JSON.parse(saved);
    } catch {}
    return DEFAULT_AVATAR_SETTINGS;
  });

  // Preloaded User Photo for Living Photo Hologram
  const photoImageRef = useRef<HTMLImageElement | null>(null);

  useEffect(() => {
    if (currentAvatar.customPhotoUrl) {
      const img = new Image();
      img.src = currentAvatar.customPhotoUrl;
      img.onload = () => {
        photoImageRef.current = img;
      };
    } else {
      photoImageRef.current = null;
    }
  }, [currentAvatar.customPhotoUrl]);

  useEffect(() => {
    if (initialAvatarSettings) {
      setCurrentAvatar(initialAvatarSettings);
    }
  }, [initialAvatarSettings]);

  // Sync prop state with internal state
  useEffect(() => {
    if (currentState) {
      setInternalState(currentState);
    }
  }, [currentState]);

  // Sync subtitle with latest message
  useEffect(() => {
    if (latestAssistantMessage) {
      setActiveSubtitle(latestAssistantMessage);
    } else {
      setActiveSubtitle(
        language === 'bn'
          ? (currentAvatar.relationshipArchetype 
              ? `${currentAvatar.relationshipArchetype}: অনলাইন এবং আপনার সাথে যুক্ত। যেকোনো সফটওয়্যার নির্মাণে বলুন।`
              : 'অনলাইন এবং সম্পূর্ণ প্রস্তুত, স্যার। যেকোনো সফটওয়্যার নির্মাণ বা সিস্টেম নিয়ন্ত্রণের জন্য আমাকে সরাসরি বলুন।')
          : 'Online and fully connected. Give me any software engineering directive or design task.'
      );
    }
  }, [latestAssistantMessage, language, currentAvatar.relationshipArchetype]);

  // Mouse, Gaze & Saccadic Physics Tracking
  const mousePos = useRef({ x: 0, y: 0, targetX: 0, targetY: 0 });
  const headRotation = useRef({ x: 0, y: 0, targetX: 0, targetY: 0 });
  const eyeGaze = useRef({ x: 0, y: 0, targetX: 0, targetY: 0, saccadeTimer: 0 });
  const blinkState = useRef({ value: 1.0, timer: 0, nextBlink: 140, isBlinking: false });
  const currentViseme = useRef<number>(0);
  const rippleWaves = useRef<{ radius: number; maxRadius: number; alpha: number }[]>([]);
  const recognitionRef = useRef<any>(null);

  // Setup Web Speech Recognition
  const initSpeech = useCallback(() => {
    if (typeof window === 'undefined') return;
    const SpeechRecognition = (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (!SpeechRecognition) return;

    try {
      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.lang = language === 'bn' ? 'bn-BD' : 'en-US';

      recognition.onstart = () => {
        setIsMicActive(true);
        setInternalState('listening');
        jarvisAudio.playScan();
      };

      recognition.onresult = (event: any) => {
        let interim = '';
        for (let i = event.resultIndex; i < event.results.length; ++i) {
          if (event.results[i].isFinal) {
            const transcript = event.results[i][0].transcript;
            setSpeechTranscript(transcript);
            handleUserDirective(transcript);
          } else {
            interim += event.results[i][0].transcript;
            setSpeechTranscript(interim);
          }
        }
      };

      recognition.onerror = () => {
        setIsMicActive(false);
      };

      recognition.onend = () => {
        setIsMicActive(false);
      };

      recognitionRef.current = recognition;
    } catch (e) {
      console.warn('Speech recognition not available:', e);
    }
  }, [language]);

  useEffect(() => {
    initSpeech();
    return () => {
      if (recognitionRef.current) {
        recognitionRef.current.abort();
      }
    };
  }, [initSpeech]);

  const toggleMic = () => {
    if (isMicActive) {
      if (recognitionRef.current) recognitionRef.current.stop();
      setIsMicActive(false);
      setInternalState('idle');
    } else {
      if (recognitionRef.current) {
        try {
          recognitionRef.current.start();
        } catch {
          initSpeech();
          recognitionRef.current?.start();
        }
      }
    }
  };

  const handleUserDirective = (text: string) => {
    if (!text.trim()) return;
    setInternalState('thinking');
    jarvisAudio.playActivate();

    if (onSendMessage) {
      onSendMessage(text);
    }

    // Contextual companion speech
    setTimeout(() => {
      setInternalState('speaking');
      const prefix = currentAvatar.relationshipArchetype 
        ? `${currentAvatar.relationshipArchetype}: ` 
        : '';
      const responseBn = `${prefix}"${text.slice(0, 36)}" এর কাজ শুরু করেছি। লাইভ স্যান্ডবক্স ও কোডবেস আপডেট করা হচ্ছে।`;
      const responseEn = `${prefix}Acknowledged: "${text.slice(0, 36)}". Updating live sandbox and workspace codebase.`;
      const finalMsg = language === 'bn' ? responseBn : responseEn;
      setActiveSubtitle(finalMsg);

      if (!isSpeakerMuted) {
        jarvisAudio.speak(
          finalMsg, 
          language, 
          () => {
            setInternalState('idle');
            jarvisAudio.playSuccess();
            currentViseme.current = 0;
          },
          {
            gender: currentAvatar.gender,
            pitch: currentAvatar.pitch,
            rate: currentAvatar.rate,
            accent: currentAvatar.accent,
          },
          (energy) => {
            currentViseme.current = energy;
          }
        );
      } else {
        setTimeout(() => {
          setInternalState('idle');
          currentViseme.current = 0;
        }, 3000);
      }
    }, 1100);
  };

  const sendQuickDirective = (directiveBn: string, directiveEn: string) => {
    const text = language === 'bn' ? directiveBn : directiveEn;
    setSpeechTranscript(text);
    handleUserDirective(text);
  };

  const toggleHologramMode = () => {
    const nextMode: HologramMode = currentAvatar.hologramMode === 'living_human' ? 'cyber' : 'living_human';
    const updated: AvatarSettings = { ...currentAvatar, hologramMode: nextMode };
    setCurrentAvatar(updated);
    try {
      localStorage.setItem('supremeai_avatar_settings', JSON.stringify(updated));
    } catch {}
    if (onUpdateAvatarSettings) onUpdateAvatarSettings(updated);
    jarvisAudio.playScan();
  };

  // Track mouse coordinates over window for smooth parallax
  useEffect(() => {
    const handleMove = (e: MouseEvent) => {
      const width = window.innerWidth;
      const height = window.innerHeight;
      mousePos.current.targetX = ((e.clientX - width / 2) / (width / 2));
      mousePos.current.targetY = ((e.clientY - height / 2) / (height / 2));
    };
    window.addEventListener('mousemove', handleMove);
    return () => window.removeEventListener('mousemove', handleMove);
  }, []);

  // Main 60 FPS Dual-Engine Canvas Hologram Shader
  useEffect(() => {
    if (!isOpen) return;
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    let animationFrameId: number;
    let time = 0;

    // Starlight dust particles
    const stars = Array.from({ length: 75 }, () => ({
      x: (Math.random() - 0.5) * 800,
      y: (Math.random() - 0.5) * 600,
      z: Math.random() * 400 + 40,
      speed: Math.random() * 0.4 + 0.2,
      alpha: Math.random() * 0.6 + 0.3,
    }));

    const render = () => {
      time += 0.02;

      // Handle resize dynamically
      const width = canvas.clientWidth || 800;
      const height = canvas.clientHeight || 600;
      if (canvas.width !== width || canvas.height !== height) {
        canvas.width = width;
        canvas.height = height;
      }

      ctx.clearRect(0, 0, width, height);

      // Smooth mouse lerp
      mousePos.current.x += (mousePos.current.targetX - mousePos.current.x) * 0.08;
      mousePos.current.y += (mousePos.current.targetY - mousePos.current.y) * 0.08;
      const lookX = mousePos.current.x;
      const lookY = mousePos.current.y;

      // Biological Saccade (quick tiny eye movements)
      eyeGaze.current.saccadeTimer++;
      if (eyeGaze.current.saccadeTimer > 80 + Math.random() * 120) {
        eyeGaze.current.saccadeTimer = 0;
        eyeGaze.current.targetX = (Math.random() - 0.5) * 6;
        eyeGaze.current.targetY = (Math.random() - 0.5) * 4;
      }
      eyeGaze.current.x += (eyeGaze.current.targetX - eyeGaze.current.x) * 0.1;
      eyeGaze.current.y += (eyeGaze.current.targetY - eyeGaze.current.y) * 0.1;

      // Natural Biological Blinking (sinusoidal closure every 2-4 seconds)
      blinkState.current.timer++;
      if (blinkState.current.timer > blinkState.current.nextBlink) {
        blinkState.current.isBlinking = true;
        blinkState.current.value -= 0.22;
        if (blinkState.current.value <= 0.05) {
          blinkState.current.value = 0.05;
          blinkState.current.timer = 0;
          blinkState.current.nextBlink = 120 + Math.floor(Math.random() * 160);
          blinkState.current.isBlinking = false;
        }
      } else if (blinkState.current.value < 1) {
        blinkState.current.value += 0.22;
        if (blinkState.current.value > 1) blinkState.current.value = 1;
      }

      // Smooth head rotation lerp
      headRotation.current.x += (lookX * 0.3 - headRotation.current.x) * 0.06;
      headRotation.current.y += (lookY * 0.2 - headRotation.current.y) * 0.06;

      // Dynamic Color Palette based on Avatar Persona and Moment State
      const currentPersonaObj = AVATAR_PERSONAS.find(p => p.id === currentAvatar.personaId) || AVATAR_PERSONAS[0];
      let mainColor = currentPersonaObj.primaryColor;
      let glowRgba = currentPersonaObj.glowColor;
      let ringSpeed = 0.015;

      switch (internalState) {
        case 'listening':
          mainColor = '#f43f5e'; // Coral
          glowRgba = 'rgba(244, 63, 94, ';
          ringSpeed = 0.025;
          break;
        case 'thinking':
          mainColor = '#f59e0b'; // Amber gold
          glowRgba = 'rgba(245, 158, 11, ';
          ringSpeed = 0.06;
          break;
        case 'speaking':
          mainColor = '#10b981'; // Living emerald
          glowRgba = 'rgba(16, 185, 129, ';
          ringSpeed = 0.03;
          break;
        case 'executing':
          mainColor = '#3b82f6'; // Electric blue
          glowRgba = 'rgba(59, 130, 246, ';
          ringSpeed = 0.045;
          break;
        case 'error':
          mainColor = '#ef4444'; // Red alert
          glowRgba = 'rgba(239, 68, 68, ';
          ringSpeed = 0.02;
          break;
        default:
          mainColor = currentPersonaObj.primaryColor;
          glowRgba = currentPersonaObj.glowColor;
          ringSpeed = 0.015;
      }

      // 1. Deep Obsidian Cyberpunk Vignette Background
      const bgGrad = ctx.createRadialGradient(width / 2, height / 2, 50, width / 2, height / 2, Math.max(width, height) * 0.7);
      bgGrad.addColorStop(0, '#0a0f1d');
      bgGrad.addColorStop(0.6, '#030712');
      bgGrad.addColorStop(1, '#010307');
      ctx.fillStyle = bgGrad;
      ctx.fillRect(0, 0, width, height);

      // 2. Rolling Perspective Hexagonal & Grid Floor
      ctx.save();
      ctx.strokeStyle = glowRgba + '0.08)';
      ctx.lineWidth = 1;
      const horizonY = height * 0.74;
      const fov = 200;

      for (let z = 20; z < 300; z += 30) {
        const perspectiveZ = (z + (time * 30) % 30);
        const y = horizonY + (fov / perspectiveZ) * 60;
        if (y < height) {
          ctx.beginPath();
          ctx.moveTo(0, y);
          ctx.lineTo(width, y);
          ctx.stroke();
        }
      }
      for (let x = -width; x < width * 2; x += 60) {
        ctx.beginPath();
        ctx.moveTo(width / 2 + (x - width / 2) * 0.2, horizonY);
        ctx.lineTo(x, height);
        ctx.stroke();
      }
      ctx.restore();

      // 3. Floating Starlight Dust Particles
      ctx.save();
      const cx = width / 2;
      const cy = height * 0.44;
      stars.forEach((s) => {
        s.y -= s.speed;
        if (s.y < -300) s.y = 300;
        const pScale = 300 / (300 + s.z);
        const px = cx + s.x * pScale;
        const py = cy + s.y * pScale;
        ctx.fillStyle = glowRgba + (s.alpha * 0.6) + ')';
        ctx.beginPath();
        ctx.arc(px, py, 1.4 * pScale, 0, Math.PI * 2);
        ctx.fill();
      });
      ctx.restore();

      // 3D Projection Helper
      const fl = 450;
      const project = (x: number, y: number, z: number) => {
        const yaw = lookX * 0.35;
        const pitch = lookY * 0.25;

        const cosY = Math.cos(yaw);
        const sinY = Math.sin(yaw);
        const x1 = x * cosY - z * sinY;
        const z1 = z * cosY + x * sinY;

        const cosX = Math.cos(pitch);
        const sinX = Math.sin(pitch);
        const y2 = y * cosX - z1 * sinX;
        const z2 = z1 * cosX + y * sinX;

        const scale = fl / (fl + z2 + 150);
        return {
          px: cx + x1 * scale,
          py: cy + y2 * scale,
          scale,
        };
      };

      // Acoustic Ripples from Chest
      const chestY = 160;
      const reactorProj = project(0, chestY, 20);

      if (internalState === 'speaking' || internalState === 'listening') {
        if (Math.random() < 0.14) {
          rippleWaves.current.push({ radius: 10, maxRadius: 180, alpha: 0.8 });
        }
      }

      for (let i = rippleWaves.current.length - 1; i >= 0; i--) {
        const w = rippleWaves.current[i];
        w.radius += 2.5;
        w.alpha *= 0.96;

        ctx.save();
        ctx.strokeStyle = glowRgba + w.alpha + ')';
        ctx.lineWidth = 1.5;
        ctx.beginPath();
        ctx.ellipse(reactorProj.px, reactorProj.py, w.radius * 1.4, w.radius * 0.7, 0, 0, Math.PI * 2);
        ctx.stroke();
        ctx.restore();

        if (w.alpha < 0.02 || w.radius > w.maxRadius) {
          rippleWaves.current.splice(i, 1);
        }
      }

      // Gyroscopic Orbital Rings around Head Center
      const hx = cx + headRotation.current.x * 60;
      const hy = cy + headRotation.current.y * 40;

      ctx.save();
      ctx.translate(hx, hy);
      for (let r = 0; r < 3; r++) {
        const ringAngle = time * (r % 2 === 0 ? 0.8 : -0.6) + r * 1.5;
        const radius = 165 + r * 18;
        ctx.beginPath();
        ctx.ellipse(0, 0, radius, radius * 0.35, ringAngle, 0, Math.PI * 2);
        ctx.strokeStyle = glowRgba + (0.15 + r * 0.08) + ')';
        ctx.lineWidth = 1.2;
        ctx.stroke();

        const dotX = Math.cos(ringAngle * 2) * radius;
        const dotY = Math.sin(ringAngle * 2) * radius * 0.35;
        ctx.fillStyle = mainColor;
        ctx.beginPath();
        ctx.arc(dotX, dotY, 2.5, 0, Math.PI * 2);
        ctx.fill();
      }
      ctx.restore();

      // =================================================================
      // DUAL ENGINE ROUTING: LIVING EMOTIONAL / PHOTO COMPANION vs CYBER
      // =================================================================
      const isLivingCompanion = currentAvatar.hologramMode === 'living_human' || currentAvatar.personaId === 'custom-companion';

      if (isLivingCompanion) {
        // -------------------------------------------------------------
        // ENGINE B: LIVING BIOLOGICAL COMPANION & CUSTOM PHOTO HOLOGRAPH
        // -------------------------------------------------------------
        const photo = photoImageRef.current;

        if (photo && photo.complete && photo.naturalWidth > 0) {
          // --- USER CUSTOM PHOTO HOLOGRAPHIC LENS ---
          const photoRadius = 110;
          ctx.save();

          // Outer Volumetric Aura Glow
          const auraGlow = ctx.createRadialGradient(hx, hy, photoRadius * 0.5, hx, hy, photoRadius * 1.4);
          auraGlow.addColorStop(0, glowRgba + '0.25)');
          auraGlow.addColorStop(0.7, glowRgba + '0.08)');
          auraGlow.addColorStop(1, 'rgba(0,0,0,0)');
          ctx.fillStyle = auraGlow;
          ctx.beginPath();
          ctx.arc(hx, hy, photoRadius * 1.4, 0, Math.PI * 2);
          ctx.fill();

          // Circular Mask for Photo
          ctx.beginPath();
          ctx.arc(hx, hy, photoRadius, 0, Math.PI * 2);
          ctx.closePath();
          ctx.clip();

          // Draw Photo with Subtle Parallax Tilt
          const pWidth = photoRadius * 2.2;
          const pHeight = photoRadius * 2.2;
          ctx.drawImage(
            photo, 
            hx - pWidth / 2 + lookX * 12, 
            hy - pHeight / 2 + lookY * 10, 
            pWidth, 
            pHeight
          );

          // Cyan / Violet Hologram Tint Overlay
          ctx.fillStyle = glowRgba + '0.22)';
          ctx.fillRect(hx - photoRadius, hy - photoRadius, photoRadius * 2, photoRadius * 2);

          // Horizontal Scanlines over Photo
          ctx.fillStyle = 'rgba(255, 255, 255, 0.06)';
          for (let y = hy - photoRadius; y < hy + photoRadius; y += 4) {
            ctx.fillRect(hx - photoRadius, y, photoRadius * 2, 1.5);
          }

          // Blinking Eyelid Shutter Overlay
          if (blinkState.current.value < 0.95) {
            const eyeYCenter = hy - 10;
            const blinkCover = (1 - blinkState.current.value) * 32;
            ctx.fillStyle = glowRgba + '0.6)';
            ctx.fillRect(hx - photoRadius, eyeYCenter - blinkCover / 2, photoRadius * 2, blinkCover);
          }

          // Speech Viseme Audio Wave Overlay on Lower Half
          if (currentViseme.current > 0.05 || internalState === 'speaking') {
            const waveEnergy = currentViseme.current || 0.4;
            ctx.strokeStyle = mainColor;
            ctx.lineWidth = 2.5;
            ctx.beginPath();
            const startX = hx - 50;
            const endX = hx + 50;
            const waveY = hy + 45;
            ctx.moveTo(startX, waveY);
            for (let wx = startX; wx <= endX; wx += 5) {
              const wy = waveY + Math.sin(time * 12 + wx * 0.15) * (waveEnergy * 16);
              ctx.lineTo(wx, wy);
            }
            ctx.stroke();
          }

          ctx.restore();

          // Hologram Lens Ring & Reticle
          ctx.save();
          ctx.strokeStyle = mainColor;
          ctx.lineWidth = 2.5;
          ctx.beginPath();
          ctx.arc(hx, hy, photoRadius, 0, Math.PI * 2);
          ctx.stroke();

          // Outer Compass Tick Marks
          const ticks = 24;
          for (let t = 0; t < ticks; t++) {
            const angle = (t * Math.PI * 2) / ticks;
            const x1 = hx + Math.cos(angle) * (photoRadius + 3);
            const y1 = hy + Math.sin(angle) * (photoRadius + 3);
            const x2 = hx + Math.cos(angle) * (photoRadius + (t % 4 === 0 ? 12 : 6));
            const y2 = hy + Math.sin(angle) * (photoRadius + (t % 4 === 0 ? 12 : 6));
            ctx.strokeStyle = glowRgba + (t % 4 === 0 ? '0.9)' : '0.4)');
            ctx.lineWidth = t % 4 === 0 ? 2 : 1;
            ctx.beginPath();
            ctx.moveTo(x1, y1);
            ctx.lineTo(x2, y2);
            ctx.stroke();
          }

          // Companion Archetype Floating Badge
          if (currentAvatar.relationshipArchetype) {
            ctx.fillStyle = 'rgba(15, 23, 42, 0.85)';
            ctx.strokeStyle = glowRgba + '0.8)';
            ctx.lineWidth = 1.2;
            const badgeW = 160;
            const badgeH = 24;
            ctx.strokeRect(hx - badgeW / 2, hy + photoRadius + 14, badgeW, badgeH);
            ctx.fillRect(hx - badgeW / 2, hy + photoRadius + 14, badgeW, badgeH);

            ctx.fillStyle = mainColor;
            ctx.font = 'bold 11px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText(`✦ ${currentAvatar.relationshipArchetype} ✦`, hx, hy + photoRadius + 30);
            ctx.textAlign = 'start';
          }
          ctx.restore();

        } else {
          // --- BIOLOGICAL VECTOR FACE MESH (If no photo uploaded) ---
          const headWidth = 90;
          const headHeight = 120;

          // Head Outer Glow
          const headGlow = ctx.createRadialGradient(hx, hy - 10, 10, hx, hy, 130);
          headGlow.addColorStop(0, glowRgba + '0.2)');
          headGlow.addColorStop(0.6, glowRgba + '0.08)');
          headGlow.addColorStop(1, 'rgba(0,0,0,0)');
          ctx.fillStyle = headGlow;
          ctx.beginPath();
          ctx.ellipse(hx, hy, headWidth * 1.3, headHeight * 1.2, headRotation.current.x * 0.1, 0, Math.PI * 2);
          ctx.fill();

          // Volumetric Head Contour Curves
          ctx.lineWidth = 1.2;
          for (let lat = -4; lat <= 4; lat++) {
            const latRatio = lat / 5;
            const latY = hy + latRatio * headHeight;
            const latRadius = Math.sqrt(Math.max(0, 1 - latRatio * latRatio)) * headWidth;

            ctx.strokeStyle = glowRgba + (0.2 + (1 - Math.abs(latRatio)) * 0.3) + ')';
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

          // Living Eyes (Saccadic Gaze Tracking + Natural Blinking)
          const eyeSpacing = 32;
          const eyeY = hy - 10 + headRotation.current.y * 12;

          [-1, 1].forEach((side) => {
            const eyeX = hx + side * eyeSpacing + headRotation.current.x * 18;
            const blinkH = Math.max(1, 12 * blinkState.current.value);

            // Eye Socket Ethereal Glow
            const eyeGlow = ctx.createRadialGradient(eyeX, eyeY, 1, eyeX, eyeY, 20);
            eyeGlow.addColorStop(0, glowRgba + '0.8)');
            eyeGlow.addColorStop(0.5, glowRgba + '0.3)');
            eyeGlow.addColorStop(1, 'rgba(0,0,0,0)');
            ctx.fillStyle = eyeGlow;
            ctx.beginPath();
            ctx.ellipse(eyeX, eyeY, 16, blinkH + 4, 0, 0, Math.PI * 2);
            ctx.fill();

            // Eye Outline
            ctx.strokeStyle = glowRgba + '0.95)';
            ctx.lineWidth = 1.8;
            ctx.beginPath();
            ctx.ellipse(eyeX, eyeY, 14, blinkH, 0, 0, Math.PI * 2);
            ctx.stroke();

            // Living Iris & Pupil with Saccade Jitter
            if (blinkState.current.value > 0.2) {
              const pupilX = eyeX + eyeGaze.current.x + lookX * 3;
              const pupilY = eyeY + eyeGaze.current.y + lookY * 2;

              // Iris Color
              ctx.fillStyle = currentAvatar.eyeColor || mainColor;
              ctx.beginPath();
              ctx.arc(pupilX, pupilY, 5, 0, Math.PI * 2);
              ctx.fill();

              // White pupil reflection
              ctx.fillStyle = '#ffffff';
              ctx.beginPath();
              ctx.arc(pupilX + 1, pupilY - 1, 2, 0, Math.PI * 2);
              ctx.fill();
            }
          });

          // Living Phonetic Viseme Mouth
          const mouthY = hy + 48 + headRotation.current.y * 15;
          const mouthX = hx + headRotation.current.x * 12;
          const visemeOpen = currentViseme.current || (internalState === 'speaking' ? Math.abs(Math.sin(time * 8)) * 0.7 : 0);
          const mouthOpenH = Math.max(2, visemeOpen * 18);
          const mouthWidth = 24 + visemeOpen * 8;

          ctx.strokeStyle = glowRgba + '0.95)';
          ctx.lineWidth = 2;
          ctx.beginPath();
          // Upper Lip
          ctx.moveTo(mouthX - mouthWidth, mouthY);
          ctx.quadraticCurveTo(mouthX, mouthY - mouthOpenH * 0.5, mouthX + mouthWidth, mouthY);
          // Lower Lip
          ctx.quadraticCurveTo(mouthX, mouthY + mouthOpenH, mouthX - mouthWidth, mouthY);
          ctx.stroke();

          // Soft Interior Glow during speech
          if (visemeOpen > 0.1) {
            ctx.fillStyle = glowRgba + (visemeOpen * 0.5) + ')';
            ctx.fill();
          }
        }

      } else {
        // -------------------------------------------------------------
        // ENGINE A: CYBERNETIC ANDROID / TITAN / ATHENA / QUANTUM CORE
        // -------------------------------------------------------------
        if (currentAvatar.personaId === 'energy-orb') {
          // QUANTUM CORE: Multi-shell oscillating plasma sphere
          const orbCenter = project(0, -10, 30);
          ctx.save();
          for (let s = 1; s <= 4; s++) {
            const shellR = (38 * s + Math.sin(time * 3 + s) * 8) * orbCenter.scale;
            const sGrad = ctx.createRadialGradient(orbCenter.px, orbCenter.py, 2, orbCenter.px, orbCenter.py, shellR);
            sGrad.addColorStop(0, mainColor);
            sGrad.addColorStop(0.4, glowRgba + (0.5 / s) + ')');
            sGrad.addColorStop(1, 'rgba(0,0,0,0)');
            ctx.fillStyle = sGrad;
            ctx.beginPath();
            ctx.arc(orbCenter.px, orbCenter.py, shellR, 0, Math.PI * 2);
            ctx.fill();

            ctx.strokeStyle = glowRgba + (0.7 / s) + ')';
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.arc(orbCenter.px, orbCenter.py, shellR * 0.85, 0, Math.PI * 2);
            ctx.stroke();
          }

          // Orbiting Quantum Electrons
          const electrons = 8;
          for (let e = 0; e < electrons; e++) {
            const angle = time * (1.2 + e * 0.2) + (e * Math.PI * 2) / electrons;
            const erX = Math.cos(angle) * 85;
            const erY = Math.sin(angle * 1.5) * 45;
            const erZ = Math.sin(angle) * 70;
            const eProj = project(erX, erY - 10, erZ + 30);

            ctx.fillStyle = '#ffffff';
            ctx.shadowColor = mainColor;
            ctx.shadowBlur = 10;
            ctx.beginPath();
            ctx.arc(eProj.px, eProj.py, 3.5 * eProj.scale, 0, Math.PI * 2);
            ctx.fill();
          }
          ctx.restore();

        } else {
          // WIREFRAME GEOMETRY (Mark-VII, Athena, Titan)
          const skullNodes = [
            { id: 'f_top', x: 0, y: -110, z: 20 },
            { id: 'f_left', x: -55, y: -90, z: 15 },
            { id: 'f_right', x: 55, y: -90, z: 15 },
            { id: 'brow_mid', x: 0, y: -50, z: 50 },
            { id: 'brow_l', x: -45, y: -52, z: 40 },
            { id: 'brow_r', x: 45, y: -52, z: 40 },
            { id: 'eye_l', x: -28, y: -30, z: 45 },
            { id: 'eye_r', x: 28, y: -30, z: 45 },
            { id: 'nose_tip', x: 0, y: 5, z: 65 },
            { id: 'cheek_l', x: currentAvatar.personaId === 'futuristic-female' ? -62 : -68, y: -5, z: 25 },
            { id: 'cheek_r', x: currentAvatar.personaId === 'futuristic-female' ? 62 : 68, y: -5, z: 25 },
            { id: 'mouth_mid', x: 0, y: 40, z: 50 },
            { id: 'mouth_l', x: -25, y: 42, z: 42 },
            { id: 'mouth_r', x: 25, y: 42, z: 42 },
            { id: 'jaw_l', x: currentAvatar.personaId === 'space-commander' ? -58 : -50, y: 65, z: 20 },
            { id: 'jaw_r', x: currentAvatar.personaId === 'space-commander' ? 58 : 50, y: 65, z: 20 },
            { id: 'chin', x: 0, y: currentAvatar.personaId === 'futuristic-female' ? 82 : 88, z: 40 },
            { id: 'neck_l', x: -35, y: 120, z: 10 },
            { id: 'neck_r', x: 35, y: 120, z: 10 },
          ];

          const projMap: Record<string, { px: number; py: number; scale: number }> = {};
          skullNodes.forEach((node) => {
            projMap[node.id] = project(node.x, node.y, node.z);
          });

          // Athena Halo Crown
          if (currentAvatar.personaId === 'futuristic-female') {
            ctx.save();
            ctx.strokeStyle = glowRgba + '0.8)';
            ctx.lineWidth = 1.8;
            const halo1 = project(0, -118, 25);
            ctx.beginPath();
            ctx.ellipse(halo1.px, halo1.py, 52 * halo1.scale, 14 * halo1.scale, 0, 0, Math.PI * 2);
            ctx.stroke();
            ctx.restore();
          }

          // Wireframe Facets
          const edges = [
            ['f_top', 'f_left'], ['f_top', 'f_right'], ['f_left', 'brow_l'], ['f_right', 'brow_r'],
            ['brow_l', 'brow_mid'], ['brow_r', 'brow_mid'], ['brow_mid', 'nose_tip'],
            ['brow_l', 'cheek_l'], ['brow_r', 'cheek_r'],
            ['cheek_l', 'jaw_l'], ['cheek_r', 'jaw_r'],
            ['nose_tip', 'mouth_mid'], ['mouth_l', 'mouth_mid'], ['mouth_r', 'mouth_mid'],
            ['mouth_mid', 'chin'], ['jaw_l', 'chin'], ['jaw_r', 'chin'],
            ['jaw_l', 'neck_l'], ['jaw_r', 'neck_r'],
            ['neck_l', 'neck_r'],
          ];

          ctx.save();
          ctx.strokeStyle = glowRgba + '0.4)';
          ctx.lineWidth = 1.3;
          edges.forEach(([p1, p2]) => {
            if (projMap[p1] && projMap[p2]) {
              ctx.beginPath();
              ctx.moveTo(projMap[p1].px, projMap[p1].py);
              ctx.lineTo(projMap[p2].px, projMap[p2].py);
              ctx.stroke();
            }
          });
          ctx.restore();

          // Cybernetic Ocular Eyes with Parallax Gaze
          const drawCyberEye = (eyeKey: 'eye_l' | 'eye_r') => {
            const eye = projMap[eyeKey];
            if (!eye) return;
            const isBlink = blinkState.current.isBlinking;
            const eyeW = (currentAvatar.personaId === 'futuristic-female' ? 20 : 18) * eye.scale;
            const eyeH = isBlink ? 1 : 9 * eye.scale;

            ctx.save();
            ctx.strokeStyle = mainColor;
            ctx.lineWidth = 1.5;
            ctx.beginPath();
            ctx.ellipse(eye.px, eye.py, eyeW, eyeH, 0, 0, Math.PI * 2);
            ctx.stroke();

            if (!isBlink) {
              const irisX = eye.px + lookX * 4 * eye.scale;
              const irisY = eye.py + lookY * 3 * eye.scale;
              ctx.fillStyle = mainColor;
              ctx.beginPath();
              ctx.arc(irisX, irisY, 4.5 * eye.scale, 0, Math.PI * 2);
              ctx.fill();
            }
            ctx.restore();
          };

          drawCyberEye('eye_l');
          drawCyberEye('eye_r');

          // Equalizer Mouth with Viseme Lip-Sync
          const mouth = projMap['mouth_mid'];
          if (mouth) {
            ctx.save();
            const bars = 9;
            const barW = 3 * mouth.scale;
            const spacing = 5 * mouth.scale;
            const startX = mouth.px - ((bars - 1) * spacing) / 2;
            const vMod = currentViseme.current || (internalState === 'speaking' ? 0.6 : 0.1);

            for (let b = 0; b < bars; b++) {
              const h = Math.max(3, (Math.abs(Math.sin(time * 8 + b * 0.7)) * 26 * vMod + 4) * mouth.scale);
              ctx.fillStyle = mainColor;
              ctx.fillRect(startX + b * spacing - barW / 2, mouth.py - h / 2, barW, h);
            }
            ctx.restore();
          }
        }
      }

      // Telemetry HUDs in 3D Space
      const leftHud = project(-180, -40, -50);
      const rightHud = project(180, -40, -50);

      // Left HUD
      ctx.save();
      ctx.fillStyle = 'rgba(15, 23, 42, 0.75)';
      ctx.strokeStyle = glowRgba + '0.5)';
      ctx.lineWidth = 1;
      ctx.strokeRect(leftHud.px - 60, leftHud.py - 40, 110, 80);
      ctx.fillRect(leftHud.px - 60, leftHud.py - 40, 110, 80);
      ctx.fillStyle = mainColor;
      ctx.font = '10px monospace';
      ctx.fillText('SYNAPSE CORE', leftHud.px - 52, leftHud.py - 24);
      ctx.fillStyle = '#94a3b8';
      ctx.font = '9px monospace';
      ctx.fillText(`MODE: ${isLivingCompanion ? 'LIVING' : 'CYBER'}`, leftHud.px - 52, leftHud.py - 10);
      ctx.fillText(`VISEME: ${(currentViseme.current * 100).toFixed(0)}%`, leftHud.px - 52, leftHud.py + 4);
      ctx.fillText(`STATE: ${internalState.toUpperCase()}`, leftHud.px - 52, leftHud.py + 18);
      ctx.fillText(`FPS: 60 LOCKED`, leftHud.px - 52, leftHud.py + 32);
      ctx.restore();

      // Right HUD
      ctx.save();
      ctx.fillStyle = 'rgba(15, 23, 42, 0.75)';
      ctx.strokeStyle = glowRgba + '0.5)';
      ctx.lineWidth = 1;
      ctx.strokeRect(rightHud.px - 50, rightHud.py - 40, 110, 80);
      ctx.fillRect(rightHud.px - 50, rightHud.py - 40, 110, 80);
      ctx.fillStyle = mainColor;
      ctx.font = '10px monospace';
      ctx.fillText('MCP TOWER SYNC', rightHud.px - 42, rightHud.py - 24);
      ctx.fillStyle = '#94a3b8';
      ctx.font = '9px monospace';
      ctx.fillText('TOWER: ONLINE', rightHud.px - 42, rightHud.py - 10);
      ctx.fillText('TOOLS: 142 ARMED', rightHud.px - 42, rightHud.py + 4);
      ctx.fillText('AUTONOMY: TIER 4', rightHud.px - 42, rightHud.py + 18);
      ctx.fillText('ENCRYPT: AES-256', rightHud.px - 42, rightHud.py + 32);
      ctx.restore();

      // Horizontal Scanlines
      ctx.save();
      ctx.fillStyle = 'rgba(255, 255, 255, 0.02)';
      for (let y = 0; y < height; y += 4) {
        ctx.fillRect(0, y, width, 1.5);
      }
      ctx.restore();

      animationFrameId = requestAnimationFrame(render);
    };

    animationFrameId = requestAnimationFrame(render);
    return () => cancelAnimationFrame(animationFrameId);
  }, [isOpen, internalState, currentAvatar]);

  if (!isOpen) return null;

  const currentPersona = AVATAR_PERSONAS.find(p => p.id === currentAvatar.personaId) || AVATAR_PERSONAS[0];

  return (
    <div 
      className={`fixed z-50 transition-all duration-300 ease-out flex flex-col bg-slate-950 border border-cyan-500/30 shadow-2xl overflow-hidden ${
        viewMode === 'fullscreen'
          ? 'inset-0 w-screen h-screen'
          : 'bottom-6 right-6 w-[420px] h-[540px] rounded-3xl'
      }`}
    >
      {/* Top Cockpit HUD Header */}
      <div className="relative z-10 px-6 py-3.5 bg-slate-950/90 border-b border-slate-800/80 flex items-center justify-between gap-4 backdrop-blur-md">
        <div className="flex items-center gap-3">
          <div className="relative">
            <span 
              className="w-3.5 h-3.5 rounded-full block animate-pulse"
              style={{ backgroundColor: currentPersona.primaryColor, boxShadow: `0 0 10px ${currentPersona.primaryColor}` }}
            />
            <span className="absolute -top-1 -right-1 w-2 h-2 rounded-full bg-emerald-400" />
          </div>

          <div>
            <div className="flex items-center gap-2">
              <span className="font-bold text-white text-sm tracking-wide">
                {currentAvatar.name}
              </span>
              <span className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-slate-800 text-cyan-300 border border-cyan-500/30">
                {currentAvatar.relationshipArchetype || currentPersona.badge}
              </span>
            </div>
            <div className="flex items-center gap-2 text-[11px] text-slate-400 font-mono">
              <span className="flex items-center gap-1 text-emerald-400">
                <Activity className="w-3 h-3" />
                <span>60 FPS</span>
              </span>
              <span>·</span>
              <span>{currentAvatar.hologramMode === 'living_human' ? 'Biological Living Engine' : 'Cyber 3D Mesh'}</span>
            </div>
          </div>
        </div>

        {/* Engine Switcher & Personas Selector */}
        <div className="flex items-center gap-2">
          {/* Dual Engine Switch Button */}
          <button
            onClick={toggleHologramMode}
            className={`px-3 py-1.5 text-xs font-semibold rounded-xl border transition-all flex items-center gap-1.5 ${
              currentAvatar.hologramMode === 'living_human'
                ? 'bg-rose-950/60 border-rose-500/50 text-rose-300'
                : 'bg-cyan-950/60 border-cyan-500/50 text-cyan-300'
            }`}
            title="Toggle between Cyber Mesh and Living Photo Companion"
          >
            {currentAvatar.hologramMode === 'living_human' ? (
              <>
                <Heart className="w-3.5 h-3.5 text-rose-400" />
                <span>{language === 'bn' ? 'বায়োলজিক্যাল প্রিয় মানুষ' : 'Living Companion'}</span>
              </>
            ) : (
              <>
                <Cpu className="w-3.5 h-3.5 text-cyan-400" />
                <span>{language === 'bn' ? 'সাইবার ৩ডি কোর' : 'Cyber Mesh Core'}</span>
              </>
            )}
          </button>

          {/* Quick Jump to Preview */}
          {onJumpToPreview && (
            <button
              onClick={() => {
                onJumpToPreview();
                if (viewMode === 'fullscreen') setViewMode('pip');
              }}
              className="px-3 py-1.5 text-xs font-semibold rounded-lg bg-indigo-600 hover:bg-indigo-500 text-white flex items-center gap-1.5 transition-all shadow-md shadow-indigo-500/20"
              title="Jump to code preview and sandbox"
            >
              <span>{language === 'bn' ? 'প্রিভিউ' : 'Preview'}</span>
              <ArrowUpRight className="w-3.5 h-3.5" />
            </button>
          )}

          <button
            onClick={() => setViewMode(viewMode === 'fullscreen' ? 'pip' : 'fullscreen')}
            className="p-2 text-slate-400 hover:text-white bg-slate-900 border border-slate-800 rounded-lg transition-colors"
            title={viewMode === 'fullscreen' ? 'Dock PIP' : 'Fullscreen'}
          >
            {viewMode === 'fullscreen' ? <Minimize2 className="w-4 h-4" /> : <Maximize2 className="w-4 h-4" />}
          </button>

          <button
            onClick={onClose}
            className="p-2 text-rose-400 hover:text-rose-200 bg-rose-950/50 border border-rose-800/80 rounded-lg transition-colors"
            title="End Call"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      </div>

      {/* Main Holographic Canvas Body */}
      <div className="relative flex-1 min-h-0 bg-slate-950 flex flex-col justify-between overflow-hidden">
        <canvas
          ref={canvasRef}
          className="absolute inset-0 w-full h-full cursor-crosshair z-0"
        />

        {/* Dynamic Holographic Subtitle HUD */}
        <div className="relative z-10 mx-auto max-w-3xl w-full px-6 pt-4 text-center pointer-events-none">
          <div className="inline-block px-5 py-2.5 rounded-2xl bg-slate-950/85 backdrop-blur-md border border-cyan-500/30 shadow-2xl">
            <div className="text-[11px] font-mono text-cyan-400 font-bold mb-0.5 tracking-wider uppercase">
              {language === 'bn' ? '✦ লাইভ সাবটাইটেল ও ফনেটিক লিপ-সিঙ্ক ✦' : '✦ LIVE PHONETIC TRANSCRIPTION & VISEME ✦'}
            </div>
            <p className="text-sm md:text-base font-medium text-slate-100 leading-snug">
              {activeSubtitle}
            </p>
            {speechTranscript && (
              <div className="mt-1 text-xs text-rose-300 font-mono italic animate-pulse">
                &ldquo;{speechTranscript}&rdquo;
              </div>
            )}
          </div>
        </div>

        {/* Quick Voice Directives Toolbar */}
        {viewMode === 'fullscreen' && (
          <div className="relative z-10 px-6 py-2 flex items-center justify-center gap-2 flex-wrap">
            <button
              onClick={() => sendQuickDirective(
                'একটি আধুনিক SaaS ল্যান্ডিং পেজ তৈরি করো',
                'Build a high-converting modern SaaS landing page'
              )}
              className="px-3 py-1.5 rounded-xl text-xs font-medium bg-slate-900/80 hover:bg-indigo-600/60 text-slate-200 border border-slate-700/80 transition-all hover:scale-105"
            >
              🚀 {language === 'bn' ? 'SaaS ল্যান্ডিং পেজ' : 'SaaS Landing Page'}
            </button>

            <button
              onClick={() => sendQuickDirective(
                'DOM ও কালার কনট্রাস্ট সম্পূর্ণ অডিট করো',
                'Run full Human-Eye DOM & contrast audit'
              )}
              className="px-3 py-1.5 rounded-xl text-xs font-medium bg-slate-900/80 hover:bg-cyan-600/60 text-slate-200 border border-slate-700/80 transition-all hover:scale-105"
            >
              🔍 {language === 'bn' ? 'UI অডিট ও ফিক্স' : 'Visual Audit & Fix'}
            </button>

            <button
              onClick={() => sendQuickDirective(
                'Render 512MB RAM নোড ক্যাশ ক্লিয়ার করো',
                'Clear Render node memory and clearCache: true'
              )}
              className="px-3 py-1.5 rounded-xl text-xs font-medium bg-slate-900/80 hover:bg-amber-600/60 text-slate-200 border border-slate-700/80 transition-all hover:scale-105"
            >
              ⚡ {language === 'bn' ? 'ক্যাশ ক্লিয়ার' : 'Purge Cache'}
            </button>

            <button
              onClick={() => sendQuickDirective(
                'গেস্ট স্যান্ডবক্স লাইভ কোড আপডেট করো',
                'Update guest live code sandbox with multi-device frame'
              )}
              className="px-3 py-1.5 rounded-xl text-xs font-medium bg-slate-900/80 hover:bg-emerald-600/60 text-slate-200 border border-slate-700/80 transition-all hover:scale-105"
            >
              💻 {language === 'bn' ? 'গেস্ট স্যান্ডবক্স' : 'Guest Sandbox'}
            </button>
          </div>
        )}

        {/* Bottom Cockpit Call Controls Dock */}
        <div className="relative z-10 px-6 py-4 bg-slate-950/90 border-t border-slate-800/80 flex flex-col md:flex-row items-center justify-between gap-4 shrink-0">
          {/* Moment State Buttons */}
          <div className="flex items-center gap-1.5 overflow-x-auto text-xs font-mono">
            <span className="text-[11px] text-slate-500 mr-1 hidden sm:inline">Moment:</span>
            {(['idle', 'listening', 'thinking', 'speaking', 'executing', 'error'] as HoloState[]).map((st) => (
              <button
                key={st}
                onClick={() => {
                  setInternalState(st);
                  if (st === 'listening') toggleMic();
                  if (st === 'thinking') jarvisAudio.playScan();
                  if (st === 'speaking') {
                    jarvisAudio.speak(
                      language === 'bn' ? `${currentAvatar.name} আপনার সাথে যুক্ত, স্যার।` : `${currentAvatar.name} online and ready, sir.`,
                      language,
                      undefined,
                      {
                        gender: currentAvatar.gender,
                        pitch: currentAvatar.pitch,
                        rate: currentAvatar.rate,
                        accent: currentAvatar.accent,
                      },
                      (energy) => {
                        currentViseme.current = energy;
                      }
                    );
                  }
                  if (st === 'error') jarvisAudio.playAlert();
                }}
                className={`px-2 py-1 rounded-md text-[11px] uppercase transition-colors ${
                  internalState === st
                    ? 'bg-cyan-500 text-slate-950 font-bold'
                    : 'bg-slate-900 text-slate-400 hover:text-white border border-slate-800'
                }`}
              >
                {st}
              </button>
            ))}
          </div>

          {/* Action Buttons: Mic, Speaker, End Call */}
          <div className="flex items-center gap-3">
            <button
              onClick={toggleMic}
              className={`p-3.5 rounded-2xl border transition-all shadow-xl flex items-center justify-center ${
                isMicActive
                  ? 'bg-rose-600 text-white border-rose-400 shadow-rose-600/40 animate-pulse scale-105'
                  : 'bg-slate-900 text-slate-300 hover:text-white border-slate-700 hover:border-slate-500'
              }`}
              title={isMicActive ? 'Mute Mic' : 'Speak'}
            >
              {isMicActive ? <Mic className="w-5 h-5 text-white" /> : <MicOff className="w-5 h-5 text-slate-400" />}
            </button>

            <button
              onClick={() => {
                const next = !isSpeakerMuted;
                setIsSpeakerMuted(next);
                jarvisAudio.soundEnabled = !next;
                if (next) jarvisAudio.stopSpeaking();
              }}
              className={`p-3.5 rounded-2xl border transition-all ${
                isSpeakerMuted
                  ? 'bg-amber-950/80 text-amber-300 border-amber-800'
                  : 'bg-slate-900 text-slate-300 hover:text-white border-slate-700'
              }`}
              title={isSpeakerMuted ? 'Unmute Audio' : 'Mute Voice'}
            >
              {isSpeakerMuted ? <VolumeX className="w-5 h-5 text-amber-400" /> : <Volume2 className="w-5 h-5 text-cyan-400" />}
            </button>

            <button
              onClick={onClose}
              className="px-4 py-3 rounded-2xl bg-rose-600 hover:bg-rose-500 text-white font-semibold text-xs flex items-center gap-2 shadow-lg shadow-rose-600/30 transition-all hover:scale-102"
              title="End Call"
            >
              <PhoneOff className="w-4 h-4" />
              <span>{language === 'bn' ? 'কল সমাপ্ত' : 'End Call'}</span>
            </button>
          </div>

          {/* Quick Directive Text Input */}
          <div className="flex items-center gap-2 w-full md:w-80">
            <input
              type="text"
              value={quickInput}
              onChange={(e) => setQuickInput(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && quickInput.trim()) {
                  handleUserDirective(quickInput);
                  setQuickInput('');
                }
              }}
              placeholder={
                language === 'bn'
                  ? 'কথা বলুন অথবা লিখে নির্দেশ দিন...'
                  : 'Speak or type directive...'
              }
              className="flex-1 bg-slate-900 border border-slate-800 focus:border-cyan-500 rounded-xl px-3 py-2 text-xs text-slate-200 outline-none"
            />
            <button
              onClick={() => {
                if (quickInput.trim()) {
                  handleUserDirective(quickInput);
                  setQuickInput('');
                }
              }}
              disabled={!quickInput.trim()}
              className="p-2 rounded-xl bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 text-white transition-all"
            >
              <Send className="w-4 h-4" />
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
