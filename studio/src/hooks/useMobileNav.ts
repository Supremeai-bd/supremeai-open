// বাংলা মন্তব্য: মোবাইল ন্যাভিগেশন ড্রয়ারের transient state — localStorage-এ
// persist করা নিষেধ (UI অবস্থা, সেটিংস নয়), তাই useWorkspaceSettings-এর
// persisted store-এর বদলে আলাদা ছোট store।
// Issue #1526 (LOW): the workspace sidebar used to render at a fixed 256px on
// phones and swallow most of the viewport. DashboardLayout now turns it into
// an overlay drawer below md; GlobalHeader's toggle opens/closes it.
import { create } from 'zustand';

interface MobileNavState {
  isMobileNavOpen: boolean;
  setMobileNavOpen: (open: boolean) => void;
  toggleMobileNav: () => void;
}

export const useMobileNav = create<MobileNavState>((set) => ({
  isMobileNavOpen: false,
  setMobileNavOpen: (open) => set({ isMobileNavOpen: open }),
  toggleMobileNav: () => set((state) => ({ isMobileNavOpen: !state.isMobileNavOpen })),
}));
