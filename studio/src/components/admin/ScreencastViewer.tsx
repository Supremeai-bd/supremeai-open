import React, { useEffect, useRef, useState, useCallback } from 'react';
import { MousePointer, Keyboard, Hand } from 'lucide-react';
import { getWsBaseUrl } from '../../utils/api';

interface ScreencastViewerProps {
  sessionId: string;
  takeoverToken: string;
  onTakeoverComplete?: () => void;
  onReturnControl?: () => void;
}

export function ScreencastViewer({ 
  sessionId, 
  takeoverToken,
  onReturnControl 
}: ScreencastViewerProps) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [isControlling, setIsControlling] = useState(false);
  const [fps, setFps] = useState(0);
  const [frameCount, setFrameCount] = useState(0);
  const lastFrameTime = useRef<number>(0);
  
  // Connect to screencast WebSocket
  useEffect(() => {
    lastFrameTime.current = Date.now();
    // SECURITY FIX (audit S-2): takeoverToken must never appear in the URL.
    // It is sent as a first-message auth frame immediately after the socket opens.
    const wsUrl = `${getWsBaseUrl()}/ws/session/${sessionId}/takeover`;

    wsRef.current = new WebSocket(wsUrl);

    wsRef.current.onopen = () => {
      // Send auth frame — this keeps the token out of browser history and server logs.
      wsRef.current?.send(JSON.stringify({ type: 'auth', token: takeoverToken }));
      setIsConnected(true);
    };

    
    wsRef.current.onmessage = async (event) => {
      try {
        const message = JSON.parse(event.data);
        
        if (message.channel === 'screencast' && message.type === 'frame') {
          // Decode JPEG frame
          const img = new Image();
          img.onload = () => {
            const canvas = canvasRef.current;
            if (!canvas) return;
          
          const ctx = canvas.getContext('2d');
          canvas.width = img.width;
          canvas.height = img.height;
          ctx?.drawImage(img, 0, 0);
          
          // Calculate FPS
          const now = Date.now();
          const delta = now - lastFrameTime.current;
          if (delta > 0) {
            setFps(Math.round(1000 / delta));
          }
          lastFrameTime.current = now;
          setFrameCount(prev => prev + 1);
        };
        img.src = `data:image/jpeg;base64,${message.data}`;
      }
      
      if (message.channel === 'screencast' && message.status === 'unavailable') {
        console.error('Screencast unavailable:', message.message);
        setIsConnected(false);
      }
    } catch (err) {
      console.warn('[ScreencastViewer] Failed parsing WebSocket payload:', err);
    }
  };
    
    wsRef.current.onclose = () => {
      setIsConnected(false);
    };
    
    return () => {
      wsRef.current?.close();
    };
  }, [sessionId, takeoverToken]);
  
  // Mouse event handlers for takeover control
  const handleCanvasMouseMove = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!isControlling || !wsRef.current) return;
    
    const rect = e.currentTarget.getBoundingClientRect();
    const x = Math.round(e.clientX - rect.left);
    const y = Math.round(e.clientY - rect.top);
    
    wsRef.current.send(JSON.stringify({
      action: 'mouse.move',
      data: { x, y },
    }));
  }, [isControlling]);
  
  const handleCanvasMouseDown = useCallback((e: React.MouseEvent<HTMLCanvasElement>) => {
    if (!isControlling || !wsRef.current) return;
    
    const rect = e.currentTarget.getBoundingClientRect();
    const x = Math.round(e.clientX - rect.left);
    const y = Math.round(e.clientY - rect.top);
    
    wsRef.current.send(JSON.stringify({
      action: 'mouse.click',
      data: { x, y, delay: 50 },
    }));
  }, [isControlling]);
  
  const handleCanvasMouseWheel = useCallback((e: React.WheelEvent<HTMLCanvasElement>) => {
    if (!isControlling || !wsRef.current) return;
    e.preventDefault();
    
    wsRef.current.send(JSON.stringify({
      action: 'mouse.wheel',
      data: { delta_x: e.deltaX, delta_y: e.deltaY },
    }));
  }, [isControlling]);
  
  // Keyboard handler
  useEffect(() => {
    if (!isControlling || !wsRef.current) return;
    
    const handleKeyDown = (e: KeyboardEvent) => {
      wsRef.current?.send(JSON.stringify({
        action: 'keyboard.press',
        data: { key: e.key },
      }));
    };
    
    window.addEventListener('keydown', handleKeyDown);
    return () => window.removeEventListener('keydown', handleKeyDown);
  }, [isControlling]);
  
  // Return control to AI
  const handleReturnControl = useCallback(() => {
    if (!wsRef.current) return;
    
    wsRef.current.send(JSON.stringify({
      action: 'return_control',
      data: {},
    }));
    
    setIsControlling(false);
    onReturnControl?.();
  }, [onReturnControl]);
  
  return (
    <div className="screencast-viewer">
      {/* Control Bar */}
      <div className="screencast-controls">
        <div className="connection-status">
          <span className={`status-dot ${isConnected ? 'connected' : 'disconnected'}`} />
          <span>{isConnected ? 'Live' : 'Disconnected'}</span>
          <span className="fps-counter">{fps} FPS</span>
          <span className="frame-counter">Frame #{frameCount}</span>
        </div>
        
        <div className="control-actions">
          {!isControlling ? (
            <button
              onClick={() => setIsControlling(true)}
              className="takeover-btn"
              title="Take control (HITL)"
            >
              <Hand size={16} />
              Take Control
            </button>
          ) : (
            <button
              onClick={handleReturnControl}
              className="return-btn"
              title="Return control to AI"
            >
              <MousePointer size={16} />
              Return to AI
            </button>
          )}
        </div>
      </div>
      
      {/* Canvas for rendering screencast */}
      <canvas
        ref={canvasRef}
        className={`screencast-canvas ${isControlling ? 'controlling' : 'view-only'}`}
        onMouseMove={handleCanvasMouseMove}
        onMouseDown={handleCanvasMouseDown}
        onWheel={handleCanvasMouseWheel}
      />
      
      {/* Instructions overlay when controlling */}
      {isControlling && (
        <div className="control-instructions">
          <Keyboard size={12} /> Move mouse to control cursor • Click to interact • Type to use keyboard • Press ESC to return
        </div>
      )}
    </div>
  );
}
