import { createContext } from 'react';

// বাংলা মন্তব্য: Toast context types এখানে সরাসরি ডিফাইন করা হয়েছে, যাতে ToastProvider.tsx এ রেফ্রেশ সমস্যা না হয়
export type ToastType = 'success' | 'error' | 'info';

export interface Toast {
  id: string;
  type: ToastType;
  message: string;
}

interface ToastContextValue {
  showToast: (type: ToastType, message: string) => void;
}

// বাংলা মন্তব্য: ToastContext এখানে সরাসরি ডিফাইন করা হয়েছে, যাতে ToastProvider.tsx এ রেফ্রেশ সমস্যা না হয়
export const ToastContext = createContext<ToastContextValue | undefined>(undefined);

// Global toast function for external access - using ref pattern
// বাংলা মন্তব্য: globalShowToastRef একে অপর ফাইলে সরানো হয়েছে, যাতে ToastProvider.tsx এ রেফ্রেশ সমস্যা না হয়
export const globalShowToastRef = { current: (() => {
  console.warn("ToastProvider is not mounted yet.");
}) as (type: ToastType, message: string) => void };

if (typeof window !== 'undefined') {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  (window as any).showGlobalToast = (type: ToastType, message: string) => {
    globalShowToastRef.current(type, message);
  };
}
