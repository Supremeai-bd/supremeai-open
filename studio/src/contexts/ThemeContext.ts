import { createContext } from 'react';
import type { Theme } from './ThemeConstants';

// বাংলা মন্তব্য: ThemeContext এখানে সরাসরি ডিফাইন করা হয়েছে, যাতে ThemeProvider.tsx এ রেফ্রেশ সমস্যা না হয়
export interface ThemeContextType {
  theme: Theme;
  toggleTheme: () => void;
  setTheme: (theme: Theme) => void;
}

export const ThemeContext = createContext<ThemeContextType | undefined>(undefined);
