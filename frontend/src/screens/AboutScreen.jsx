import logoUV from '../assets/images/logo-uv.png';
import logoLab from '../assets/images/Multimedia-y-visin-logo.png';
import { useT } from '../i18n/LanguageContext.jsx';

const AboutScreen = ({ onBack }) => {
  const t = useT();
  return (
    <div className="fu">
      <button className="btn btn-g btn-sm" onClick={onBack} style={{ marginBottom: 22 }}>
        {t('about.back')}
      </button>

      <div className="about-hero">
        <img src={logoUV} alt="Universidad del Valle" className="about-logo-uv" />
        <img src={logoLab} alt="Multimedia y Visión por Computador" className="about-logo-lab" />
      </div>

      <h1 className="about-title">{t('about.title')}</h1>

      <div className="card about-section">
        <h2 className="about-h2">{t('about.toolSection')}</h2>
        <p className="about-p">{t('about.toolBody')}</p>
      </div>

      <div className="card about-section">
        <h2 className="about-h2">{t('about.teamSection')}</h2>
        <div className="about-grid">
          <div>
            <div className="about-label">{t('about.teamDev')}</div>
            <div className="about-value">
              <strong>Kevin Velez</strong>
              <br />
              {t('footer.role')}
            </div>
          </div>
          <div>
            <div className="about-label">{t('about.teamDirector')}</div>
            <div className="about-value">{t('about.teamDirectorName')}</div>
          </div>
          <div>
            <div className="about-label">{t('about.teamCoDirectors')}</div>
            <div className="about-value" style={{ whiteSpace: 'pre-line' }}>
              {t('about.teamCoDirectorsNames')}
            </div>
          </div>
          <div>
            <div className="about-label">{t('about.teamLab')}</div>
            <div className="about-value">{t('about.teamLabName')}</div>
          </div>
          <div>
            <div className="about-label">{t('about.teamInstitution')}</div>
            <div className="about-value">{t('about.teamInstitutionName')}</div>
          </div>
        </div>
      </div>

      <div className="card about-section">
        <h2 className="about-h2">{t('about.techSection')}</h2>
        <p className="about-p">{t('about.techBackend')}</p>
        <p className="about-p" style={{ marginTop: 6 }}>{t('about.techFrontend')}</p>
      </div>

      <div className="wb" style={{ marginTop: 20 }}>
        <span style={{ fontSize: 22, flexShrink: 0 }}>⚕️</span>
        <div>
          <strong>{t('about.disclaimerSection')}.</strong> {t('about.disclaimerBody')}
        </div>
      </div>
    </div>
  );
};

export default AboutScreen;
