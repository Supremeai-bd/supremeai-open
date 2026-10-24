import { useEffect, useRef, useCallback } from 'react';
import { eventBus, Events } from '../lib/componentEventBus';

interface ConsoleError {
  type: 'error' | 'warning' | 'info';
  message: string;
  source: string;
  line: number;
  column: number;
  timestamp: number;
}

export function useIframeConsole(iframeRef: React.RefObject<HTMLIFrameElement>) {
  const errorsRef = useRef<ConsoleError[]>([]);
  
  const captureErrors = useCallback(() => {
    const iframe = iframeRef.current;
    if (!iframe?.contentWindow) return;
    
    try {
      // Inject error interceptor into iframe
      // H-05 Fix: Determine precise target origin instead of wildcard
      const targetOrigin = iframe.src && iframe.src !== 'about:blank' 
        ? new URL(iframe.src, window.location.href).origin 
        : window.location.origin;

      iframe.contentWindow.postMessage({
        type: 'CONSOLE_TRAP_INIT',
      }, targetOrigin);

      // Listen for errors from iframe via postMessage
      const handler = (event: MessageEvent) => {
        if (event.data?.source !== 'iframe-console') return;
        
        const error: ConsoleError = {
          type: event.data.type,
          message: event.data.message,
          source: event.data.source,
          line: event.data.line,
          column: event.data.column,
          timestamp: Date.now(),
        };
        
        errorsRef.current.push(error);
        
        // Emit event for AI self-healing
        eventBus.emit(Events.IFRAME_CONSOLE_ERROR, {
          error,
          url: iframe.src,
        });
      };
      
      window.addEventListener('message', handler);
      return () => window.removeEventListener('message', handler);
    } catch (e) {
      console.warn('Cannot intercept iframe console (CORS restriction):', e);
    }
  }, [iframeRef]);
  
  useEffect(() => {
    const cleanup = captureErrors();
    return cleanup;
  }, [captureErrors]);
  
  return {
    getErrors: () => errorsRef.current,
    clearErrors: () => { errorsRef.current = []; },
    getErrorSummary: () => ({
      total: errorsRef.current.length,
      errors: errorsRef.current.filter(e => e.type === 'error').length,
      warnings: errorsRef.current.filter(e => e.type === 'warning').length,
      lastError: errorsRef.current[errorsRef.current.length - 1],
    }),
  };
}
