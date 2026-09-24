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

    // ── Metrics block ────────────────────────────────────────────────────
    const metricsBlock = [t('report.sectionMetrics')];
    if (result?.model_dsc != null)
      metricsBlock.push(row(t('metrics.dscMean'),
        `${(result.model_dsc * 100).toFixed(1)} %`));
    if (result?.model_hd95 != null)
      metricsBlock.push(row(t('metrics.hausdorff95'),
        `${result.model_hd95.toFixed(2)} mm`));
    if (result?.model_seg_sensitivity != null)
      metricsBlock.push(row(t('metrics.sensitivity'),
        `${(result.model_seg_sensitivity * 100).toFixed(1)} %`));
    if (result?.model_seg_specificity != null)
      metricsBlock.push(row(t('metrics.specificity'),
        `${(result.model_seg_specificity * 100).toFixed(1)} %`));
    if (result?.model_seg_ppv != null)
      metricsBlock.push(row(t('metrics.ppv'),
        `${(result.model_seg_ppv * 100).toFixed(1)} %`));
    if (result?.model_seg_npv != null)
      metricsBlock.push(row(t('metrics.npv'),
        `${(result.model_seg_npv * 100).toFixed(1)} %`));
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

    const lines = [...header, ...resultBlock, ...metricsBlock, ...footer]
      .filter((l) => l !== null && l !== undefined)
      .join('\n');

    const blob = new Blob([lines], { type: 'text/plain;charset=utf-8' });
    const a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = `VBM_${lang === 'en' ? 'Report' : 'Reporte'}_${info.test.replace(/\s+/g, '_')}.txt`;
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
                <div className="seg-verdict-conf">
                  <div className="seg-verdict-conf-val">
                    {Math.round((result.confidence || 0) * 100)}%
                  </div>
                  <div className="seg-verdict-conf-lab">
                    {isEpi ? t('results.segConfSens') : t('results.segConfSpec')}
                  </div>
                </div>
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

                {/* Model metrics (evaluation on 778 subjects) */}
                {result?.model_dsc != null && (
                  <div>
                    <div style={{ fontWeight: 700, fontSize: 13, marginBottom: 8, color: 'var(--t2)' }}>
                      {t('results.modelMetricsTitle')}
                    </div>
                    <div className="mtiles" style={{ gridTemplateColumns: 'repeat(3,1fr)' }}>
                      <div className="mtile">
                        <div className="mv">{(result.model_dsc * 100).toFixed(1)}%</div>
                        <div className="ml">{t('metrics.dscMean')}</div>
                      </div>
                      {result.model_hd95 != null && (
                        <div className="mtile">
                          <div className="mv">{result.model_hd95.toFixed(1)}</div>
                          <div className="ml">{t('metrics.hausdorff95')} (mm)</div>
                        </div>
                      )}
                      {result.model_seg_sensitivity != null && (
                        <div className="mtile">
                          <div className="mv">{(result.model_seg_sensitivity * 100).toFixed(1)}%</div>
                          <div className="ml">{t('metrics.sensitivity')}</div>
                        </div>
                      )}
                      {result.model_seg_specificity != null && (
                        <div className="mtile">
                          <div className="mv">{(result.model_seg_specificity * 100).toFixed(1)}%</div>
                          <div className="ml">{t('metrics.specificity')}</div>
                        </div>
                      )}
                      {result.model_seg_ppv != null && (
                        <div className="mtile tw">
                          <div className="mv">{(result.model_seg_ppv * 100).toFixed(1)}%</div>
                          <div className="ml">{t('metrics.ppv')}</div>
                          <div className="tt">{t('metrics.ppvTooltip')}</div>
                        </div>
                      )}
                      {result.model_seg_npv != null && (
                        <div className="mtile tw">
                          <div className="mv">{(result.model_seg_npv * 100).toFixed(1)}%</div>
                          <div className="ml">{t('metrics.npv')}</div>
                          <div className="tt">{t('metrics.npvTooltip')}</div>
                        </div>
                      )}
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
              downloadMask(jobId, `VBM_mask_${info.test.replace(/\s+/g, '_')}.nii.gz`)
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
