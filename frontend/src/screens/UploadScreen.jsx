import { useState } from 'react';
import DropZone from '../components/DropZone.jsx';
import { useT } from '../i18n/LanguageContext.jsx';
import { postAnalyze } from '../api/client.js';

// Public NITRC download page for ROBEX v1.2 (requires accepting the license).
const ROBEX_URL = 'https://www.nitrc.org/projects/robex';

const UploadScreen = ({ model, assets, onStart, onBack }) => {
  const t = useT();
  const [info, setInfo] = useState({ test: '', patient: '', notes: '', useRobex: false });
  const [file, setFile] = useState(null);
  const [uploading, setUploading] = useState(false);
  const [uploadError, setUploadError] = useState(null);
  const u = (k, v) => setInfo((p) => ({ ...p, [k]: v }));
  // Force-off the toggle if ROBEX is missing on the backend.
  const robexAvailable = !assets || assets.robex?.ready !== false;
  const modelAvailable = !assets || assets[model.id]?.ready !== false;
  const ok = file && info.test.trim() && !uploading && modelAvailable;

  const handleStart = async () => {
    setUploading(true);
    setUploadError(null);
    try {
      const { job_id } = await postAnalyze(file, info, model.id);
      onStart(info, file, job_id);
    } catch (e) {
      setUploadError(e.message || String(e));
      setUploading(false);
    }
  };

  return (
    <div className="fu">
      <div style={{ display: 'flex', alignItems: 'center', gap: 12, marginBottom: 28 }}>
        <button className="btn btn-g btn-sm" onClick={onBack} disabled={uploading}>{t('upload.back')}</button>
        <div>
          <div style={{ fontWeight: 700, fontSize: 19 }}>{t(`models.${model.id}.fullName`)}</div>
          <div style={{ fontSize: 13.5, color: 'var(--t2)' }}>
            {t(`metrics.${model.metricLabel}`)}: {model.metricVal} · {t(`badge.${model.badge}`)}
          </div>
        </div>
      </div>

      <div className="fgrid" style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 22 }}>
        <div className="card" style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
          <div>
            <div style={{ fontWeight: 700, fontSize: 17, marginBottom: 3 }}>{t('upload.infoTitle')}</div>
            <div style={{ fontSize: 13, color: 'var(--t3)' }}>{t('upload.infoSubtitle')}</div>
          </div>
          <div className="ff">
            <label className="fl">{t('upload.testLabel')}</label>
            <input
              className="fi"
              placeholder={t('upload.testPh')}
              value={info.test}
              onChange={(e) => u('test', e.target.value)}
              disabled={uploading}
            />
          </div>
          <div className="ff">
            <label className="fl">{t('upload.patientLabel')}</label>
            <input
              className="fi"
              placeholder={t('upload.patientPh')}
              value={info.patient}
              onChange={(e) => u('patient', e.target.value)}
              disabled={uploading}
            />
          </div>
          <div className="ff">
            <label className="fl">{t('upload.notesLabel')}</label>
            <textarea
              className="fta"
              rows={3}
              placeholder={t('upload.notesPh')}
              value={info.notes}
              onChange={(e) => u('notes', e.target.value)}
              disabled={uploading}
            />
          </div>

          {/* ROBEX skull stripping toggle */}
          <label className={`opt-toggle${(uploading || !robexAvailable) ? ' opt-disabled' : ''}`}>
            <input
              type="checkbox"
              checked={info.useRobex && robexAvailable}
              onChange={(e) => u('useRobex', e.target.checked)}
              disabled={uploading || !robexAvailable}
            />
            <div className="opt-text">
              <div className="opt-title">{t('upload.robexLabel')}</div>
              <div className="opt-hint">{t('upload.robexHint')}</div>
              {!robexAvailable && (
                <div className="opt-warn">
                  ⚠ {t('upload.robexMissing')}{' '}
                  <a href={ROBEX_URL} target="_blank" rel="noopener noreferrer">
                    {ROBEX_URL}
                  </a>
                </div>
              )}
            </div>
          </label>

          <div className="ib" style={{ fontSize: 12.5 }}>
            <span>ℹ️</span>
            <span
              dangerouslySetInnerHTML={{
                __html: t('upload.oneImage', { bold: `<strong>${t('upload.oneImageBold')}</strong>` }),
              }}
            />
          </div>
        </div>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
          <div className="card">
            <div style={{ fontWeight: 700, fontSize: 15, marginBottom: 13 }}>{t('upload.t1Title')}</div>
            <DropZone file={file} onChange={uploading ? () => {} : setFile} />
          </div>
          <div
            className="card"
            style={{ background: 'var(--pl)', borderColor: 'oklch(0.86 0.06 235)', padding: '18px 20px' }}
          >
            <div style={{ fontWeight: 700, fontSize: 13.5, color: 'var(--pd)', marginBottom: 10 }}>
              {t('upload.stepsTitle')} · {model.steps.length}
            </div>
            {model.steps.map((stepKey, i) => (
              <div
                key={i}
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 9,
                  padding: '5px 0',
                  borderBottom: i < model.steps.length - 1 ? '1px solid oklch(0.89 0.05 235)' : 'none',
                }}
              >
                <div
                  style={{
                    width: 22,
                    height: 22,
                    borderRadius: '50%',
                    background: 'white',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: 11,
                    fontWeight: 700,
                    color: 'var(--primary)',
                    flexShrink: 0,
                  }}
                >
                  {i + 1}
                </div>
                <span style={{ fontSize: 13, color: 'var(--pd)' }}>{t(`steps.${stepKey}.name`)}</span>
              </div>
            ))}
          </div>
        </div>
      </div>

      {!modelAvailable && (
        <div className="wb" style={{ marginTop: 18, color: 'var(--bad)', borderColor: 'oklch(.86 .09 25)', background: 'var(--badl)' }}>
          <span style={{ flexShrink: 0 }}>⚠</span>
          <span>
            {t('upload.modelMissing', { model: t(`models.${model.id}.name`) })}{' '}
            <a href="mailto:kevin.alejandro.velez@correounivalle.edu.co"
               style={{ color: 'var(--bad)', fontWeight: 700 }}>
              kevin.alejandro.velez@correounivalle.edu.co
            </a>
          </span>
        </div>
      )}

      {uploadError && (
        <div className="wb" style={{ marginTop: 18, color: 'var(--bad)', borderColor: 'oklch(.86 .09 25)', background: 'var(--badl)' }}>
          <span style={{ flexShrink: 0 }}>⚠</span>
          <span>{t('upload.uploadError', { msg: uploadError })}</span>
        </div>
      )}

      <div
        style={{
          display: 'flex',
          justifyContent: 'flex-end',
          alignItems: 'center',
          gap: 12,
          marginTop: 24,
          flexWrap: 'wrap',
        }}
      >
        {!ok && !uploading && (
          <span style={{ fontSize: 13, color: 'var(--t3)' }}>
            {!file ? t('upload.warnFile') : !info.test.trim() ? t('upload.warnName') : ''}
          </span>
        )}
        {uploading && (
          <span style={{ fontSize: 13, color: 'var(--primary)', display: 'flex', alignItems: 'center', gap: 8 }}>
            <span className="spin" /> {t('upload.uploading')}
          </span>
        )}
        <button className="btn btn-g" onClick={onBack} disabled={uploading}>{t('upload.cancel')}</button>
        <button className="btn btn-p btn-lg" disabled={!ok} onClick={handleStart}>
          {t('upload.start')}
        </button>
      </div>
    </div>
  );
};

export default UploadScreen;
