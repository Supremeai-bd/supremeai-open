export const locales = ['en', 'bn', 'es', 'zh'] as const;

export type Locale = (typeof locales)[number];

export const localeNames: Record<Locale, string> = {
  en: 'English',
  bn: 'Bengali',
  es: 'Spanish',
  zh: 'Chinese',
};
