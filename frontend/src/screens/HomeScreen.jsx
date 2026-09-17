import Brain from '../components/Brain.jsx';
import { MODELS } from '../data/models.js';
import { useT } from '../i18n/LanguageContext.jsx';

const CONTACT_EMAIL = 'kevin.alejandro.velez@correounivalle.edu.co';

const HomeScreen = ({ onSelect, assets }) => {
  const t = useT();
  const isReady = (id) => !assets || assets[id]?.ready !== false;
  const missingAny = assets && MODELS.some((m) => assets[m.id]?.ready === false);
  return (
    <div className="fu">
      <div className="hero">
        <div style={{ display: 'inline-block', marginBottom: 20 }}>
          <Brain size={82} color="var(--primary)" glow />
        </div>
        <h1>
          {t('home.heroTitleA')} <span>{t('home.heroTitleHl')}</span>
          {t('home.heroTitleB') ? (<><br />{t('home.heroTitleB')}</>) : null}
        </h1>
        <p style={{ marginTop: 10 }}>{t('home.heroLead')}</p>
        <p style={{ fontSize: 14, color: 'var(--t3)', marginTop: 6 }}>{t('home.heroCta')}</p>
      </div>

      <div className="ib" style={{ marginBottom: 24 }}>
        <span>⏱️</span>
        <span
          dangerouslySetInnerHTML={{
            __html: t('home.durationBanner', { range: `<strong>${t('home.durationRange')}</strong>` }),
          }}
        />
      </div>

      {missingAny && (
        <div className="wb" style={{ marginBottom: 24 }}>
          <span style={{ fontSize: 20, flexShrink: 0 }}>⚠</span>
          <div>
            <strong>{t('home.assetsWarnTitle')}</strong>{' '}
            {MODELS.filter((m) => assets[m.id]?.ready === false).map((m) => t(`models.${m.id}.name`)).join(', ')}.{' '}
            {t('home.assetsWarnBody')}{' '}
            <a href={`mailto:${CONTACT_EMAIL}`} style={{ color: 'var(--pd)', fontWeight: 600 }}>
              {CONTACT_EMAIL}
            </a>.
          </div>
        </div>
      )}

      <div
        className="mgrid"
        style={{
          display: 'grid',
          gridTemplateColumns: `repeat(${Math.min(MODELS.length, 3)}, minmax(0, 1fr))`,
          gap: 22,
          maxWidth: MODELS.length === 2 ? 720 : '100%',
          margin: '0 auto',
        }}
      >
        {MODELS.map((m) => {
          const ready = isReady(m.id);
          return (
          <div
            key={m.id}
            className={`mcard${m.recommended ? ' rec' : ''}${ready ? '' : ' disabled'}`}
            onClick={ready ? () => onSelect(m) : undefined}
            title={ready ? undefined : t('home.modelUnavailable')}
          >
            {m.recommended && ready && <div className="rec-lbl">{t('home.recommended')}</div>}
            {!ready && <div className="rec-lbl rec-lbl-bad">{t('home.unavailableBadge')}</div>}
            <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
              <div
                style={{
                  width: 48,
                  height: 48,
                  borderRadius: 14,
                  background: 'var(--pl)',
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  flexShrink: 0,
                }}
              >
                <Brain size={30} color="var(--primary)" />
              </div>
              <div>
                <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 3 }}>{t(`models.${m.id}.name`)}</div>
                <span className={`badge ${m.badge === 'segmentation' ? 'b-am' : 'b-bl'}`}>
                  {t(`badge.${m.badge}`)}
                </span>
              </div>
            </div>
            <p style={{ fontSize: 13.5, color: 'var(--t2)', lineHeight: 1.6 }}>{t(`models.${m.id}.desc`)}</p>
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginTop: 2 }}>
              <div className="tw">
                <div
                  style={{
                    display: 'flex',
                    alignItems: 'center',
                    gap: 6,
                    background: 'var(--pl)',
                    padding: '6px 12px',
                    borderRadius: 99,
                    cursor: 'help',
                  }}
                >
                  <span style={{ fontWeight: 800, color: 'var(--primary)', fontSize: 17 }}>{m.metricVal}</span>
                  <span style={{ fontSize: 11.5, color: 'var(--pd)', fontWeight: 600 }}>
                    {t(`metrics.${m.metricLabel}`)}
                  </span>
                </div>
                <div className="tt">{t(`models.${m.id}.tooltip`)}</div>
              </div>
              <span style={{ fontSize: 12.5, color: 'var(--t3)' }}>{t('home.stepsCount', { n: m.steps.length })}</span>
            </div>
          </div>
          );
        })}
      </div>
    </div>
  );
};

export default HomeScreen;
