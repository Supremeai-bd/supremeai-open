import React, { useEffect, useRef } from 'react';
import { useSessionCockpitStore } from '../../store/sessionCockpitStore';

export const SandboxViewport: React.FC = () => {
    const canvasRef = useRef<HTMLCanvasElement>(null);
    const { wsRef, controlMode } = useSessionCockpitStore();
    const imageCache = useRef<HTMLImageElement>(new Image());

    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas) return;
        const ctx = canvas.getContext('2d');
        if (!ctx) return;

        const currentImageCache = imageCache.current;

        // Listen for base64 screencast frames on SSE
        const handleMessage = (event: MessageEvent) => {
            try {
                const parsed = JSON.parse(event.data);
                if (parsed.channel === 'screencast') {
                    // Expecting parsed.data to be base64 string of JPEG
                    const img = currentImageCache;
                    img.onload = () => {
                        // Maintain aspect ratio or stretch? Usually CDP provides viewport-sized frames
                        canvas.width = img.width;
                        canvas.height = img.height;
                        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
                    };
                    img.src = `data:image/jpeg;base64,${parsed.data}`;
                }
            } catch {
                // Ignore parsing errors for other channels
            }
        };

        if (wsRef) {
            wsRef.addEventListener('message', handleMessage);
        }

        return () => {
            if (wsRef) {
                wsRef.removeEventListener('message', handleMessage);
            }
            // Clear image cache
            currentImageCache.src = '';
        };

    }, [wsRef]);

    // Handle Human Takeover Dispatch
    useEffect(() => {
        const canvas = canvasRef.current;
        if (!canvas || controlMode !== 'human' || !wsRef) return;

        const sendDispatch = (method: string, params: unknown) => {
            if (wsRef.readyState === WebSocket.OPEN) {
                wsRef.send(JSON.stringify({ method, params }));
            }
        };

        const getCoords = (e: MouseEvent) => {
            const rect = canvas.getBoundingClientRect();
            // Map coordinates from canvas visual size to actual intrinsic width/height (which matches CDP viewport)
            const scaleX = canvas.width / rect.width;
            const scaleY = canvas.height / rect.height;
            return {
                x: (e.clientX - rect.left) * scaleX,
                y: (e.clientY - rect.top) * scaleY
            };
        };

        const onMouseMove = (e: MouseEvent) => {
            const { x, y } = getCoords(e);
            sendDispatch('Input.dispatchMouseEvent', {
                type: 'mouseMoved',
                x, y
            });
        };

        const onMouseDown = (e: MouseEvent) => {
            const { x, y } = getCoords(e);
            const button = e.button === 0 ? 'left' : e.button === 2 ? 'right' : 'middle';
            sendDispatch('Input.dispatchMouseEvent', {
                type: 'mousePressed',
                x, y, button, clickCount: 1
            });
        };

        const onMouseUp = (e: MouseEvent) => {
            const { x, y } = getCoords(e);
            const button = e.button === 0 ? 'left' : e.button === 2 ? 'right' : 'middle';
            sendDispatch('Input.dispatchMouseEvent', {
                type: 'mouseReleased',
                x, y, button, clickCount: 1
            });
        };

        const onWheel = (e: WheelEvent) => {
            const { x, y } = getCoords(e);
            sendDispatch('Input.dispatchMouseEvent', {
                type: 'mouseWheel',
                x, y, deltaX: e.deltaX, deltaY: e.deltaY
            });
        };

        const onKeyDown = (e: KeyboardEvent) => {
            sendDispatch('Input.dispatchKeyEvent', {
                type: 'keyDown',
                key: e.key,
                code: e.code
            });
        };

        const onKeyUp = (e: KeyboardEvent) => {
            sendDispatch('Input.dispatchKeyEvent', {
                type: 'keyUp',
                key: e.key,
                code: e.code
            });
        };

        canvas.addEventListener('mousemove', onMouseMove);
        canvas.addEventListener('mousedown', onMouseDown);
        canvas.addEventListener('mouseup', onMouseUp);
        canvas.addEventListener('wheel', onWheel, { passive: true });

        // Canvas needs tabIndex to receive keyboard events
        canvas.tabIndex = 0;
        canvas.addEventListener('keydown', onKeyDown);
        canvas.addEventListener('keyup', onKeyUp);

        return () => {
            canvas.removeEventListener('mousemove', onMouseMove);
            canvas.removeEventListener('mousedown', onMouseDown);
            canvas.removeEventListener('mouseup', onMouseUp);
            canvas.removeEventListener('wheel', onWheel);
            canvas.removeEventListener('keydown', onKeyDown);
            canvas.removeEventListener('keyup', onKeyUp);
        };

    }, [controlMode, wsRef]);

    return (
        <div className="w-full h-full flex flex-col bg-black overflow-hidden relative">
            <div className="absolute top-0 w-full p-2 bg-gradient-to-b from-black/80 to-transparent z-10 flex justify-between items-center pointer-events-none">
                <span className="text-xs font-mono text-slate-400">CDP SCREENCAST PORT 9222</span>
                {controlMode === 'human' && (
                    <span className="text-xs font-mono text-amber-500 animate-pulse uppercase px-2 py-1 bg-amber-500/10 rounded">
                        HUMAN DRIVING
                    </span>
                )}
            </div>
            <div className="flex-1 overflow-auto flex items-center justify-center p-4">
                <canvas
                    ref={canvasRef}
                    className={`max-w-full max-h-full object-contain shadow-2xl rounded-sm border ${controlMode === 'human' ? 'border-amber-500/50 cursor-crosshair outline-none' : 'border-slate-800'}`}
                    style={{ minWidth: '320px', minHeight: '240px' }}
                />
            </div>
        </div>
    );
};
