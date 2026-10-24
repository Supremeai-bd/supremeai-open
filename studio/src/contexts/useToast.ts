import { useContext } from 'react';
import { ToastContext } from './ToastContext';

// বাংলা মন্তব্য: useToast hook এখানে সরাসরি ডিফাইন করা হয়েছে, যাতে ToastProvider.tsx এ রেফ্রেশ সমস্যা না হয়
export const useToast = () => {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error('useToast must be used within a ToastProvider');
  }
  return context;
};
