import React, { createContext, useContext, useState } from 'react';
import { enDictionary, TranslationDictionary } from './dictionaries/en';
import { hiDictionary } from './dictionaries/hi';
import { mrDictionary } from './dictionaries/mr';

export type SupportedLanguage = 'en' | 'hi' | 'mr';

export const PRIVACY_NOTICE_VERSION = 'v1.0-2026-pune';

const DICTIONARIES: Record<SupportedLanguage, TranslationDictionary> = {
  en: enDictionary,
  hi: hiDictionary,
  mr: mrDictionary,
};

export const LANGUAGE_LABELS: Record<SupportedLanguage, string> = {
  en: 'English',
  hi: 'हिंदी',
  mr: 'मराठी',
};

interface LanguageContextValue {
  language: SupportedLanguage;
  setLanguage: (lang: SupportedLanguage) => void;
  t: TranslationDictionary;
  privacyNoticeVersion: string;
}

const STORAGE_KEY = 'isoswe_preferred_lang_v1';

const LanguageContext = createContext<LanguageContextValue>({
  language: 'en',
  setLanguage: () => undefined,
  t: enDictionary,
  privacyNoticeVersion: PRIVACY_NOTICE_VERSION,
});

export const LanguageProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [language, setLanguageState] = useState<SupportedLanguage>(() => {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved === 'en' || saved === 'hi' || saved === 'mr') {
        return saved;
      }
    } catch {
      // Ignore storage access errors
    }
    return 'en';
  });

  const setLanguage = (lang: SupportedLanguage) => {
    setLanguageState(lang);
    try {
      localStorage.setItem(STORAGE_KEY, lang);
    } catch {
      // Ignore storage access errors
    }
  };

  const value: LanguageContextValue = {
    language,
    setLanguage,
    t: DICTIONARIES[language] || enDictionary,
    privacyNoticeVersion: PRIVACY_NOTICE_VERSION,
  };

  return <LanguageContext.Provider value={value}>{children}</LanguageContext.Provider>;
};

export function useLanguage(): LanguageContextValue {
  return useContext(LanguageContext);
}

export function getDictionary(lang: SupportedLanguage): TranslationDictionary {
  return DICTIONARIES[lang] || enDictionary;
}

