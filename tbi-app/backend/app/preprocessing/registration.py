"""
registration.py — Nonlinear registration to the SRI24 atlas with ANTs SyN

The TBI training images were skull-stripped with ROBEX and then registered
to SRI24 with antsRegistrationSyN.sh using its default transform
(rigid + affine + SyN). This module replicates that call, so a raw T1 that
went through ROBEX ends up in the same space the model was trained on
(240×240×155 at 1 mm, RAS).

The mask predicted by nnU-Net stays in atlas space, so the viewer shows it
over the registered T1 returned here.
"""

import os
import subprocess
import time
from pathlib import Path

from app.config import ANTS_DIR, ANTS_SYN_SCRIPT, ATLAS_PATH, TMP_DIR


def register_to_atlas(brain_path: Path, job_id: str) -> Path:
    """
    Register a skull-stripped T1 to SRI24 and return the warped image.

    Same command as the training pipeline:
        antsRegistrationSyN.sh -d 3 -f <atlas> -m <brain> -o <prefix>
    Only `-n` (threads) is added, to use every CPU core.

    Raises:
        RuntimeError: if ANTs or the atlas are missing, or the registration fails.
            There is no fallback: an unregistered T1 would not match training.
    """
    brain_path = Path(brain_path)
    if not ANTS_SYN_SCRIPT.exists():
        raise RuntimeError(f"ANTs no encontrado en {ANTS_SYN_SCRIPT}")
    if not ATLAS_PATH.exists():
        raise RuntimeError(f"Atlas SRI24 no encontrado en {ATLAS_PATH}")

    job_dir = TMP_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)
    prefix  = job_dir / f"{job_id}_sri24_"
    warped  = Path(f"{prefix}Warped.nii.gz")

    if warped.exists():
        return warped

    cmd = [
        str(ANTS_SYN_SCRIPT),
        "-d", "3",
        "-f", str(ATLAS_PATH),
        "-m", str(brain_path),
        "-o", str(prefix),
        "-n", str(os.cpu_count() or 1),
    ]
    env = {**os.environ, "ANTSPATH": f"{ANTS_DIR}/"}

    print(f"[ANTs] Registro SyN a SRI24: {brain_path.name}")
    t_start = time.time()
    result = subprocess.run(cmd, capture_output=True, text=True, env=env)

    if result.returncode != 0 or not warped.exists():
        tail = (result.stderr or result.stdout or "")[-1500:]
        raise RuntimeError(f"El registro ANTs a SRI24 falló (código {result.returncode}): {tail}")

    print(f"[ANTs] Registro completado en {time.time() - t_start:.1f}s → {warped.name}")
    return warped
