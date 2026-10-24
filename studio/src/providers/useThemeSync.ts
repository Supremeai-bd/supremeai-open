import { useContext } from 'react';
import { ThemeSyncContext } from './ThemeSyncContext';

// বাংলা মন্তব্য: useThemeSync hook এখানে সরাসরি ডিফাইন করা হয়েছে, যাতে ThemeSyncProvider.tsx এ রেফ্রেশ সমস্যা না হয়
export const useThemeSync = () => useContext(ThemeSyncContext);
