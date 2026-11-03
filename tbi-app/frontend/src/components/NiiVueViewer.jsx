import { useCallback, useEffect, useRef, useState } from 'react';
import * as nifti from 'nifti-reader-js';
import pako from 'pako';
import { useT } from '../i18n/LanguageContext.jsx';
import { postViewerMetrics } from '../api/client.js';

// ─── 2D NIfTI viewer (axial / coronal / sagittal) ───────────────────────────
//
// Replacement for NiiVue: we use nifti-reader-js + canvas2d for full control
// over the render — no WebGL, no 3D library overhead, exactly the 3
// anatomical views with a red overlay of the binary mask.
//
// Works in spatial RAS (x=L→R, y=P→A, z=I→S). Assumes images are in standard
// orientation (raw T1 without reorientation + nnUNet mask in the same space,
// which is what the pipeline produces).
//
// Axial and coronal views use the RADIOLOGICAL convention, like Mango and most
// clinical viewers: the patient's right is drawn on the left of the screen
// (R/L labels on the canvas edges). The X axis is mirrored only when drawing;
// the volumes, crop and mask stay untouched.
//
// Performance is MEASURED, not estimated: every phase below is timed with
// performance.now() and POSTed to /viewer-metrics/{job_id}, which prints it to
// `docker logs samil_backend`. See flushRenderMetrics() at the bottom. The
// instrumentation is read-only — it does not throttle, cache or reorder any of
// the render work, so the numbers describe this exact implementation.

// `mirror`: draw the X axis right→left (radiological convention).
const VIEWS = [
  { key: 'axial',    axis: 2, mirror: true  },   // slices on the Z axis (I-S)
  { key: 'coronal',  axis: 1, mirror: true  },   // slices on the Y axis (P-A)
  { key: 'sagittal', axis: 0, mirror: false },   // slices on the X axis (L-R)
];

// Wait this long after the last slider tick before shipping the render stats.
// Long enough that one drag of the slider becomes a single log block.
const FLUSH_DEBOUNCE_MS = 2500;

const r2 = (x) => Math.round(x * 100) / 100;

/**
 * Download + decompress + parse a .nii.gz → { header, data, dims, timings }
 *
 * `timings` splits the one-off load cost into its three real phases (network,
 * gzip inflate, NIfTI parse) because they scale differently: inflate is pure
 * CPU and dominates on a slow machine, download dominates on a slow link.
 */
async function fetchVolume(url) {
  const tFetch0 = performance.now();
  const res = await fetch(url);
  if (!res.ok) throw new Error(`HTTP ${res.status} fetching ${url}`);
  const buf = await res.arrayBuffer();
  const tFetch1 = performance.now();

  // .nii.gz → decompress; .nii → use directly
  let raw;
  const wasCompressed = nifti.isCompressed(buf);
  if (wasCompressed) {
    raw = pako.inflate(new Uint8Array(buf)).buffer;
  } else {
    raw = buf;
  }
  const tInflate1 = performance.now();

  if (!nifti.isNIFTI(raw)) {
    throw new Error('Archivo no es NIfTI válido');
  }
  const header = nifti.readHeader(raw);
  const image  = nifti.readImage(header, raw);

  // Type the array according to datatypeCode
  const data = toTypedArray(image, header.datatypeCode);
  const dims = [header.dims[1], header.dims[2], header.dims[3]];
  const tParse1 = performance.now();

  return {
    header,
    data,
    dims,
    timings: {
      downloadMs: tFetch1 - tFetch0,
      inflateMs:  tInflate1 - tFetch1,
      parseMs:    tParse1 - tInflate1,
      bytes:      buf.byteLength,   // size on the wire (still compressed)
      wasCompressed,
    },
  };
}

function toTypedArray(buffer, code) {
  switch (code) {
    case nifti.NIFTI1.TYPE_UINT8:   return new Uint8Array(buffer);
    case nifti.NIFTI1.TYPE_INT16:   return new Int16Array(buffer);
    case nifti.NIFTI1.TYPE_INT32:   return new Int32Array(buffer);
    case nifti.NIFTI1.TYPE_FLOAT32: return new Float32Array(buffer);
    case nifti.NIFTI1.TYPE_FLOAT64: return new Float64Array(buffer);
    case nifti.NIFTI1.TYPE_INT8:    return new Int8Array(buffer);
    case nifti.NIFTI1.TYPE_UINT16:  return new Uint16Array(buffer);
    case nifti.NIFTI1.TYPE_UINT32:  return new Uint32Array(buffer);
    default: return new Float32Array(buffer);
  }
}

/** Human-readable datatype, so the logged timings state what they measured. */
function datatypeName(code) {
  switch (code) {
    case nifti.NIFTI1.TYPE_UINT8:   return 'uint8';
    case nifti.NIFTI1.TYPE_INT16:   return 'int16';
    case nifti.NIFTI1.TYPE_INT32:   return 'int32';
    case nifti.NIFTI1.TYPE_FLOAT32: return 'float32';
    case nifti.NIFTI1.TYPE_FLOAT64: return 'float64';
    case nifti.NIFTI1.TYPE_INT8:    return 'int8';
    case nifti.NIFTI1.TYPE_UINT16:  return 'uint16';
    case nifti.NIFTI1.TYPE_UINT32:  return 'uint32';
    default: return `code ${code}`;
  }
}

/** Extract a 2D slice from a 3D volume along the given axis. Returns {w, h, pixels}. */
function sliceVolume(volume, axis, sliceIdx) {
  const [nx, ny, nz] = volume.dims;
  const data = volume.data;
  let w, h, out;

  if (axis === 2) {           // AXIAL (fixed Z) → XY plane
    w = nx; h = ny;
    out = new Float32Array(w * h);
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        out[y * w + x] = data[sliceIdx * nx * ny + y * nx + x];
      }
    }
  } else if (axis === 1) {    // CORONAL (fixed Y) → XZ plane
    w = nx; h = nz;
    out = new Float32Array(w * h);
    for (let z = 0; z < h; z++) {
      for (let x = 0; x < w; x++) {
        out[z * w + x] = data[z * nx * ny + sliceIdx * nx + x];
      }
    }
  } else {                    // SAGITTAL (fixed X) → YZ plane
    w = ny; h = nz;
    out = new Float32Array(w * h);
    for (let z = 0; z < h; z++) {
      for (let y = 0; y < w; y++) {
        out[z * w + y] = data[z * nx * ny + y * nx + sliceIdx];
      }
    }
  }
  return { w, h, pixels: out };
}

/**
 * Compute the brain's 3D bounding box in the full volume (min/max indices
 * where intensity > threshold). It is computed ONCE per volume and reused
 * on every render — no per-slice cost.
 *
 * Returns [[xMin, xMax], [yMin, yMax], [zMin, zMax]] with a 4-voxel margin.
 */
function computeBoundingBox(volume) {
  const [nx, ny, nz] = volume.dims;
  const data = volume.data;
  // Robust threshold: 5% of the 99th percentile (filters background noise)
  const sample = new Float32Array(Math.min(30000, data.length));
  for (let i = 0; i < sample.length; i++) sample[i] = data[(Math.random() * data.length) | 0];
  sample.sort();
  const p99 = sample[(sample.length * 0.99) | 0];
  const thr = p99 * 0.05;

  let xMin = nx, xMax = 0, yMin = ny, yMax = 0, zMin = nz, zMax = 0;
  for (let z = 0; z < nz; z++) {
    for (let y = 0; y < ny; y++) {
      for (let x = 0; x < nx; x++) {
        if (data[z * nx * ny + y * nx + x] > thr) {
          if (x < xMin) xMin = x; if (x > xMax) xMax = x;
          if (y < yMin) yMin = y; if (y > yMax) yMax = y;
          if (z < zMin) zMin = z; if (z > zMax) zMax = z;
        }
      }
    }
  }
  const margin = 4;
  return [
    [Math.max(0, xMin - margin), Math.min(nx - 1, xMax + margin)],
    [Math.max(0, yMin - margin), Math.min(ny - 1, yMax + margin)],
    [Math.max(0, zMin - margin), Math.min(nz - 1, zMax + margin)],
  ];
}

/** Crop a 2D slice to a rectangular region [[xMin,xMax],[yMin,yMax]] */
function cropSlice(slice, bbox) {
  const { w, h, pixels } = slice;
  const [[x0, x1], [y0, y1]] = bbox;
  const cw = x1 - x0 + 1;
  const ch = y1 - y0 + 1;
  const out = new Float32Array(cw * ch);
  for (let y = 0; y < ch; y++) {
    for (let x = 0; x < cw; x++) {
      out[y * cw + x] = pixels[(y + y0) * w + (x + x0)];
    }
  }
  return { w: cw, h: ch, pixels: out };
}

/** 2D bounding box corresponding to a given view (axis ∈ {0,1,2}). */
function sliceBboxFor(axis, bbox3d) {
  const [[x0, x1], [y0, y1], [z0, z1]] = bbox3d;
  if (axis === 2) return [[x0, x1], [y0, y1]];   // axial: XY
  if (axis === 1) return [[x0, x1], [z0, z1]];   // coronal: XZ
  return [[y0, y1], [z0, z1]];                    // sagittal: YZ
}

/**
 * Draw T1 in grayscale + red mask onto a canvas. With `mirror`, column x of
 * the canvas shows column (w-1-x) of the slice (radiological convention).
 */
function renderSlice(canvas, t1Slice, maskSlice, showMask, opacity, t1Min, t1Max, mirror) {
  const { w, h, pixels: t1 } = t1Slice;
  canvas.width  = w;
  canvas.height = h;

  const ctx     = canvas.getContext('2d');
  const imgData = ctx.createImageData(w, h);
  const range   = (t1Max - t1Min) || 1;

  for (let p = 0; p < t1.length; p++) {
    // p = canvas pixel, i = source voxel of the slice
    const i = mirror ? p - (p % w) + (w - 1 - (p % w)) : p;
    // Normalize T1 to 0-255
    let v = (t1[i] - t1Min) / range;
    v = Math.max(0, Math.min(1, v));
    let r = (v * 255) | 0;
    let g = r, b = r;

    // Red overlay of the mask (alpha-blending)
    if (showMask && maskSlice) {
      const m = maskSlice.pixels[i];
      if (m > 0) {
        // Blend: pixel = (1-α)·gray + α·red
        r = (r * (1 - opacity) + 255 * opacity) | 0;
        g = (g * (1 - opacity)) | 0;
        b = (b * (1 - opacity)) | 0;
      }
    }

    const j = p * 4;
    imgData.data[j]     = r;
    imgData.data[j + 1] = g;
    imgData.data[j + 2] = b;
    imgData.data[j + 3] = 255;
  }
  ctx.putImageData(imgData, 0, 0);
}

/** min/max stats ignoring outliers (1st-99th percentile for better contrast) */
function computeIntensityRange(data) {
  // Sampling: 50k random voxels are enough for stable percentiles
  const n = data.length;
  const sample = new Float32Array(Math.min(50000, n));
  for (let i = 0; i < sample.length; i++) {
    sample[i] = data[(Math.random() * n) | 0];
  }
  sample.sort();
  const lo = sample[(sample.length * 0.01) | 0];
  const hi = sample[(sample.length * 0.99) | 0];
  return [lo, hi];
}

// ─── Telemetry helpers ──────────────────────────────────────────────────────

/**
 * Aggregate a set of millisecond samples. Returns null for an empty set so the
 * backend schema can leave the field out.
 *
 * Percentiles are nearest-rank on the sorted array — no interpolation, which is
 * what you want when reporting "the slowest 5% of frames took at least this".
 */
function summarize(values) {
  if (!values || values.length === 0) return null;
  const s = [...values].sort((a, b) => a - b);
  const q = (p) => s[Math.min(s.length - 1, Math.floor(s.length * p))];
  const mean = s.reduce((a, b) => a + b, 0) / s.length;
  return {
    n:       s.length,
    min_ms:  r2(s[0]),
    p50_ms:  r2(q(0.5)),
    p95_ms:  r2(q(0.95)),
    max_ms:  r2(s[s.length - 1]),
    mean_ms: r2(mean),
  };
}

/** Shape of a loaded volume — gives the reported timings their units. */
function volumeInfo(vol) {
  const [nx, ny, nz] = vol.dims;
  const pd = vol.header.pixDims;
  return {
    dims:   [nx, ny, nz],
    voxels: nx * ny * nz,
    // pixDims[1..3] is the voxel size in mm — this is what documents whether
    // the measured volume really was 1 mm isometric.
    voxel_size_mm: pd ? [r2(pd[1]), r2(pd[2]), r2(pd[3])] : null,
    datatype: datatypeName(vol.header.datatypeCode),
  };
}

/**
 * Client hardware. The whole point of the measurement is comparing a machine
 * with a dedicated GPU against one without, so every report carries this.
 * deviceMemory is Chromium-only; null elsewhere.
 */
function clientInfo() {
  return {
    cores:            navigator.hardwareConcurrency ?? null,
    device_memory_gb: navigator.deviceMemory ?? null,
    dpr:              window.devicePixelRatio ?? null,
    user_agent:       navigator.userAgent,
  };
}

const NiiVueViewer = ({ t1Url, maskUrl, jobId, onError }) => {
  const t = useT();
  const canvasRef = useRef(null);
  const t1Ref     = useRef(null);
  const maskRef   = useRef(null);
  const rangeRef  = useRef([0, 1]);
  const bboxRef   = useRef(null);   // brain 3D bounding box (in voxels)

  // ── Telemetry state (refs only — must never trigger a re-render) ──────────
  const samplesRef    = useRef([]);      // [{view, slice, crop, draw, total, toPaint}]
  const loadStatsRef  = useRef(null);    // load report, held until the 1st frame
  const loadSentRef   = useRef(false);   // the load report is sent exactly once
  const flushTimerRef = useRef(null);
  const sentCountRef  = useRef(0);       // samples already reported, avoids re-sends
  // Bumped on every visibilitychange. requestAnimationFrame is PAUSED while the
  // tab is hidden, so a paint measurement spanning a visibility change times how
  // long the user was away, not the compositor — those samples get dropped.
  const visEpochRef   = useRef(0);

  const [viewKey,     setViewKey]     = useState('axial');
  const [sliceIdx,    setSliceIdx]    = useState(0);
  const [maxSlice,    setMaxSlice]    = useState(0);
  const [showOverlay, setShowOverlay] = useState(true);
  const [opacity,     setOpacity]     = useState(0.5);
  const [loading,     setLoading]     = useState(true);
  const [errorMsg,    setErrorMsg]    = useState(null);

  /**
   * Ship the render stats accumulated so far. Every flush reports the FULL set
   * of samples since load, not just the new ones, so the last block in the log
   * for a given job is already the complete session summary — no adding up
   * lines by hand.
   */
  const flushRenderMetrics = useCallback(() => {
    if (flushTimerRef.current) {
      clearTimeout(flushTimerRef.current);
      flushTimerRef.current = null;
    }
    const all = samplesRef.current;
    if (!jobId || all.length === 0 || all.length === sentCountRef.current) return;
    sentCountRef.current = all.length;

    // toPaint is filled in asynchronously by a rAF, so the newest samples may
    // not have it yet — filter rather than report a null as a zero.
    const pick = (key) => all.map((s) => s[key]).filter((v) => typeof v === 'number');

    // Per-view split: axial walks contiguous memory, coronal/sagittal walk it
    // strided, so their cache behaviour (and timing) genuinely differs.
    const perView = {};
    for (const v of VIEWS) {
      const stats = summarize(all.filter((s) => s.view === v.key).map((s) => s.total));
      if (stats) perView[v.key] = stats;
    }

    postViewerMetrics(jobId, {
      phase:    'render',
      total:    summarize(pick('total')),
      slice:    summarize(pick('slice')),
      crop:     summarize(pick('crop')),
      draw:     summarize(pick('draw')),
      to_paint: summarize(pick('toPaint')),
      per_view: perView,
      // Raw per-frame totals for offline stats. Capped to match the backend's
      // max_length=2000; keep the most recent ones.
      samples:  all.slice(-2000).map((s) => r2(s.total)),
      client:   clientInfo(),
    });
  }, [jobId]);

  // Flush on unmount ("New analysis" / "Back") and on pagehide (tab closed).
  // Declared after the render effect's deps but registered once, so the
  // debounce timer can never be orphaned with unsent samples.
  useEffect(() => {
    const onHide = () => flushRenderMetrics();
    const onVisChange = () => { visEpochRef.current += 1; };
    window.addEventListener('pagehide', onHide);
    document.addEventListener('visibilitychange', onVisChange);
    return () => {
      window.removeEventListener('pagehide', onHide);
      document.removeEventListener('visibilitychange', onVisChange);
      flushRenderMetrics();
    };
  }, [flushRenderMetrics]);

  // ── Initial load of both volumes in parallel ──────────────────────────
  useEffect(() => {
    let cancelled = false;
    // Clock starts at mount: "time to first frame" is what the user perceives
    // as the viewer opening.
    const startedAt = performance.now();
    samplesRef.current   = [];
    sentCountRef.current = 0;
    loadSentRef.current  = false;
    loadStatsRef.current = null;

    (async () => {
      try {
        setLoading(true);
        setErrorMsg(null);
        const [t1Vol, maskVol] = await Promise.all([
          fetchVolume(t1Url),
          fetchVolume(maskUrl).catch((e) => {
            console.warn('[Viewer] máscara no cargada:', e);
            return null;
          }),
        ]);
        if (cancelled) return;

        t1Ref.current   = t1Vol;
        maskRef.current = maskVol;

        const tRange0 = performance.now();
        rangeRef.current = computeIntensityRange(t1Vol.data);
        const tRange1 = performance.now();
        bboxRef.current  = computeBoundingBox(t1Vol);
        const tBbox1 = performance.now();

        // Held here and sent from the render effect, so to_first_frame_ms can
        // include the actual first paint.
        loadStatsRef.current = {
          startedAt,
          t1:   volumeInfo(t1Vol),
          mask: maskVol ? volumeInfo(maskVol) : null,
          load: {
            // NOTE: T1 and mask download concurrently via Promise.all, so
            // these two overlap — the wall clock is not their sum.
            t1_download_ms:   r2(t1Vol.timings.downloadMs),
            t1_inflate_ms:    r2(t1Vol.timings.inflateMs),
            t1_parse_ms:      r2(t1Vol.timings.parseMs),
            t1_bytes:         t1Vol.timings.bytes,
            mask_download_ms: maskVol ? r2(maskVol.timings.downloadMs) : null,
            mask_inflate_ms:  maskVol ? r2(maskVol.timings.inflateMs)  : null,
            mask_parse_ms:    maskVol ? r2(maskVol.timings.parseMs)    : null,
            mask_bytes:       maskVol ? maskVol.timings.bytes          : null,
            range_ms:         r2(tRange1 - tRange0),
            bbox_ms:          r2(tBbox1 - tRange1),
          },
        };

        // Default to the central axial slice
        const axis = VIEWS.find((v) => v.key === viewKey).axis;
        const sliceCount = t1Vol.dims[axis];
        setMaxSlice(sliceCount - 1);
        setSliceIdx(Math.floor(sliceCount / 2));
        setLoading(false);
      } catch (err) {
        if (cancelled) return;
        console.error('[Viewer] Error:', err);
        setErrorMsg(err.message || String(err));
        setLoading(false);
        onError?.(err.message || String(err));
      }
    })();
    return () => { cancelled = true; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [t1Url, maskUrl]);

  // ── View change: reset slice to the center of the new axis ──────────
  useEffect(() => {
    if (!t1Ref.current) return;
    const axis = VIEWS.find((v) => v.key === viewKey).axis;
    const count = t1Ref.current.dims[axis];
    setMaxSlice(count - 1);
    setSliceIdx(Math.floor(count / 2));
  }, [viewKey]);

  // ── Reactive render whenever slice/overlay/opacity changes ──────────
  // This effect IS the hot path the jury is asking about: one run = one frame,
  // triggered by every slider tick, view switch, mask toggle and opacity change.
  useEffect(() => {
    if (!t1Ref.current || !canvasRef.current) return;
    const { axis, mirror } = VIEWS.find((v) => v.key === viewKey);

    const tSlice0 = performance.now();
    let t1Slice   = sliceVolume(t1Ref.current, axis, sliceIdx);
    let maskSlice = maskRef.current ? sliceVolume(maskRef.current, axis, sliceIdx) : null;
    const tSlice1 = performance.now();

    // Auto-crop to the brain bounding box — removes the empty FOV and the
    // image fills the whole canvas (≈ 2× larger visually).
    if (bboxRef.current) {
      const slice2dBbox = sliceBboxFor(axis, bboxRef.current);
      t1Slice = cropSlice(t1Slice, slice2dBbox);
      if (maskSlice) maskSlice = cropSlice(maskSlice, slice2dBbox);
    }
    const tCrop1 = performance.now();

    const [lo, hi]  = rangeRef.current;
    renderSlice(canvasRef.current, t1Slice, maskSlice, showOverlay, opacity, lo, hi, mirror);
    const tDraw1 = performance.now();

    const sample = {
      view:    viewKey,
      slice:   r2(tSlice1 - tSlice0),
      crop:    r2(tCrop1 - tSlice1),
      draw:    r2(tDraw1 - tCrop1),
      total:   r2(tDraw1 - tSlice0),   // the JS work of one frame
      toPaint: null,                   // filled below, after the compositor
    };
    samplesRef.current.push(sample);

    // First frame done → the load report is complete. Sent SYNCHRONOUSLY on
    // purpose: sending it from the rAF below made it hostage to rAF throttling,
    // which stops entirely while the tab is hidden. Tabbing away to read the
    // logs inflated to_first_frame_ms to ~29 s on a ~1.8 s load.
    if (!loadSentRef.current && loadStatsRef.current && jobId) {
      loadSentRef.current = true;
      const ls = loadStatsRef.current;
      postViewerMetrics(jobId, {
        phase: 'load',
        t1:    ls.t1,
        mask:  ls.mask,
        // mount → first slice fully rasterized. Excludes the compositor blit,
        // which `to_paint` covers per frame.
        load:  { ...ls.load, to_first_frame_ms: r2(tDraw1 - ls.startedAt) },
        client: clientInfo(),
      });
    }

    // Observational rAF: fires on the next paint, so this captures the time
    // until pixels are actually on screen. It schedules nothing and throttles
    // nothing — the render above already ran synchronously.
    const visEpoch = visEpochRef.current;
    requestAnimationFrame(() => {
      // Drop the sample if the tab was hidden at any point between the render
      // and this callback: rAF is paused while hidden, so the elapsed time would
      // measure the user's absence instead of the compositor.
      if (visEpoch !== visEpochRef.current || document.hidden) return;
      sample.toPaint = r2(performance.now() - tSlice0);
    });

    // Debounce: one drag of the slider yields one log block, not 50.
    if (flushTimerRef.current) clearTimeout(flushTimerRef.current);
    flushTimerRef.current = setTimeout(flushRenderMetrics, FLUSH_DEBOUNCE_MS);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [viewKey, sliceIdx, showOverlay, opacity, loading]);

  return (
    <div className="niivue-wrap">
      <div className="niivue-toolbar">
        <label className="niivue-field">
          <span className="niivue-label">{t('viewer.view')}</span>
          <select
            value={viewKey}
            onChange={(e) => setViewKey(e.target.value)}
            className="niivue-select"
          >
            {VIEWS.map((v) => (
              <option key={v.key} value={v.key}>{t(`viewer.slice.${v.key}`)}</option>
            ))}
          </select>
        </label>

        <label className="niivue-field niivue-slider">
          <span className="niivue-label">{t('viewer.slice')}</span>
          <input
            type="range"
            min="0"
            max={maxSlice}
            value={sliceIdx}
            onChange={(e) => setSliceIdx(parseInt(e.target.value, 10))}
            disabled={loading || !!errorMsg}
          />
          <span className="niivue-value">{sliceIdx} / {maxSlice}</span>
        </label>

        <label className="niivue-field niivue-toggle">
          <input
            type="checkbox"
            checked={showOverlay}
            disabled={!maskRef.current}
            onChange={(e) => setShowOverlay(e.target.checked)}
          />
          <span>{t('viewer.showMask')}</span>
        </label>

        <label className="niivue-field niivue-slider">
          <span className="niivue-label">{t('viewer.opacity')}</span>
          <input
            type="range"
            min="0" max="1" step="0.05"
            value={opacity}
            disabled={!showOverlay || !maskRef.current}
            onChange={(e) => setOpacity(parseFloat(e.target.value))}
          />
          <span className="niivue-value">{Math.round(opacity * 100)}%</span>
        </label>
      </div>

      <div className="niivue-canvas-wrap">
        {loading && <div className="niivue-loading">{t('viewer.loading')}</div>}
        {errorMsg && (
          <div className="niivue-loading" style={{ color: '#f87171' }}>
            ⚠ {errorMsg}
          </div>
        )}
        <canvas ref={canvasRef} className="niivue-canvas" />
        {!loading && !errorMsg && VIEWS.find((v) => v.key === viewKey).mirror && (
          <>
            <span className="niivue-orient niivue-orient-left">R</span>
            <span className="niivue-orient niivue-orient-right">L</span>
          </>
        )}
      </div>

      <div className="niivue-hint">{t('viewer.hint')}</div>
    </div>
  );
};

export default NiiVueViewer;
