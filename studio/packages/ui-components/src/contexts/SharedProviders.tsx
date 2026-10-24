import React from 'react';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';

// QueryClient ইচ্ছাকৃতভাবে কম্পোনেন্টের বাইরে (মডিউল স্কোপে) তৈরি করা হয়েছে।
// কম্পোনেন্টের ভেতরে তৈরি করলে প্রতিবার রি-রেন্ডারে নতুন ক্লায়েন্ট তৈরি হতো
// এবং পুরো ক্যাশ মুছে গিয়ে অপ্রয়োজনীয় রি-ফেচ হতো।
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // FINAL-TEST FIX: smart retry policy moved here from the (now removed)
      // duplicate QueryClient in studio's App.tsx so every consumer shares one
      // client with the same behavior. Auth/rate-limit errors are never retried
      // — retrying them just hammers the backend and delays the login prompt.
      retry: (failureCount: number, error: unknown) => {
        const err = error as Record<string, unknown> | null;
        const msg = (err?.message as string) || '';
        const status = err?.status as number | undefined;
        if (
          status === 401 || status === 403 || status === 429 ||
          msg.includes('401') || msg.includes('403') || msg.includes('429') ||
          msg.includes('Rate limit') || msg.includes('Unauthorized')
        ) return false;
        return failureCount < 2;
      },
      retryDelay: (attemptIndex: number) =>
        Math.min(1000 * 2 ** attemptIndex + Math.random() * 500, 15000),
      refetchOnWindowFocus: false, // ট্যাব বদলালেই যেন অকারণে ডেটা রি-ফেচ না হয়
      staleTime: 30_000,
    },
  },
});

/**
 * SharedProviders — একাধিক অ্যাপে (স্টুডিও, ডেস্কটপ) ব্যবহারের জন্য
 * সাধারণ কনটেক্সট প্রোভাইডারগুলোকে একত্রে মোড়ানো হয়েছে।
 * নতুন গ্লোবাল প্রোভাইডার যুক্ত করতে হলে এখানেই যোগ করতে হবে।
 */
export const SharedProviders: React.FC<{children: React.ReactNode}> = ({ children }) => {
  return (
    <QueryClientProvider client={queryClient}>
      {children}
    </QueryClientProvider>
  );
};

export default SharedProviders;
