import { useLang } from '../i18n/LanguageContext.jsx';

const LanguageToggle = () => {
  const [lang, setLang] = useLang();
  return (
    <div className="lang-toggle" role="group" aria-label="Language">
      <button
        type="button"
        className={`lang-btn${lang === 'es' ? ' active' : ''}`}
        onClick={() => setLang('es')}
        aria-pressed={lang === 'es'}
      >
        ES
      </button>
      <span className="lang-sep">|</span>
      <button
        type="button"
        className={`lang-btn${lang === 'en' ? ' active' : ''}`}
        onClick={() => setLang('en')}
        aria-pressed={lang === 'en'}
      >
        EN
      </button>
    </div>
  );
};

export default LanguageToggle;
