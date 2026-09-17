import { useT } from '../i18n/LanguageContext.jsx';

const Footer = ({ onAbout }) => {
  const t = useT();
  return (
    <footer className="footer">
      <div className="footer-text">
        <div>
          {t('footer.developedBy')} <strong>{t('footer.developer')}</strong> · {t('footer.role')}
        </div>
        <div className="footer-institution">{t('footer.institution')} · 2026</div>
      </div>
      <button type="button" className="footer-link" onClick={onAbout}>
        {t('footer.aboutLink')}
      </button>
    </footer>
  );
};

export default Footer;
