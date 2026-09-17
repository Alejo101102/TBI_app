import { createContext, useContext, useState, useCallback } from 'react';
import { TRANSLATIONS } from './translations.js';

const STORAGE_KEY = 'vbm.lang';
const DEFAULT_LANG = 'es';

const LanguageContext = createContext(null);

const interpolate = (template, vars) => {
  if (!vars) return template;
  return template.replace(/\{(\w+)\}/g, (_, k) => (k in vars ? String(vars[k]) : `{${k}}`));
};

export const LanguageProvider = ({ children }) => {
  const [lang, setLangState] = useState(() => {
    if (typeof window === 'undefined') return DEFAULT_LANG;
    const saved = window.localStorage.getItem(STORAGE_KEY);
    return saved === 'es' || saved === 'en' ? saved : DEFAULT_LANG;
  });

  const setLang = useCallback((next) => {
    setLangState(next);
    try {
      window.localStorage.setItem(STORAGE_KEY, next);
    } catch {}
  }, []);

  const t = useCallback(
    (key, vars) => {
      const dict = TRANSLATIONS[lang] || TRANSLATIONS[DEFAULT_LANG];
      const raw = dict[key];
      if (raw === undefined) {
        if (import.meta.env?.DEV) console.warn(`[i18n] Missing key: ${key} (${lang})`);
        return `[${key}]`;
      }
      return interpolate(raw, vars);
    },
    [lang]
  );

  return (
    <LanguageContext.Provider value={{ lang, setLang, t }}>{children}</LanguageContext.Provider>
  );
};

export const useT = () => {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error('useT must be used within a LanguageProvider');
  return ctx.t;
};

export const useLang = () => {
  const ctx = useContext(LanguageContext);
  if (!ctx) throw new Error('useLang must be used within a LanguageProvider');
  return [ctx.lang, ctx.setLang];
};
