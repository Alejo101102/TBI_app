import { useState, useEffect, useRef } from 'react';
import Brain from '../components/Brain.jsx';
import Spinner from '../components/Spinner.jsx';
import { useT } from '../i18n/LanguageContext.jsx';
import { getStatus } from '../api/client.js';

const POLL_INTERVAL_MS = 1500;

const ProcessingScreen = ({ model, info, jobId, onCancel, onDone }) => {
  const t = useT();
  const [progress, setProgress] = useState(0);
  const [backendSteps, setBackendSteps] = useState([]);
  const [jobStatus, setJobStatus] = useState('pending');
  const [jobError, setJobError] = useState(null);
  const [fetchError, setFetchError] = useState(null);
  const cancelled = useRef(false);

  useEffect(() => {
    cancelled.current = false;
    let timer = null;

    const tick = async () => {
      if (cancelled.current) return;
      try {
        const data = await getStatus(jobId);
        if (cancelled.current) return;

        setProgress(data.progress);
        setBackendSteps(data.steps);
        setJobStatus(data.status);
        setFetchError(null);

        if (data.status === 'completed' && data.result) {
          onDone(data.result);
          return;
        }
        if (data.status === 'error') {
          setJobError(data.error || 'unknown');
          return;
        }
        timer = setTimeout(tick, POLL_INTERVAL_MS);
      } catch (e) {
        setFetchError(e.message || String(e));
        timer = setTimeout(tick, POLL_INTERVAL_MS * 2);
      }
    };

    tick();
    return () => {
      cancelled.current = true;
      if (timer) clearTimeout(timer);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [jobId]);

  // Status per step index (aligned with the frontend's model.steps)
  const stepStatus = (i) => {
    const bs = backendSteps[i];
    if (!bs) return 'pend';
    switch (bs.status) {
      case 'completed': return 'done';
      case 'in_progress': return 'act';
      case 'error': return 'err';
      default: return 'pend';
    }
  };

  const allDone = jobStatus === 'completed';
  const hasError = jobStatus === 'error';

  // The current step displayed in "Step X of Y"
  const activeIndex = backendSteps.findIndex(s => s.status === 'in_progress');
  const doneCount   = backendSteps.filter(s => s.status === 'completed').length;
  const displayStepNum = hasError
    ? doneCount + 1
    : activeIndex >= 0
      ? activeIndex + 1
      : Math.min(doneCount + (allDone ? 0 : 1), model.steps.length);

  return (
    <div className="fu">
      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 30 }}>
        <div>
          <div style={{ fontWeight: 700, fontSize: 19 }}>{t(`models.${model.id}.fullName`)}</div>
          <div style={{ fontSize: 13.5, color: 'var(--t2)', marginTop: 3 }}>
            {t('processing.test')} <strong>{info.test}</strong>
            {info.patient ? ` · ${info.patient}` : ''}
            {jobId && <span style={{ marginLeft: 10, color: 'var(--t3)', fontSize: 12, fontFamily: 'monospace' }}>#{jobId}</span>}
          </div>
        </div>
        <button className="btn btn-d btn-sm" onClick={onCancel}>
          <span className="btn-stop-icon" aria-hidden="true" />
          {t('processing.cancel')}
        </button>
      </div>

      <div className="rgrid" style={{ display: 'grid', gridTemplateColumns: '260px 1fr', gap: 24 }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 18 }}>
          <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '22px 0', position: 'relative' }}>
            <div style={{ position: 'relative', width: 140, height: 140 }}>
              {!allDone && !hasError &&
                [0, 1, 2].map((i) => (
                  <div
                    key={i}
                    style={{
                      position: 'absolute',
                      inset: 0,
                      borderRadius: '50%',
                      border: '2px solid oklch(0.50 0.18 242 / 0.22)',
                      animation: `ripple 2s ease ${i * 0.65}s infinite`,
                    }}
                  />
                ))}
              <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                <Brain size={78} color={hasError ? 'var(--bad)' : 'var(--primary)'} glow={!allDone && !hasError} />
              </div>
            </div>
          </div>

          <div className="card" style={{ textAlign: 'center', padding: '28px 24px' }}>
            <div style={{ fontSize: 13, color: 'var(--t3)', marginBottom: 14 }}>{t('processing.generalProgress')}</div>
            <div className="pt" style={{ marginBottom: 16, height: 9 }}>
              <div className="pf" style={{ width: `${progress}%`, background: hasError ? 'var(--bad)' : undefined }} />
            </div>
            <div style={{ fontWeight: 800, fontSize: 34, color: hasError ? 'var(--bad)' : 'var(--primary)', lineHeight: 1 }}>{progress}%</div>
            <div style={{ fontSize: 13, color: 'var(--t3)', marginTop: 10 }}>
              {t('processing.stepNofM', {
                cur: displayStepNum,
                total: model.steps.length,
              })}
            </div>
          </div>

          {!hasError && (
            <div className="wb" style={{ fontSize: 12.5 }}>
              <span style={{ flexShrink: 0 }}>⏱</span>
              <span
                dangerouslySetInnerHTML={{
                  __html: t('processing.durationWarn', { range: `<strong>${t('processing.durationRange')}</strong>` }),
                }}
              />
            </div>
          )}
        </div>

        <div className="card">
          <div style={{ fontWeight: 700, fontSize: 16, marginBottom: 16 }}>{t('processing.stateTitle')}</div>
          <div className="slist">
            {model.steps.map((stepKey, i) => {
              const status = stepStatus(i);
              const bsMsg = backendSteps[i]?.message;
              return (
                <div key={i} className={`srow ${status === 'err' ? 'act' : status}`}>
                  <div className="sdot" style={status === 'err' ? { background: 'var(--badl)', borderColor: 'var(--bad)', color: 'var(--bad)' } : undefined}>
                    {status === 'done' ? '✓' :
                     status === 'act' ? <Spinner /> :
                     status === 'err' ? '✕' :
                     <span style={{ fontSize: 12.5, color: 'var(--t3)' }}>{i + 1}</span>}
                  </div>
                  <div className="sinfo">
                    <div className="sname">{t(`steps.${stepKey}.name`)}</div>
                    <div className="sdet" style={status === 'err' ? { color: 'var(--bad)' } : undefined}>
                      {status === 'done' ? t('processing.done') :
                       status === 'act' ? (bsMsg || t('processing.processing')) :
                       status === 'err' ? (bsMsg || jobError || 'error') :
                       t(`steps.${stepKey}.det`)}
                    </div>
                  </div>
                  {status === 'act' && (
                    <span className="s-badge">{t('processing.inProgress')}</span>
                  )}
                </div>
              );
            })}
          </div>

          {allDone && (
            <div className="ib" style={{ marginTop: 16 }}>
              <span>✅</span>
              <span>
                <strong>{t('processing.finishedBold')}</strong> {t('processing.finishedRest')}
              </span>
            </div>
          )}
          {hasError && (
            <div className="wb" style={{ marginTop: 16, color: 'var(--bad)', borderColor: 'oklch(.86 .09 25)', background: 'var(--badl)' }}>
              <span style={{ fontSize: 18, flexShrink: 0 }}>⚠</span>
              <span>{t('processing.jobError', { msg: jobError || 'unknown' })}</span>
            </div>
          )}
          {fetchError && !hasError && (
            <div className="ib" style={{ marginTop: 12, background: 'var(--warnl)', borderColor: 'oklch(.86 .09 75)', color: 'oklch(.40 .12 65)' }}>
              <span>⏳</span>
              <span>{t('processing.fetchError', { msg: fetchError })}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  );
};

export default ProcessingScreen;
