import React, { useEffect, useMemo, useState } from 'react';
import { useTranslation } from '../hooks/useTranslation';
import { I18nContext } from './I18nContext';
import { locales, type Locale } from './config';
import { apiClient } from '../services/apiClient';

const LOCALE_KEY = 'supreme_lang';

function readStoredLocale(fallback: Locale): Locale {
  if (typeof window === 'undefined') return fallback;
  const stored = window.localStorage.getItem(LOCALE_KEY);
  return stored && locales.includes(stored as Locale) ? (stored as Locale) : fallback;
}

export const TranslationProvider = ({ locale: initialLocale, children }: { locale?: Locale; children: React.ReactNode }) => {
  const fallbackLocale = initialLocale ?? 'en';
  const [locale, setLocaleState] = useState<Locale>(() => readStoredLocale(fallbackLocale));
  const { t } = useTranslation(locale);

  useEffect(() => {
    if (typeof window !== 'undefined') window.localStorage.setItem(LOCALE_KEY, locale);
  }, [locale]);

  const setLocale = (next: Locale) => {
    if (!locales.includes(next)) return;
    setLocaleState(next);
    // ERR-H01 FIX: real backend route is POST /api/preferences/ (no PUT, no
    // /api/user/preferences path); locale persists as preferred_language.
    // Issue #2475: exact canonical path (trailing slash) — no 307 redirect hop.
    void apiClient.post('/api/preferences/', {
      preferred_language: next,
    }).catch(() => {
      // Local state remains usable when the account is offline or unauthenticated.
    });
  };

  const value = useMemo(() => ({ t, locale, setLocale }), [locale, t]);
  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
};
