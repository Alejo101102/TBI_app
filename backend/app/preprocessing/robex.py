"""
robex.py — Skull stripping with ROBEX (OPTIONAL step)

CRITICAL DESIGN DECISION:
  The training pipeline (run_vbm_spm12_checkpoint.m on the iMac) passed the
  T1 DIRECTLY to SPM12 Unified Segmentation without prior skull stripping.
  SPM12 performs its own brain extraction internally.

  Adding ROBEX before SPM12 at inference time produces GM maps that differ
  from the training ones (~28,000 extra voxels for sub-102), which degrades
  the CNN predictions.

  THEREFORE: skull_strip() returns the raw T1 by default (skip_robex=True).
  ROBEX would only be used if the model were retrained in the future with
  ROBEX as an explicit prior step.

  The function is kept implemented so we don't break the backend or frontend
  architecture (which displays "Extracción de cráneo · ROBEX" as a step).
  In the UI that step completes instantly with the correct message.
"""

import time
from pathlib import Path

from app.config import ROBEX_DIR, ROBEX_SCRIPT, TMP_DIR


def skull_strip(t1_path: Path, job_id: str,
                skip_robex: bool = True) -> Path:
    """
    Skull-stripping step of the pipeline.

    By default skip_robex=True: returns the original T1 unmodified.
    This exactly replicates the training pipeline (SPM12 direct).

    Args:
        t1_path:    Path to the input .nii (already decompressed).
        job_id:     Job ID (for logging).
        skip_robex: If True (default), returns t1_path unmodified.
                    SPM12 Unified Segmentation performs its own brain
                    extraction internally — no prior ROBEX is required.

    Returns:
        Path to the image that will enter SPM12 (raw or stripped).
    """
    t1_path = Path(t1_path)

    if skip_robex:
        print(f"[ROBEX] Paso omitido — T1 pasa directamente a SPM12 "
              f"(replica pipeline de entrenamiento)")
        return t1_path

    # ── Active skull stripping (only if skip_robex=False) ─────────────────────
    import subprocess

    job_dir       = TMP_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    stripped_path = job_dir / f"{job_id}_brain.nii"
    mask_path     = job_dir / f"{job_id}_brain_mask.nii"

    if stripped_path.exists():
        return stripped_path

    if not ROBEX_SCRIPT.exists():
        print(f"[ROBEX] Binario no encontrado en {ROBEX_SCRIPT} — usando T1 cruda")
        return t1_path

    cmd = [
        str(ROBEX_SCRIPT),
        str(t1_path),
        str(stripped_path),
        str(mask_path),
    ]

    print(f"[ROBEX] Ejecutando skull stripping: {t1_path.name}")
    t_start = time.time()

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(ROBEX_DIR),
        )
        elapsed = round(time.time() - t_start, 1)

        if result.returncode != 0 or not stripped_path.exists():
            print(f"[ROBEX] Falló (código {result.returncode}) — usando T1 cruda")
            return t1_path

        print(f"[ROBEX] Completado en {elapsed}s")
        return stripped_path

    except Exception as e:
        print(f"[ROBEX] Error: {e} — usando T1 cruda")
        return t1_path
