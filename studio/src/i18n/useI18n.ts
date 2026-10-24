import { useContext } from 'react';
import { I18nContext } from './I18nContext';

// বাংলা মন্তব্য: useI18n hook এখানে সরাসরি ডিফাইন করা হয়েছে, যাতে I18nProvider.tsx এ রেফ্রেশ সমস্যা না হয়
export const useI18n = () => useContext(I18nContext);
