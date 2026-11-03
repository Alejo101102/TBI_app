import Brain from '../components/Brain.jsx';
import NiiVueViewer from '../components/NiiVueViewer.jsx';
import { useT, useLang } from '../i18n/LanguageContext.jsx';
import { getT1URL, getMaskURL, downloadMask } from '../api/client.js';

// Format seconds as "Mm Ss" (e.g. "5m 23s") or "Xs" when under a minute.
// Used both in the UI tile and the exported .txt report.
const fmtTime = (seconds) => {
  if (seconds == null) return '—';
  const total = Math.round(seconds);
  const m = Math.floor(total / 60);
  const s = total % 60;
  return m ? `${m}m ${String(s).padStart(2, '0')}s` : `${s}s`;
};

// Model metrics sent by the backend (constants from the TCEC test set):
// [translation key under metrics.*, field in the result].
const MODEL_METRICS = [
  ['dscMean',      'model_dsc'],
  ['iou',          'model_iou'],
  ['detSmall',     'model_det_small'],
  ['detMedium',    'model_det_medium'],
  ['detLarge',     'model_det_large'],
  ['fpProportion', 'model_fp_proportion'],
  ['fpPerSubject', 'model_fp_per_subject'],
];

// FP per subject is a count; every other metric is a fraction shown as %.
const fmtMetric = (field, value) =>
  field === 'model_fp_per_subject' ? value.toFixed(2) : `${(value * 100).toFixed(1)} %`;

// Padded "Label : value" row for the exported plain-text report.
// Keeps all colons in the same column for a clean look.
const row = (label, value, width = 22) =>
  `  ${label.padEnd(width)}: ${value}`;

const ResultsScreen = ({ model, info, file, jobId, result, onReset }) => {
  const t = useT();
  const [lang] = useLang();
  const isEpi = result?.prediction === 'epilepsy';

  const genTxt = () => {
    const locale = lang === 'en' ? 'en-US' : 'es-CO';
    const now = new Date().toLocaleString(locale);
    const sepEq   = '═'.repeat(60);
    const sepDash = '─'.repeat(60);

    // ── Header block (always present) ────────────────────────────────────
    const header = [
      sepEq,
      `   ${t('report.header')}`,
      sepEq,
      '',
      row(t('report.date'),    now),
      row(t('report.model'),   t(`models.${model.id}.fullName`)),
      row(t('report.test'),    info.test),
      row(t('report.patient'), info.patient || t('report.notSpecified')),
      row(t('report.file'),    file?.name || ''),
      result?.processing_time_s != null
        ? row(t('results.processingTime'), fmtTime(result.processing_time_s))
        : null,
      result?.preprocessed != null
        ? row(t('report.preprocessing'), result.preprocessed ? t('report.preprocYes') : t('report.preprocNo'))
        : null,
      row(t('report.space'), t('report.spaceVal')),
      '',
    ];

    // ── Result block (segmentation) ───────────────────────────────────────
    const resultBlock = [t('report.sectionResult')];
    resultBlock.push(
      row(t('report.type'), t('report.typeSeg')),
      result?.mask_volume_cm3 != null
        ? row(t('results.maskVolume'),     `${result.mask_volume_cm3.toFixed(2)} cm³`) : null,
      result?.n_clusters != null
        ? row(t('results.nClusters'),      String(result.n_clusters)) : null,
      result?.largest_cluster_cm3 != null && result?.n_clusters > 1
        ? row(t('results.largestCluster'), `${result.largest_cluster_cm3.toFixed(2)} cm³`) : null,
      result?.mask_voxels != null
        ? row(t('results.maskVoxels'),     result.mask_voxels.toLocaleString()) : null,
      row(t('report.mask'), t('report.maskAvail')),
    );
    resultBlock.push('');

    // ── Lesion list + size summary (one entry per cluster of the mask) ────
    const lesions = result?.lesions || [];
    const count   = (cat) => lesions.filter((l) => l.category === cat).length;
    const nSmall  = count('small');
    const lesionBlock = [];
    if (result?.lesions != null) {
      lesionBlock.push(
        t('report.sectionLesions'),
        row(t('report.sizeSummary'),
          t('report.sizeSummaryVal', { s: nSmall, m: count('medium'), l: count('large') })),
      );
      lesions.forEach((l, i) => {
        const [x, y, z] = l.centroid_vox;
        lesionBlock.push(`  ${t('report.lesionLine', {
          n: i + 1, vol: l.volume_mm3.toFixed(1), cat: t(`report.cat.${l.category}`),
          a: l.slice_min, b: l.slice_max, x, y, z,
        })}`);
      });
      if (lesions.length) lesionBlock.push(`  ${t('report.lesionsNote')}`);
      lesionBlock.push('');
    }

    // ── Notices that depend on this subject's mask ───────────────────────
    const pct = (v) => (v != null ? `${(v * 100).toFixed(1)} %` : '—');
    const notices = [];
    if (result?.lesions != null) {
      if (lesions.length === 0)
        notices.push(t('report.noticeEmpty', { det: pct(result.model_det_small) }));
      if (nSmall > 0)
        notices.push(t('report.noticeSmall', { n: nSmall, det: pct(result.model_det_small) }));
      if (nSmall >= 2)
        notices.push(t('report.noticeFp', { n: nSmall, fp: pct(result.model_fp_proportion) }));
    }
    const noticeBlock = notices.length
      ? [t('report.sectionNotices'), ...notices.map((n) => `  ${n}`), '']
      : [];

    // ── Metrics block ────────────────────────────────────────────────────
    const metricsBlock = [t('report.sectionMetrics')];
    for (const [key, field] of MODEL_METRICS) {
      if (result?.[field] != null) metricsBlock.push(row(t(`metrics.${key}`), fmtMetric(field, result[field])));
    }
    metricsBlock.push('');

    // ── Footer with disclaimer ───────────────────────────────────────────
    const footer = [
      sepDash,
      t('report.sectionWarn'),
      t('report.warn1'),
      t('report.warn2'),
      info.notes ? `\n${t('report.notes')} ${info.notes}` : null,
      '',
      sepEq,
      t('report.footerLine'),
      sepEq,
      '',
    ];

    const lines = [...header, ...resultBlock, ...lesionBlock, ...noticeBlock, ...metricsBlock, ...footer]
      .filter((l) => l !== null && l !== undefined)
      .join('\n');

    const blob = new Blob([lines], { type: 'text/plain;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `TBI_${lang === 'en' ? 'Report' : 'Reporte'}_${info.test.replace(/\s+/g, '_')}.txt`;
    a.click();
    URL.revokeObjectURL(a.href);
  };

  return (
    <div className="fu">
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 28 }}>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <div
            style={{
              width: 42, height: 42, borderRadius: 12, background: 'var(--pl)',
              display: 'flex', alignItems: 'center', justifyContent: 'center',
            }}
          >
            <Brain size={26} color="var(--primary)" />
          </div>
          <div>
            <div style={{ fontWeight: 700, fontSize: 19 }}>{t('results.title')}</div>
            <div style={{ fontSize: 13.5, color: 'var(--t2)' }}>
              {t(`models.${model.id}.fullName`)} · <strong>{info.test}</strong>
              {info.patient ? ` · ${info.patient}` : ''}
            </div>
          </div>
        </div>
        <button className="btn btn-g btn-sm" onClick={onReset}>{t('results.back')}</button>
      </div>

      <div className="card" style={{ marginBottom: 20 }}>
        <div>
          {/* ── Verdict banner: classification derived from the mask ──── */}
          {result?.prediction && (
              <div className={`seg-verdict ${isEpi ? 'sv-pos' : 'sv-neg'}`}>
                <div className="seg-verdict-main">
                  <span className="seg-verdict-icon">{isEpi ? '⚠' : '✓'}</span>
                  <div>
                    <div className="seg-verdict-title">
                      {isEpi ? t('results.segVerdictEpi') : t('results.segVerdictControl')}
                    </div>
                    <div className="seg-verdict-sub">
                      {isEpi
                        ? t('results.segVerdictEpiSub', { vol: result.mask_volume_cm3.toFixed(2), n: result.n_clusters })
                        : t('results.segVerdictControlSub')}
                    </div>
                  </div>
                </div>
                {result.confidence != null && (
                  <div className="seg-verdict-conf">
                    <div className="seg-verdict-conf-val">
                      {Math.round(result.confidence * 100)}%
                    </div>
                    <div className="seg-verdict-conf-lab">
                      {isEpi ? t('results.segConfSens') : t('results.segConfSpec')}
                    </div>
                  </div>
                )}
              </div>
            )}

            {/* 2-column layout: data on the left, square viewer on the right */}
            <div className="seg-layout">
              <div className="seg-data">
                <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 10 }}>
                  {t('results.segCompletedTitle')}
                </div>

                {/* Mask tiles — 2 columns */}
                <div className="mtiles" style={{ gridTemplateColumns: 'repeat(2,1fr)', marginBottom: 16 }}>
                  {result?.mask_volume_cm3 != null && (
                    <div className="mtile">
                      <div className="mv">{result.mask_volume_cm3.toFixed(2)}</div>
                      <div className="ml">{t('results.maskVolume')} (cm³)</div>
                    </div>
                  )}
                  {result?.n_clusters != null && (
                    <div className="mtile">
                      <div className="mv">{result.n_clusters}</div>
                      <div className="ml">{t('results.nClusters')}</div>
                    </div>
                  )}
                  {result?.largest_cluster_cm3 != null && result?.n_clusters > 1 && (
                    <div className="mtile">
                      <div className="mv">{result.largest_cluster_cm3.toFixed(2)}</div>
                      <div className="ml">{t('results.largestCluster')} (cm³)</div>
                    </div>
                  )}
                  {result?.mask_voxels != null && (
                    <div className="mtile">
                      <div className="mv">{result.mask_voxels.toLocaleString()}</div>
                      <div className="ml">{t('results.maskVoxels')}</div>
                    </div>
                  )}
                </div>

                {/* Model metrics (TCEC test set: 57 images, 230 lesions) */}
                {result?.model_dsc != null && (
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 8, color: 'var(--t2)' }}>
                      {t('results.modelMetricsTitle')}
                    </div>
                    <div className="mtiles" style={{ gridTemplateColumns: 'repeat(3,1fr)' }}>
                      {MODEL_METRICS.filter(([, field]) => result[field] != null).map(([key, field]) => (
                        <div className="mtile" key={field}>
                          <div className="mv">{fmtMetric(field, result[field]).replace(' %', '%')}</div>
                          <div className="ml">{t(`metrics.${key}`)}</div>
                        </div>
                      ))}
                    </div>
                    <div style={{ fontSize: 11, color: 'var(--t3)', marginTop: 8, lineHeight: 1.5 }}>
                      {t('results.modelMetricsFootnote')}
                    </div>
                  </div>
                )}
              </div>

              <div className="seg-viewer">
                {jobId && (
                  <NiiVueViewer
                    t1Url={getT1URL(jobId)}
                    maskUrl={getMaskURL(jobId)}
                    jobId={jobId}
                    onError={(err) => console.error('Viewer:', err)}
                  />
                )}
              </div>
            </div>
          </div>
      </div>

      <div className="wb" style={{ marginBottom: 20 }}>
        <span style={{ fontSize: 22, flexShrink: 0 }}>⚕️</span>
        <div>
          <strong>{t('results.disclaimerBold')}</strong> {t('results.disclaimerBody')}{' '}
          <strong>{t('results.disclaimerEm')}</strong>
          {t('results.disclaimerRest')}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 12, justifyContent: 'flex-end', flexWrap: 'wrap' }}>
        {model.type === 'segmentation' && jobId && (
          <button
            className="btn btn-ok"
            onClick={() =>
              downloadMask(jobId, `TBI_mask_${info.test.replace(/\s+/g, '_')}.nii.gz`)
                .catch((e) => alert(`${t('results.downloadMaskError') || 'Download error'}: ${e.message || e}`))
            }
          >
            {t('results.downloadMaskLong')}
          </button>
        )}
        <button className="btn btn-g" onClick={genTxt}>{t('results.exportTxt')}</button>
        <button className="btn btn-p" onClick={onReset}>{t('results.newAnalysis')}</button>
      </div>
    </div>
  );
};

export default ResultsScreen;
