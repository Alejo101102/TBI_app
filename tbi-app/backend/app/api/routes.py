"""
routes.py — TBI App API endpoints
POST /analyze  → uploads T1 + metadata, creates a job, returns job_id
GET  /status/{job_id} → polls the job status
GET  /report/{job_id} → downloads the .txt report
"""

import os
import uuid
import time
import asyncio
import traceback
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import FileResponse

from app.config import TMP_DIR, API_CONFIG, validate_assets

# Runtime flags (set via docker-compose.yml or `docker compose run -e`)
# KEEP_TMP_FILES=true → does not delete /app/tmp/<job_id>/ on completion,
#                        so we can inspect mwp1*.nii and .m batches.
#
# Note: SKIP_ROBEX was removed — preprocessing (ROBEX + SRI24 registration)
# is controlled per job by the frontend `preprocess` toggle (design decision
# documented in app/preprocessing/robex.py).
def _truthy(env_value: str) -> bool:
    return (env_value or "").lower() in ("1", "true", "yes", "on")

KEEP_TMP_FILES = _truthy(os.environ.get("KEEP_TMP_FILES"))
from app.api.schemas import (
    ModelType, JobCreatedResponse, JobStatusResponse,
    ProcessStep, StepStatus, AnalysisResult,
    ViewerMetrics, ViewerRenderStats,
)

router = APIRouter()

# Assets required by the optional preprocessing (ROBEX + SRI24 registration).
PREPROCESS_ASSETS = ("robex", "ants", "atlas")

# ─── Job store (memory + lightweight persistence on disk) ────────────────────
# Structure: { job_id: { "status": ..., "steps": [...], "result": ... } }
#
# Persistence: a snapshot of "job ID + status + final step" is saved to disk
# every time a step is updated. If the container dies and restarts, the
# /status endpoint can return "error" instead of 404 → the frontend shows a
# useful message ("the backend restarted mid-analysis") instead of the
# generic "Job not found".
import json as _json

JOBS: dict = {}
_PERSIST_FILE = TMP_DIR / "_jobs_snapshot.json"


def _persist_snapshot():
    """Save a serializable snapshot of the JOBS dict — silent on failure."""
    try:
        snapshot = {}
        for jid, j in JOBS.items():
            snapshot[jid] = {
                "status":   j.get("status"),
                "progress": j.get("progress", 0),
                "error":    j.get("error"),
            }
        _PERSIST_FILE.write_text(_json.dumps(snapshot), encoding="utf-8")
    except Exception:
        pass


def _load_snapshot_on_start():
    """
    At startup, read previous jobs from disk. Any job left as "running" or
    "pending" → mark it as "error" because the container restarted mid-job.
    The frontend will see it as a failure instead of a 404.
    """
    if not _PERSIST_FILE.exists():
        return
    try:
        prev = _json.loads(_PERSIST_FILE.read_text(encoding="utf-8"))
    except Exception:
        return
    for jid, snap in prev.items():
        status = snap.get("status")
        if status in ("running", "pending"):
            status = "error"
        JOBS[jid] = {
            "status":   status,
            "progress": snap.get("progress", 0),
            "steps":    [],
            "result":   None,
            "error":    snap.get("error") or (
                "El backend se reinició durante el análisis. "
                "Vuelve a lanzar el job."),
        }


# Load snapshot on module import (uvicorn imports it once per process).
_load_snapshot_on_start()


# ─── Helpers ─────────────────────────────────────────────────────────────────
def _steps_for_model(model: ModelType) -> list[ProcessStep]:
    """Return the list of steps for the selected model."""
    return [
        ProcessStep(step=1, name="Cargando imagen T1",       status=StepStatus.PENDING),
        ProcessStep(step=2, name="Preprocesamiento · ROBEX + registro SRI24", status=StepStatus.PENDING),
        ProcessStep(step=3, name="Segmentación nnUNet",       status=StepStatus.PENDING),
        ProcessStep(step=4, name="Análisis de máscara",       status=StepStatus.PENDING),
    ]


def _update_step(job_id: str, step_num: int, status: StepStatus, msg: str = None):
    """
    Update a single step's status. The overall progress percentage uses
    a weighted scheme so the bar moves smoothly even within a long step:
      - COMPLETED  → counts as 1.0
      - IN_PROGRESS → counts as 0.5 (half-credit, so the bar climbs as
                       soon as a step starts, instead of jumping only when
                       a step finishes — relevant for nnUNet inference
                       which takes 5-7 min as a single big step).
      - PENDING/ERROR → 0.0
    """
    for s in JOBS[job_id]["steps"]:
        if s.step == step_num:
            s.status  = status
            s.message = msg
            break

    weight_map = {
        StepStatus.COMPLETED:   1.0,
        StepStatus.IN_PROGRESS: 0.5,
    }
    total       = len(JOBS[job_id]["steps"])
    accumulated = sum(weight_map.get(s.status, 0.0) for s in JOBS[job_id]["steps"])
    JOBS[job_id]["progress"] = int((accumulated / total) * 100)
    _persist_snapshot()


def _update_substep(job_id: str, step_num: int, fraction: float, msg: str = None):
    """
    Optional finer-grained progress within a single step (0.0-1.0). Used by
    long-running pipelines (e.g. nnUNet inference) to nudge the global bar
    forward while a single step is still running.
    """
    fraction = max(0.0, min(1.0, fraction))
    weight_map = {StepStatus.COMPLETED: 1.0}
    total = len(JOBS[job_id]["steps"])
    accumulated = 0.0
    for s in JOBS[job_id]["steps"]:
        if s.step == step_num and s.status == StepStatus.IN_PROGRESS:
            accumulated += fraction
            if msg:
                s.message = msg
        else:
            accumulated += weight_map.get(s.status, 0.0)
    JOBS[job_id]["progress"] = int((accumulated / total) * 100)
    _persist_snapshot()


# ─── Main background task ────────────────────────────────────────────────────
async def _run_analysis(job_id: str, nii_path: Path, model: ModelType,
                        metadata: dict):
    """
    Runs the full pipeline in the background.
    Updates JOBS[job_id] on each step so polling can observe progress.
    """
    start = time.time()
    JOBS[job_id]["status"] = "running"

    try:
        # ── Step 1: Load image ─────────────────────────────────────────────
        _update_step(job_id, 1, StepStatus.IN_PROGRESS, "Validando archivo NIfTI")
        from app.preprocessing.nifti_utils import validate_and_load
        t1_path = validate_and_load(nii_path)
        _update_step(job_id, 1, StepStatus.COMPLETED)

        # ── Step 2: Optional preprocessing (controlled by `preprocess`) ────
        # Default (preprocess=False): the T1 is already skull-stripped and
        # registered to SRI24, so it goes directly to nnUNet.
        # If preprocess=True: raw T1 → ROBEX → ANTs SyN to SRI24, the same
        # two steps the training images went through.
        preprocess = bool(metadata.get("preprocess", False))
        if preprocess:
            from app.preprocessing.robex import skull_strip
            from app.preprocessing.registration import register_to_atlas
            _update_step(job_id, 2, StepStatus.IN_PROGRESS, "Aplicando ROBEX...")
            stripped_path = await asyncio.to_thread(skull_strip, t1_path, job_id, False)
            _update_substep(job_id, 2, 0.3, "Registrando a SRI24 (ANTs SyN)...")
            brain_path = await asyncio.to_thread(register_to_atlas, stripped_path, job_id)
            _update_step(job_id, 2, StepStatus.COMPLETED,
                         "ROBEX + registro SRI24 aplicados")
        else:
            brain_path = t1_path
            _update_step(job_id, 2, StepStatus.COMPLETED,
                         "T1 ya preprocesada pasa directamente a nnUNet")

        # ── Following steps depend on the selected model ───────────────────
        if model == ModelType.NNUNET:
            from app.pipelines.nnunet import run as run_nnunet
            result = await asyncio.to_thread(run_nnunet, brain_path, job_id,
                                             _update_step, metadata)

        else:
            raise ValueError(f"Modelo no soportado: {model}")

        # ── Final result ───────────────────────────────────────────────────
        result.processing_time_s = round(time.time() - start, 1)
        result.test_name         = metadata.get("test_name", "")
        result.patient_name      = metadata.get("patient_name")
        result.notes             = metadata.get("notes")
        result.preprocessed      = preprocess

        JOBS[job_id]["result"]   = result
        JOBS[job_id]["status"]   = "completed"
        JOBS[job_id]["progress"] = 100

        # Generate .txt report
        _generate_report(job_id, result)
        _persist_snapshot()

    except Exception as e:
        JOBS[job_id]["status"] = "error"
        JOBS[job_id]["error"]  = str(e)
        for s in JOBS[job_id]["steps"]:
            if s.status == StepStatus.IN_PROGRESS:
                s.status  = StepStatus.ERROR
                s.message = str(e)
        print(f"[JOB {job_id}] ERROR: {traceback.format_exc()}")
        _persist_snapshot()

    finally:
        # Clean up temporary job files (skippable with KEEP_TMP_FILES=true
        # so we can inspect mwp1*.nii, rc1*.nii, .m batches, etc.)
        if KEEP_TMP_FILES:
            print(f"[JOB {job_id}] KEEP_TMP_FILES=true — intermediarios en {TMP_DIR / job_id}")
        else:
            _cleanup(job_id)


def _pct(value):
    """Format as percentage or '—' if None."""
    return f"{value * 100:.1f}%" if value is not None else "—"


def _fmt_time(seconds):
    """Format seconds as 'Mm Ss' (e.g. '5m 23s') or '<1m Xs' if under a minute."""
    if seconds is None:
        return "—"
    s = int(round(seconds))
    m, s = divmod(s, 60)
    return f"{m}m {s:02d}s" if m else f"{s}s"


def _row(label: str, value: str, width: int = 24) -> str:
    """Pad label to width and append ': value' for consistent column alignment."""
    return f"  {label:<{width}}: {value}"


def _generate_report(job_id: str, result: AnalysisResult):
    """Generate a downloadable .txt report. Supports classification and segmentation."""
    report_path = TMP_DIR / f"{job_id}_report.txt"
    sep_eq = "=" * 60
    sep_dash = "-" * 60

    lines = [
        sep_eq,
        "  TBI App — Reporte de Análisis",
        sep_eq,
        _row("Prueba",     result.test_name),
        _row("Paciente",   result.patient_name or "No especificado"),
        _row("Modelo",     result.model_used.value),
        _row("Tiempo",     _fmt_time(result.processing_time_s)),
        _row("Preprocesamiento",
             "Sí (ROBEX + registro SRI24)" if result.preprocessed else "No (imagen ya en SRI24)"),
        sep_dash,
    ]

    # ── Verdict derived from the mask ─────────────────────────────────────
    if result.prediction is not None:
        lines += [
            "  RESULTADO (derivado de la segmentación)",
            _row("Predicción",
                 "LESIÓN DETECTADA" if result.prediction == "lesion" else "SIN HALLAZGOS"),
            sep_dash,
        ]

    # ── SEGMENTATION block (only if there is a mask) ──────────────────────
    if result.mask_filename is not None:
        fp_subj = (f"{result.model_fp_per_subject:.2f}"
                   if result.model_fp_per_subject is not None else "—")
        lines += [
            "  RESULTADO (segmentación nnU-Net 3D fullres)",
            _row("Vóxeles máscara",     f"{result.mask_voxels:,}" if result.mask_voxels is not None else "—"),
            _row("Volumen total",       f"{result.mask_volume_cm3:.2f} cm³"),
            _row("Clusters conexos",    str(result.n_clusters)),
            _row("Cluster más grande",  f"{result.largest_cluster_cm3:.2f} cm³"),
        ]
        cat_es = {"small": "pequeña", "medium": "mediana", "large": "grande"}
        for i, les in enumerate(result.lesions or [], start=1):
            x, y, z = les.centroid_vox
            lines.append(f"  #{i}  {les.volume_mm3:.1f} mm³ · {cat_es[les.category]} · "
                         f"cortes axiales {les.slice_min}–{les.slice_max} · "
                         f"centro ({x}, {y}, {z})")
        lines += [
            sep_dash,
            "  MÉTRICAS DEL MODELO (prueba TCEC · 57 imágenes, 230 lesiones)",
            _row("DSC",                     _pct(result.model_dsc)),
            _row("IoU",                     _pct(result.model_iou)),
            _row("Detección pequeñas",      _pct(result.model_det_small)),
            _row("Detección medianas",      _pct(result.model_det_medium)),
            _row("Detección grandes",       _pct(result.model_det_large)),
            _row("Proporción de FP",        _pct(result.model_fp_proportion)),
            _row("FP por sujeto",           fp_subj),
        ]

    if result.notes:
        lines += [sep_dash, "  NOTAS CLÍNICAS", f"  {result.notes}"]

    lines += [
        sep_eq,
        "  AVISO MÉDICO",
        "  Este análisis es herramienta de apoyo diagnóstico",
        "  y NO reemplaza el criterio clínico especializado.",
        sep_eq,
    ]
    report_path.write_text("\n".join(lines), encoding="utf-8")
    JOBS[job_id]["report_path"] = str(report_path)


def _cleanup(job_id: str):
    """
    Delete the job's temporary files.

    Exception: nnUNet jobs — we keep `t1.nii.gz` and `nnunet_out/<case>.nii.gz`
    because the frontend viewer consumes them after the job finishes
    (via /t1/{job_id} and /mask/{job_id}). We delete everything else (raw
    input, intermediates, _0000 duplicate).
    """
    job_tmp = TMP_DIR / job_id
    if not job_tmp.exists():
        return

    result = JOBS.get(job_id, {}).get("result")
    is_nnunet = result is not None and result.model_used == ModelType.NNUNET

    import shutil
    if not is_nnunet:
        try:
            shutil.rmtree(job_tmp)
        except Exception:
            pass
        return

    # nnUNet: delete everything except the served T1 and the generated mask.
    keep = {
        job_tmp / (result.t1_filename or ""),
        job_tmp / "nnunet_out" / (result.mask_filename or ""),
    }
    for path in job_tmp.rglob("*"):
        if path.is_dir():
            continue
        if path in keep:
            continue
        try:
            path.unlink()
        except Exception:
            pass
    # Remove empty folders (keep nnunet_out if it still holds the mask)
    for sub in sorted(job_tmp.rglob("*"), reverse=True):
        if sub.is_dir():
            try:
                sub.rmdir()
            except OSError:
                pass


# ─── ENDPOINTS ───────────────────────────────────────────────────────────────

@router.get("/assets")
def get_assets_status():
    """
    Report which model weights and optional tools are available on disk.
    The frontend uses this to disable model cards or the preprocessing toggle
    and to show a clear message ("contact the author to receive the weights").

    Returns a flat dict per model with a boolean and the list of missing
    files. nnUNet has 3 required files. Preprocessing needs the ROBEX binary,
    ANTs and the SRI24 atlas.
    """
    checks = validate_assets()
    nnunet_files = ["nnunet_checkpoint", "nnunet_plans", "nnunet_dataset"]
    nnunet_missing = [k for k in nnunet_files if not checks.get(k)]
    preprocess_missing = [k for k in PREPROCESS_ASSETS if not checks.get(k)]
    return {
        "nnunet": {
            "ready": len(nnunet_missing) == 0,
            "missing": nnunet_missing,
        },
        "preprocess": {
            "ready": len(preprocess_missing) == 0,
            "missing": preprocess_missing,
        },
    }


@router.post("/analyze", response_model=JobCreatedResponse)
async def analyze(
    background_tasks: BackgroundTasks,
    file:         UploadFile = File(...),
    test_name:    str        = Form(...),
    model:        ModelType  = Form(...),
    patient_name: str        = Form(""),
    notes:        str        = Form(""),
    preprocess:   bool       = Form(False),
):
    # Validate extension
    filename = file.filename or ""
    if not (filename.endswith(".nii") or filename.endswith(".nii.gz")):
        raise HTTPException(
            status_code=400,
            detail="Solo se aceptan archivos .nii o .nii.gz"
        )

    # Defense-in-depth asset checks. The frontend already disables cards/
    # toggles when an asset is missing, but we re-check here so a stale
    # cached UI or a direct API call cannot submit a job that will fail
    # mid-pipeline. Returns 503 with a clear message so the frontend can
    # display it to the user.
    assets = validate_assets()
    if model == ModelType.NNUNET and not all(assets.get(k) for k in
            ("nnunet_checkpoint", "nnunet_plans", "nnunet_dataset")):
        raise HTTPException(
            status_code=503,
            detail="Modelo nnUNet no disponible: faltan archivos del modelo en el servidor. "
                   "Solicítelos a alejandro.cano@correounivalle.edu.co",
        )
    preprocess_missing = [k for k in PREPROCESS_ASSETS if not assets.get(k)]
    if preprocess and preprocess_missing:
        raise HTTPException(
            status_code=503,
            detail=f"Preprocesamiento no disponible, faltan: {', '.join(preprocess_missing)}. "
                   "Desactive la opción o instale ROBEX (backend/vendor/), ANTs y el atlas "
                   "SRI24 (backend/app/atlas/) y reconstruya la imagen.",
        )

    # Validate size
    max_bytes = API_CONFIG["max_upload_mb"] * 1024 * 1024
    content   = await file.read()
    if len(content) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"Archivo demasiado grande (máx {API_CONFIG['max_upload_mb']} MB)"
        )

    # Save into tmp
    job_id  = str(uuid.uuid4())[:8]
    job_dir = TMP_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    nii_path = job_dir / filename
    nii_path.write_bytes(content)

    # Register job
    JOBS[job_id] = {
        "status":   "pending",
        "progress": 0,
        "steps":    _steps_for_model(model),
        "result":   None,
        "error":    None,
    }

    metadata = {
        "test_name":    test_name,
        "patient_name": patient_name or None,
        "notes":        notes or None,
        "preprocess":   preprocess,
    }

    background_tasks.add_task(_run_analysis, job_id, nii_path, model, metadata)

    return JobCreatedResponse(job_id=job_id)


@router.get("/status/{job_id}", response_model=JobStatusResponse)
def get_status(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    j = JOBS[job_id]
    return JobStatusResponse(
        job_id=job_id,
        status=j["status"],
        progress=j["progress"],
        steps=j["steps"],
        result=j.get("result"),
        error=j.get("error"),
    )


@router.get("/report/{job_id}")
def download_report(job_id: str):
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    report_path = JOBS[job_id].get("report_path")
    if not report_path or not Path(report_path).exists():
        raise HTTPException(status_code=404, detail="Reporte aún no disponible")
    return FileResponse(
        path=report_path,
        filename=f"tbi_reporte_{job_id}.txt",
        media_type="text/plain",
    )


# ─── Viewer endpoints (nnUNet) ───────────────────────────────────────────────
# The frontend (NiiVue) consumes these two files to render the T1 + the
# overlay of the segmented mask.

def _resolve_job_file(job_id: str, kind: str) -> Path:
    if job_id not in JOBS:
        raise HTTPException(status_code=404, detail="Job no encontrado")
    result = JOBS[job_id].get("result")
    if result is None:
        raise HTTPException(status_code=404, detail="Job sin resultado disponible")
    if result.model_used != ModelType.NNUNET:
        raise HTTPException(
            status_code=400,
            detail=f"El modelo {result.model_used.value} no genera archivos para el visor",
        )

    job_dir = TMP_DIR / job_id
    if kind == "t1":
        fname = result.t1_filename
        path  = job_dir / (fname or "")
    elif kind == "mask":
        fname = result.mask_filename
        path  = job_dir / "nnunet_out" / (fname or "")
    else:
        raise HTTPException(status_code=400, detail=f"Kind inválido: {kind}")

    if not fname or not path.exists():
        raise HTTPException(
            status_code=404,
            detail=f"Archivo {kind} no encontrado para el job {job_id}",
        )
    return path


@router.get("/t1/{job_id}")
def get_t1(job_id: str):
    """T1 served to the NiiVue viewer (after the nnUNet job)."""
    path = _resolve_job_file(job_id, "t1")
    return FileResponse(
        path=path,
        filename=f"t1_{job_id}.nii.gz",
        media_type="application/gzip",
    )


@router.get("/mask/{job_id}")
def get_mask(job_id: str):
    """Binary mask produced by nnUNet (overlay in the viewer)."""
    path = _resolve_job_file(job_id, "mask")
    return FileResponse(
        path=path,
        filename=f"mask_{job_id}.nii.gz",
        media_type="application/gzip",
    )


# ─── Anatomical viewer telemetry ─────────────────────────────────────────────
# The viewer renders on the CLIENT's CPU (canvas2d, no WebGL), so the container
# cannot time it — nginx only ever sees the HTTP requests. The browser measures
# with performance.now() and POSTs here; we just print it so the numbers show up
# in `docker logs tbi_backend` (the Dockerfile sets PYTHONUNBUFFERED=1).

def _ms(value) -> str:
    """Format milliseconds with one decimal, or '—' if the client omitted it."""
    return f"{value:.1f} ms" if value is not None else "—"


def _ms_size(ms, nbytes) -> str:
    """'412.3 ms (4.21 MB comprimidos)' — omits the size when unknown."""
    if nbytes:
        return f"{_ms(ms)} ({nbytes / (1024 * 1024):.2f} MB comprimidos)"
    return _ms(ms)


def _stats_line(s: ViewerRenderStats) -> str:
    """'min 14.2 · p50 18.6 · p95 27.1 · max 38.4 ms' — the shape of the range."""
    return (f"min {s.min_ms:.1f} · p50 {s.p50_ms:.1f} · "
            f"p95 {s.p95_ms:.1f} · max {s.max_ms:.1f} ms")


def _volume_line(v) -> str:
    if v is None:
        return "—"
    dims = "x".join(str(d) for d in v.dims)
    dtype = f" ({v.datatype})" if v.datatype else ""
    return f"{dims} = {v.voxels:,} vóxeles{dtype}"


def _log_viewer_metrics(job_id: str, m: ViewerMetrics):
    """Print one readable block per report. Mirrors _generate_report's style."""
    tag = job_id[:8]
    sep = "=" * 60
    lines = [sep]

    if m.phase == "load":
        lines.append(f"  [VIEWER {tag}] Visor anatómico — carga")
        lines.append(sep)
        lines.append(_row("Volumen T1", _volume_line(m.t1)))
        if m.t1 and m.t1.voxel_size_mm:
            vs = " x ".join(f"{p:.2f}" for p in m.t1.voxel_size_mm)
            lines.append(_row("Tamaño de vóxel", f"{vs} mm"))
        lines.append(_row("Máscara", _volume_line(m.mask)))

        ld = m.load
        if ld:
            lines += [
                _row("Descarga T1",      _ms_size(ld.t1_download_ms, ld.t1_bytes)),
                _row("Descompresión T1", _ms(ld.t1_inflate_ms)),
                _row("Parseo NIfTI T1",  _ms(ld.t1_parse_ms)),
            ]
            # Only when a mask actually loaded — the viewer degrades to T1-only.
            if m.mask is not None:
                lines += [
                    _row("Descarga máscara",    _ms_size(ld.mask_download_ms, ld.mask_bytes)),
                    _row("Descompresión másc.", _ms(ld.mask_inflate_ms)),
                    _row("Parseo máscara",      _ms(ld.mask_parse_ms)),
                ]
            lines += [
                _row("Bounding box (1 vez)",  _ms(ld.bbox_ms)),
                _row("Rango intens. (1 vez)", _ms(ld.range_ms)),
                _row("Total a 1er frame",     _ms(ld.to_first_frame_ms)),
                # The two downloads run concurrently (Promise.all in the viewer),
                # so reading them as sequential would overstate the load cost.
                _row("Nota", "descargas T1/máscara en paralelo (no sumar)"),
            ]

    else:  # phase == "render"
        n = m.total.n if m.total else 0
        lines.append(f"  [VIEWER {tag}] Visor anatómico — render por slice (n={n})")
        lines.append(sep)
        for view, s in (m.per_view or {}).items():
            lines.append(_row(f"{view} (n={s.n})", _stats_line(s)))
        if m.total:
            lines.append(_row(f"GLOBAL (n={m.total.n})", _stats_line(m.total)))
            # p50 breakdown: where the frame budget actually goes.
            parts = [(lbl, st) for lbl, st in
                     (("slice", m.slice_), ("crop", m.crop), ("draw", m.draw)) if st]
            if parts:
                lines.append(_row("Desglose p50",
                                  " · ".join(f"{lbl} {st.p50_ms:.1f}" for lbl, st in parts) + " ms"))
            if m.to_paint:
                lines.append(_row("Hasta pintado (p50)", _ms(m.to_paint.p50_ms)))
            # FPS the slider could sustain if the user dragged it continuously.
            fps50 = 1000.0 / m.total.p50_ms if m.total.p50_ms > 0 else 0
            fps95 = 1000.0 / m.total.p95_ms if m.total.p95_ms > 0 else 0
            lines.append(_row("FPS equivalente", f"~{fps50:.0f} a p50, ~{fps95:.0f} a p95"))

    if m.client:
        c = m.client
        hw = (f"{c.cores or '?'} núcleos, "
              f"{f'{c.device_memory_gb:g} GB' if c.device_memory_gb else 'RAM n/d'}, "
              f"DPR {c.dpr or '?'}")
        lines.append(_row("Hardware cliente", hw))
        if c.user_agent:
            lines.append(_row("User agent", c.user_agent[:120]))

    lines.append(sep)
    print("\n".join(lines))

    # Raw samples on one compact line — copy/paste into Excel or Python to
    # compute the range over several runs without trusting our aggregation.
    if m.samples:
        print(f"[VIEWER {tag} RAW] {_json.dumps([round(v, 2) for v in m.samples])}")


@router.post("/viewer-metrics/{job_id}", status_code=204)
def post_viewer_metrics(job_id: str, metrics: ViewerMetrics):
    """Log client-side viewer timings. Fire-and-forget: returns 204, no body.

    Deliberately does NOT check that the job exists — this is telemetry, and a
    404 here must never surface as an error in the viewer.
    """
    try:
        _log_viewer_metrics(job_id, metrics)
    except Exception:
        # A formatting bug in the log must not turn into a 500 for the client.
        print(f"[VIEWER {job_id[:8]}] ERROR al formatear métricas: {traceback.format_exc()}")
    return None