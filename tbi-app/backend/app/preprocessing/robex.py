"""
robex.py — Skull stripping with ROBEX (first half of the preprocessing step)

DESIGN DECISION:
  The TBI model was trained on T1s preprocessed in two stages: ROBEX skull
  stripping, then ANTs SyN registration to the SRI24 atlas
  (app/preprocessing/registration.py). Raw T1s (skull, scalp, neck, any
  orientation) must go through both before nnU-Net.

  The frontend `preprocess` toggle runs ROBEX + registration together. It is
  OFF by default for T1s that are already skull-stripped and registered to
  SRI24 (e.g. the TCEC test set): those go straight to nnU-Net.

  When preprocessing is requested, a ROBEX failure raises instead of falling
  back to the raw T1 — a T1 with skull would not match training.
"""

import time
from pathlib import Path

from app.config import ROBEX_DIR, ROBEX_SCRIPT, TMP_DIR


def skull_strip(t1_path: Path, job_id: str,
                skip_robex: bool = True) -> Path:
    """
    Skull-stripping step of the pipeline.

    By default skip_robex=True: returns the original T1 unmodified (input
    already preprocessed).

    Args:
        t1_path:    Path to the input .nii (already decompressed).
        job_id:     Job ID (for logging).
        skip_robex: If True (default), returns t1_path unmodified.

    Returns:
        Path to the skull-stripped T1 (or the input T1 if skipped).

    Raises:
        RuntimeError: if ROBEX is requested but missing or fails.
    """
    t1_path = Path(t1_path)

    if skip_robex:
        print(f"[ROBEX] Paso omitido — T1 ya preprocesada pasa directamente a nnUNet")
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
        raise RuntimeError(f"ROBEX no encontrado en {ROBEX_SCRIPT}")

    cmd = [
        str(ROBEX_SCRIPT),
        str(t1_path),
        str(stripped_path),
        str(mask_path),
    ]

    print(f"[ROBEX] Ejecutando skull stripping: {t1_path.name}")
    t_start = time.time()

    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=600,
        cwd=str(ROBEX_DIR),
    )
    elapsed = round(time.time() - t_start, 1)

    if result.returncode != 0 or not stripped_path.exists():
        tail = (result.stderr or result.stdout or "")[-1500:]
        raise RuntimeError(f"ROBEX falló (código {result.returncode}): {tail}")

    print(f"[ROBEX] Completado en {elapsed}s")
    return stripped_path
