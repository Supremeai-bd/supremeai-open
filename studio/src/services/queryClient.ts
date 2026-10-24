import { QueryClient } from '@tanstack/react-query';
// 🔬 Evolution v3.0: Enhanced query client with retry + circuit breaker awareness

/**
 * 🔬 Error classification for smart retries
 */
export function classifyError(error: unknown): {
  retryable: boolean;
  category: 'network' | 'auth' | 'rate_limit' | 'server' | 'client' | 'unknown';
} {
  if (error instanceof Error) {
    const msg = error.message.toLowerCase();
    if (msg.includes('fetch failed') || msg.includes('network')) {
      return { retryable: true, category: 'network' };
    }
    if (msg.includes('401') || msg.includes('unauthorized') || msg.includes('forbidden')) {
      return { retryable: false, category: 'auth' };
    }
    if (msg.includes('429') || msg.includes('rate')) {
      return { retryable: true, category: 'rate_limit' };
    }
    if (msg.includes('500') || msg.includes('502') || msg.includes('503')) {
      return { retryable: true, category: 'server' };
    }
    if (msg.includes('400') || msg.includes('404') || msg.includes('422')) {
      return { retryable: false, category: 'client' };
    }
  }
  
  // HTTP status codes from response
  if (error && typeof error === 'object' && 'status' in error) {
    const status = (error as { status: number }).status;
    if ([408, 429, 500, 502, 503, 504].includes(status)) {
      return { retryable: true, category: 'server' };
    }
    if ([400, 401, 403, 404, 422].includes(status)) {
      return { retryable: false, category: 'client' };
    }
  }
  
  return { retryable: true, category: 'unknown' };
}

/**
 * 🔬 Smart retry decision function
 */
export function smartRetryDecision(failureCount: number, error: unknown): boolean {
  const { retryable, category: _category } = classifyError(error);
  
  // Never retry auth/client errors more than once
  if (!retryable) return false;
  
  // Max 3 retries for retryable errors
  const maxRetries = parseInt(
    typeof window !== 'undefined' 
      ? (window as unknown as { __VITE_MAX_RETRIES?: string }).__VITE_MAX_RETRIES || import.meta.env.VITE_MAX_RETRIES || '3'
      : '3',
    10
  );
  
  return failureCount < maxRetries;
}

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 5 * 60 * 1000, // 5 minutes
      gcTime: 10 * 60 * 1000,   // 10 minutes
      refetchOnWindowFocus: true,
      retry: smartRetryDecision, // 🔬 Evolution v3.0: Smart retry
      retryDelay: (attemptIndex) => Math.min(1000 * 2 ** attemptIndex + Math.random() * 500, 8000), // Exponential backoff
    },
    mutations: {
      retry: 1,
      retryDelay: 1000, // 🔬 Evolution v3.0: Fixed delay for mutations
    },
  },
});
