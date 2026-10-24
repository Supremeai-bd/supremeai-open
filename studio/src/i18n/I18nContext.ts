import { createContext } from 'react';
import type { Locale } from './config';
import type { StringTranslationKey } from '../hooks/useTranslation';

export interface I18nContextValue {
  t: (key: StringTranslationKey, params?: Record<string, string | number>) => string;
  locale: Locale;
  setLocale: (next: Locale) => void;
}

export const I18nContext = createContext<I18nContextValue>({
  t: (key) => key,
  locale: 'en',
  setLocale: () => undefined,
});
