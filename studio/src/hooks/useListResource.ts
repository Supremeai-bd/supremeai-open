// useListResource — generic list-loading lifecycle hook (Wave 3 dedup)
// বাংলা মন্তব্য: RunsPage/ActivityPage/FilesPage/ProjectsPage/MarketplacePage/
// KnowledgePage — প্রতিটিতে একই `useState(items) + useState(isLoading) +
// useState(loadError) + useCallback(load) + useEffect` ক্লাস্টার কপি-পেস্ট ছিল
// (~৬০-৯০ লাইন boilerplate)। এই হুক শুধু load/lifecycle-এর মালিক; search/filter/
// mutation state সম্পূর্ণ পেজ-লোকাল থাকে — ফলে পেজের behavior, test-visible
// text ও aria attribute অপরিবর্তিত থাকে।
//
// ডিজাইন সিদ্ধান্ত (সবগুলো পেজের প্রকৃত প্রয়োজন থেকে উদ্ভূত):
//  - fetcher পেজ সাইডে থাকে → service-layer mock করা টেস্টগুলো অপরিবর্তিত থাকে।
//  - reload() boolean রিটার্ন করে (সফল/ব্যর্থ) — KnowledgePage-এর `searched`
//    gate-এর মতো সফলতা-নির্ভর page-local state এর জন্য।
//  - reload(override) — MarketplacePage-এর server-search ক্যাটালগ *replace* নয়,
//    *merge* করে; override ক্লোজার বর্তমান items পেয়ে merged list বানিয়ে দেয়।
//  - immediate: false — KnowledgePage mount-এ load করে না; user-triggered
//    search-ই এর load।

import { useCallback, useEffect, useRef, useState } from 'react';
import type { Dispatch, SetStateAction } from 'react';

export interface UseListResourceOptions<T> {
  /** প্রতিটি load-এ কল হবে; নতুন items-এর array রিটার্ন করবে (throw করলে loadError)। */
  fetcher: () => Promise<T[]>;
  /** mount-এই auto-load হবে কি না (default: true)। manual search page-এর জন্য false। */
  immediate?: boolean;
}

export interface UseListResourceResult<T> {
  items: T[];
  isLoading: boolean;
  loadError: string | null;
  /**
   * List reload করে। `override` দিলে সেটিই fetch হয় — সেক্ষেত্রে বর্তমান
   * items আর্গুমেন্ট হিসেবে পাওয়া যায় (merge-style search-এর জন্য)।
   * রিটার্ন: true = সফল, false = ব্যর্থ (loadError সেট হয়েছে)।
   */
  reload: (override?: (current: T[]) => Promise<T[]>) => Promise<boolean>;
  /** optimistic update (delete/rename ইত্যাদি) — FilesPage/ProjectsPage-এর মতো। */
  setItems: Dispatch<SetStateAction<T[]>>;
  /** page-local action (যেমন seed) শুরুর সময় পুরোনো load error মুছতে। */
  clearError: () => void;
}

export function useListResource<T>({
  fetcher,
  immediate = true,
}: UseListResourceOptions<T>): UseListResourceResult<T> {
  const [items, setItems] = useState<T[]>([]);
  // বাংলা: immediate মোডে mount-এই লোড শুরু হয়, তাই loading true থেকে শুরু;
  // manual মোডে (KnowledgePage) পেজটি আগেই loading=false ছিল — একই parity।
  const [isLoading, setIsLoading] = useState(immediate);
  const [loadError, setLoadError] = useState<string | null>(null);

  // বাংলা: fetcher প্রতি render-এ নতুন closure — page-local state (query,
  // stateFilter, installedIds setter) বন্দী করে। ref-এ সর্বশেষ closure রাখলে
  // reload() সবসময় fresh state নিয়ে fetch করে। itemsRef-ও একই কারণে — merge-style
  // override-কে হুক সর্বশেষ committed items দেয় (পেজের নিজের closure stale হতো)।
  // ইচ্ছাকৃতভাবে এই sync effect টি নিচের mount-load effect-এর *আগে* ডিক্লেয়ার করা —
  // React effects declaration-order-এ চলে বলে mount-এর প্রথম load-ও fresh মান পায়।
  // (render-এর মধ্যে ref লেখা React 19 concurrent রুলে unsafe — তাই effect।)
  const fetcherRef = useRef(fetcher);
  const itemsRef = useRef<T[]>(items);
  useEffect(() => {
    fetcherRef.current = fetcher;
    itemsRef.current = items;
  });

  const reload = useCallback(
    async (override?: (current: T[]) => Promise<T[]>): Promise<boolean> => {
      setIsLoading(true);
      setLoadError(null);
      try {
        // বাংলা: override থাকলে সেটি বর্তমান items পেয়ে merged list বানায়
        // (MarketplacePage-এর server-search merge); নাহলে সর্বশেষ fetcher closure
        // দিয়ে স্বাভাবিক replace-load হয়।
        const exec: () => Promise<T[]> = override
          ? () => override(itemsRef.current)
          : fetcherRef.current;
        setItems(await exec());
        return true;
      } catch (err) {
        setLoadError(err instanceof Error ? err.message : 'Failed to load');
        return false;
      } finally {
        setIsLoading(false);
      }
    },
    [],
  );

  useEffect(() => {
    if (immediate) void reload();
  }, [reload, immediate]);

  const clearError = useCallback(() => setLoadError(null), []);

  return { items, isLoading, loadError, reload, setItems, clearError };
}
