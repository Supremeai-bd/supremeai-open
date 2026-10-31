import { HOLO_AVATAR_CORTANA, HOLO_AVATAR_IRIDESCENT } from './avatarAssets';
import { useState, useEffect, useRef } from 'react';
import './HolographicHero.css';

export type CompanionState = 'idle' | 'listening' | 'thinking' | 'speaking';

export interface HolographicHeroProps {
  state?: CompanionState;
  isDocked?: boolean;
  onToggleDock?: () => void;
  onClose?: () => void;
  latestReply?: string;
  onSendPrompt?: (text: string) => void;
}

export default function HolographicHero({
  state = 'idle',
  isDocked = false,
  onToggleDock,
  onClose,
  latestReply,
  onSendPrompt,
}: HolographicHeroProps) {
  // Avatars switchable: cortana (blue neon wireframe) vs iridescent (anime cyber-glow)
  const [activeModel, setActiveModel] = useState<'cortana' | 'iridescent'>('cortana');
  const [internalState, setInternalState] = useState<CompanionState>(state);
  const [transcript, setTranscript] = useState('');
  const [isListening, setIsListening] = useState(false);
  const recognitionRef = useRef<any>(null);

  // Drag state for floating mode
  const [position, setPosition] = useState({ x: 30, y: window.innerHeight - 480 });
  const isDraggingRef = useRef(false);
  const dragOffsetRef = useRef({ x: 0, y: 0 });

  useEffect(() => {
    setInternalState(state);
  }, [state]);

  const handleMouseDown = (e: React.MouseEvent) => {
    if (!isDocked) return;
    isDraggingRef.current = true;
    dragOffsetRef.current = {
      x: e.clientX - position.x,
      y: e.clientY - position.y,
    };
    window.addEventListener('mousemove', handleMouseMove);
    window.addEventListener('mouseup', handleMouseUp);
  };

  const handleMouseMove = (e: MouseEvent) => {
    if (!isDraggingRef.current) return;
    const newX = Math.max(10, Math.min(window.innerWidth - 340, e.clientX - dragOffsetRef.current.x));
    const newY = Math.max(10, Math.min(window.innerHeight - 460, e.clientY - dragOffsetRef.current.y));
    setPosition({ x: newX, y: newY });
  };

  const handleMouseUp = () => {
    isDraggingRef.current = false;
    window.removeEventListener('mousemove', handleMouseMove);
    window.removeEventListener('mouseup', handleMouseUp);
  };

  // Setup Web Speech recognition if supported in WebView
  useEffect(() => {
    const SpeechRecognition =
      (window as any).SpeechRecognition || (window as any).webkitSpeechRecognition;
    if (SpeechRecognition) {
      const recognition = new SpeechRecognition();
      recognition.continuous = false;
      recognition.interimResults = true;
      recognition.lang = 'en-US';

      recognition.onstart = () => {
        setIsListening(true);
        setInternalState('listening');
      };

      recognition.onresult = (event: any) => {
        const text = Array.from(event.results)
          .map((r: any) => r[0].transcript)
          .join('');
        setTranscript(text);
      };

      recognition.onend = () => {
        setIsListening(false);
        setInternalState('thinking');
        if (transcript.trim() && onSendPrompt) {
          onSendPrompt(transcript.trim());
        } else {
          setInternalState('idle');
        }
      };

      recognition.onerror = () => {
        setIsListening(false);
        setInternalState('idle');
      };

      recognitionRef.current = recognition;
    }
  }, [transcript, onSendPrompt]);

  const handleMicToggle = () => {
    if (!recognitionRef.current) {
      if (!isListening) {
        setIsListening(true);
        setInternalState('listening');
        setTranscript('Listening to your voice command...');
        setTimeout(() => {
          setIsListening(false);
          setInternalState('thinking');
          setTranscript('Analyzing system diagnostics...');
          setTimeout(() => {
            setInternalState('speaking');
          }, 1200);
        }, 2200);
      } else {
        setIsListening(false);
        setInternalState('idle');
      }
      return;
    }

    if (isListening) {
      recognitionRef.current.stop();
    } else {
      setTranscript('');
      recognitionRef.current.start();
    }
  };

  const avatarSrc = activeModel === 'cortana' ? HOLO_AVATAR_CORTANA : HOLO_AVATAR_IRIDESCENT;

  const floatingStyle: React.CSSProperties = isDocked
    ? {
        left: `${position.x}px`,
        top: `${position.y}px`,
      }
    : {};

  return (
    <div
      style={floatingStyle}
      className={`holo-container ${
        isDocked ? 'holo-container--floating' : 'holo-container--immersive'
      }`}
    >
      {/* Background Cyber Floor Projector (visible in 90% full immersive view) */}
      {!isDocked && (
        <>
          <div className="holo-projector-floor" />
          <div className="holo-projector-rings" />
          <div className="holo-beam-sweep" />
        </>
      )}

      {/* Floating Header / Drag Handle */}
      <div
        className={isDocked ? 'holo-drag-handle' : 'holo-controls-bar'}
        onMouseDown={handleMouseDown}
        title={isDocked ? 'Click & Drag to move hologram anywhere' : ''}
      >
        <div className="holo-badge">
          <span className="holo-status-dot" />
          <span>{isDocked ? '⠿ DRAG ME' : `HOLO-AI // ${internalState.toUpperCase()}`}</span>
        </div>

        <div style={{ display: 'flex', gap: '6px' }}>
          {/* Avatar Switcher */}
          <button
            className="holo-btn-action"
            onClick={(e) => {
              e.stopPropagation();
              setActiveModel((m) => (m === 'cortana' ? 'iridescent' : 'cortana'));
            }}
            title="Switch Holographic Model"
          >
            {activeModel === 'cortana' ? '⚡ Cyber' : '✨ Glow'}
          </button>

          {/* Dock / Expand Toggle */}
          {onToggleDock && (
            <button
              className="holo-btn-action"
              onClick={(e) => {
                e.stopPropagation();
                onToggleDock();
              }}
            >
              {isDocked ? '⤢ 90%' : '◨ Mini'}
            </button>
          )}

          {/* Close */}
          {onClose && (
            <button
              className="holo-btn-action"
              style={{ color: '#ff7b7b' }}
              onClick={(e) => {
                e.stopPropagation();
                onClose();
              }}
            >
              ✕
            </button>
          )}
        </div>
      </div>

      {/* Main Holographic Avatar Stage */}
      <div className={`holo-avatar-wrapper holo-avatar-wrapper--${internalState}`}>
        <img src={avatarSrc} alt="Holographic AI Companion" className="holo-avatar-img" />
        <div className="holo-scanlines" />
      </div>

      {/* Bottom Dialogue & Voice Controls */}
      <div className="holo-speech-hud">
        <div className="holo-dialogue-bubble">
          {latestReply ||
            transcript ||
            (internalState === 'listening'
              ? 'Listening... Speak your command clearly.'
              : internalState === 'thinking'
              ? 'Synthesizing neural telemetry...'
              : internalState === 'speaking'
              ? 'Broadcasting response across system channels.'
              : 'SupremeAI Neural Hologram online. Tap the mic or type.')}
        </div>

        {/* Microphone Push-to-Talk */}
        <button
          className={`holo-mic-btn ${isListening ? 'holo-mic-btn--active' : ''}`}
          onClick={handleMicToggle}
          title="Push to Talk"
        >
          {isListening ? (
            <span style={{ fontSize: '18px' }}>⏹</span>
          ) : (
            <span style={{ fontSize: '20px' }}>🎙️</span>
          )}
        </button>
      </div>
    </div>
  );
}
