"""
deepmriprep_pipeline.py — VBM pipeline with deepmriprep + CNN for inference

Replaces the old SPM12/DARTEL (discarded for cross-platform irreproducibility).
deepmriprep is a pure-Python toolkit based on PyTorch that performs:
  - Brain extraction (deepbet)
  - Tissue segmentation (3D UNet)
  - Spatial registration to MNI152 (sSYMNet)
  - Modulation (preserves volume with the jacobian)

Output: mwp1*.nii.gz — modulated gray matter map in MNI152 space
        (same format that SPM12 produced, but reproducible bit-for-bit
         across Linux/macOS/Windows because the whole chain is made of
         deterministic PyTorch models).

Flow (ModelType.DEEPMRIPREP frontend steps):
  1. Loading T1 image              ← routes.py
  2. (Optional) ROBEX skull strip  ← routes.py (use_robex toggle)
  3. VBM preprocessing             ← this module (deepmriprep)
  4. CNN classification            ← this module
"""

import torch
from pathlib import Path
from typing import Callable

from app.config import TMP_DIR
from app.api.schemas import AnalysisResult, ModelType, StepStatus
from app.classifiers.cnn_model import predict as cnn_predict, CNN_MODEL_METRICS
from app.preprocessing.nifti_utils import extract_volumetric_features


def run(brain_path: Path, job_id: str,
        update_step: Callable, metadata: dict) -> AnalysisResult:
    """
    deepmriprep + CNN pipeline.

    Args:
        brain_path:  T1 (raw or post-ROBEX depending on the use_robex toggle).
        job_id:      Job ID.
        update_step: callback(job_id, step_num, StepStatus, msg=None)
        metadata:    dict with test_name, patient_name, notes, use_robex.
    """
    brain_path = Path(brain_path)
    job_dir    = TMP_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # ── Step 3: deepmriprep — brain extraction + seg + MNI + modulation ──────
    update_step(job_id, 3, StepStatus.IN_PROGRESS,
                "Preprocesamiento VBM con deepmriprep (deepbet + UNet + sSYMNet)...")
    try:
        gm_map_path = _run_deepmriprep(brain_path, job_dir)
    except Exception as e:
        update_step(job_id, 3, StepStatus.ERROR, str(e))
        raise RuntimeError(f"deepmriprep falló: {e}") from e

    update_step(job_id, 3, StepStatus.COMPLETED,
                f"mapa GM: {gm_map_path.name}")

    # Volumetric features for the report (do not affect CNN prediction)
    try:
        vol_features = extract_volumetric_features(gm_map_path)
    except Exception:
        vol_features = {}

    # ── Step 4: CNN prediction ───────────────────────────────────────────────
    update_step(job_id, 4, StepStatus.IN_PROGRESS,
                "Clasificación CNN (MedicalNet ResNet-18 fold 3)...")
    try:
        cnn_result = cnn_predict(gm_map_path)
    except Exception as e:
        update_step(job_id, 4, StepStatus.ERROR, str(e))
        raise RuntimeError(f"Inferencia CNN falló: {e}") from e

    update_step(job_id, 4, StepStatus.COMPLETED,
                f"P(epilepsia)={cnn_result['prob_epilepsy']:.2f} "
                f"[umbral={cnn_result['threshold_used']}]")

    # ── Result ────────────────────────────────────────────────────────────────
    return AnalysisResult(
        prediction        = cnn_result["prediction"],
        confidence        = cnn_result["confidence"],
        prob_epilepsy     = cnn_result["prob_epilepsy"],
        prob_control      = cnn_result["prob_control"],
        # Fold 3 metrics (best fold, representative for the app)
        model_auc         = CNN_MODEL_METRICS["auc"],
        model_sensitivity = CNN_MODEL_METRICS["sensitivity"],
        model_specificity = CNN_MODEL_METRICS["specificity"],
        model_accuracy    = CNN_MODEL_METRICS["accuracy"],
        gm_volume_cm3     = vol_features.get("gm_volume_cm3"),
        gm_mean_density   = vol_features.get("gm_mean_density"),
        gm_voxels         = vol_features.get("gm_voxels"),
        model_used        = ModelType.DEEPMRIPREP,
        test_name         = metadata.get("test_name", ""),
        patient_name      = metadata.get("patient_name"),
        notes             = metadata.get("notes"),
    )


# ─── deepmriprep wrapper ─────────────────────────────────────────────────────

def _run_deepmriprep(t1_path: Path, job_dir: Path) -> Path:
    """
    Runs the deepmriprep pipeline with outputs='vbm' (produces mwp1*.nii.gz).
    Auto-detects GPU via torch.cuda.is_available().

    Returns:
        Path to the generated mwp1*.nii.gz file.
    """
    # Lazy import — deepmriprep is heavy (loads models on import)
    from deepmriprep import run_preprocess

    out_dir = job_dir / "deepmriprep_out"
    out_dir.mkdir(parents=True, exist_ok=True)

    no_gpu = not torch.cuda.is_available()
    print(f"[deepmriprep] Iniciando: {t1_path.name} (GPU={'sí' if not no_gpu else 'no'})")

    run_preprocess(
        input_paths      = [str(t1_path)],
        output_dir       = str(out_dir),
        outputs          = 'vbm',
        dir_format       = 'sub',         # create one subfolder per subject
        no_gpu           = no_gpu,
        skip_broken      = True,
        skip_unprocessed = True,
    )

    # Look for mwp1*.nii.gz recursively (compat with dir_format='sub'/'flat')
    candidates = list(out_dir.rglob('mwp1*.nii.gz'))
    if not candidates:
        # Fallback: mwp1 without .gz (some deepmriprep versions)
        candidates = list(out_dir.rglob('mwp1*.nii'))
    if not candidates:
        raise RuntimeError(
            f"deepmriprep terminó pero no se encontró mwp1*.nii(.gz) en {out_dir}.\n"
            f"Archivos generados: {[p.name for p in out_dir.rglob('*.nii*')]}"
        )

    return candidates[0]
