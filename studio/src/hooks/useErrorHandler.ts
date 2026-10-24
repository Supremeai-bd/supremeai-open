// apps/studio-client/src/hooks/useErrorHandler.ts
// 🛡️ Centralized error handling hook for production-grade frontend resilience

import { useCallback } from 'react';

export interface ErrorContext {
  componentStack?: string;
  errorId?: string;
  timestamp: string;
  userAgent?: string;
}

export interface ErrorHandlerOptions {
  context?: string;
  showToast?: boolean;
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  fallbackData?: any;
}

export const useErrorHandler = () => {
  const handleError = useCallback(
    // eslint-disable-next-line @typescript-eslint/no-explicit-any
    (error: any, context?: string, options?: ErrorHandlerOptions): void => {
      const errorInfo: ErrorContext = {
        timestamp: new Date().toISOString(),
        componentStack: options?.context || context,
        userAgent: typeof navigator !== 'undefined' ? navigator.userAgent : 'unknown',
      };

      // 🔍 Log for observability
      console.error('🚨 [GLOBAL_ERROR_HANDLER]', {
        message: error?.message || String(error),
        context: context || options?.context,
        stack: error?.stack,
        ...errorInfo,
      });

      // 🚨 Show global toast if available and not suppressed
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      if (options?.showToast !== false && (window as any).showGlobalToast) {
        // বাংলা মন্তব্য: React #31 crash রোধ — error?.message object (যেমন `{code,message,errors}`)
        // হলে সবসময় string-এ রূপান্তর করবো, যেন toast-এর message কখনো object না হয়।
        const raw = error?.message ?? error ?? 'An unexpected error occurred';
        const toastMessage =
          typeof raw === 'string'
            ? raw
            : raw && typeof raw === 'object'
              ? JSON.stringify(raw)
              : String(raw);
        // eslint-disable-next-line @typescript-eslint/no-explicit-any
        (window as any).showGlobalToast('error', toastMessage);
      }

      // 📊 In production, could integrate with error monitoring services
      if (typeof process !== 'undefined' && process.env.NODE_ENV === 'production') {
        // Ready for Sentry, LogRocket, etc. integration
        // Example: Sentry.captureException(error, { contexts: { errorInfo } });
      }
    },
    []
  );

  return { handleError };
};
