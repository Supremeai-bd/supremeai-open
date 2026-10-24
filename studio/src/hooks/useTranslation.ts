import { locales, type Locale } from '../i18n/config';
import { translations } from '../i18n/translations';

type TranslationValues = typeof translations.en;
export type TranslationKey = keyof TranslationValues;
export type StringTranslationKey = {
  [K in TranslationKey]: TranslationValues[K] extends string ? K : never;
}[TranslationKey];

export function useTranslation(locale: Locale = 'en') {
  const current = locales.includes(locale) ? locale : 'en';
  const t = (key: StringTranslationKey, params?: Record<string, string | number>): string => {
    let value = translations[current][key] ?? translations.en[key] ?? key;
    // বাংলা মন্তব্য: কিছু ট্রান্সলেশন এন্ট্রি নেস্টেড অবজেক্ট, তাই শুধু string হলেই প্যারামিটার ইন্টারপোলেট হবে
    if (params && typeof value === 'string') {
      Object.entries(params).forEach(([k, v]) => {
        value = (value as string).replace(`{${k}}`, String(v));
      });
    }
    return value;
  };

  return { t, locale, setLocale: (_next: Locale) => {} };
}
