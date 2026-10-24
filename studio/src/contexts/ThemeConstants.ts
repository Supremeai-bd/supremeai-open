// বাংলা মন্তব্য: থিম সাইকেল অর্ডার (টগল বাটনে ক্লিক করলে পরবর্তী থিমে যাবে)
// Theme type এখানে সরাসরি ডিফাইন করা হয়েছে, যাতে ThemeContext.ts এর সাথে সাইকেল ইম্পোর্ট না হয়
// (#4138 Phase 1): 4-থিম → 8-থিম সম্প্রসারণ (FRONTEND_DASHBOARD_MASTER_PLAN_V2)।
// SSOT: এই ফাইলই একমাত্র উৎস — ThemeProvider/ThemeSyncProvider/টেস্ট সব এখান থেকে
// পড়ে, কোথাও হার্ডকোড করা theme-তালিকা রাখা নিষিদ্ধ (Config > Hardcoded)।
export type Theme =
  | 'dark'
  | 'light'
  | 'synthwave'
  | 'cyberpunk'
  | 'minimal'
  | 'sunset'
  | 'matrix'
  | 'emerald';

export const THEME_ORDER: Theme[] = [
  'dark',
  'light',
  'synthwave',
  'cyberpunk',
  'minimal',
  'sunset',
  'matrix',
  'emerald',
];

// বাংলা মন্তব্য (#4138): প্রতিটি থিমের মেটা — টগল UI-লেবেল ও isDark-সিদ্ধান্তের
// একমাত্র উৎস। আগে isDark সব জায়গায় `theme === 'dark' || theme === 'matrix'`
// হার্ডকোড ছিল (ThemeProvider + ThemeSyncProvider) — নতুন থিম যোগ হলে সেটা
// নীরবে ভুল isDark দিত; এখন এক জায়গায় (Single Source of Truth)।
export interface ThemeMeta {
  /** টগল-টুলটিপে দেখানোর মানব-পাঠযোগ্য নাম */
  label: string;
  /** থিমটি ডার্ক-পরিবারভুক্ত কি না — অ্যানিমেশন তীব্রতা/কনট্রাস্ট-সিদ্ধান্তে ব্যবহৃত */
  isDark: boolean;
}

export const THEME_META: Record<Theme, ThemeMeta> = {
  dark: { label: 'Deep Space', isDark: true },
  light: { label: 'Daylight', isDark: false },
  synthwave: { label: 'Synthwave', isDark: true },
  cyberpunk: { label: 'Cyberpunk', isDark: true },
  minimal: { label: 'Minimal', isDark: false },
  sunset: { label: 'Sunset Ember', isDark: true },
  matrix: { label: 'Matrix Rain', isDark: true },
  emerald: { label: 'Emerald Deep', isDark: true },
};

/** isDark-সিদ্ধান্তের canonical helper — অজানা মানে fail-safe (true)। */
export const isDarkTheme = (theme: Theme | string): boolean =>
  THEME_META[theme as Theme]?.isDark ?? true;
