"""
config.py — Central configuration for the TBI App backend
All paths, parameters and system constants are defined here.

Current pipeline: 3D nnU-Net segmentation of TBI lesions.
OPTIONAL preprocessing before inference: ROBEX skull stripping + ANTs SyN
registration to the SRI24 atlas (frontend toggle `preprocess` — OFF by default).
"""

import os
import torch
from pathlib import Path

# ─── Base directories ────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent

MODELS_DIR = BASE_DIR / "models"
TMP_DIR    = BASE_DIR / "tmp"
TMP_DIR.mkdir(exist_ok=True)

# ─── ROBEX (optional skull stripping) ────────────────────────────────────────
ROBEX_DIR    = Path(os.environ.get("ROBEX_DIR", "/opt/ROBEX"))
ROBEX_SCRIPT = ROBEX_DIR / "runROBEX.sh"

# ─── Registration to the SRI24 atlas (ANTs SyN) ──────────────────────────────
# The TBI model was trained on T1s that went through ROBEX + nonlinear
# registration to SRI24 (antsRegistrationSyN.sh, default parameters). Raw T1s
# must go through the same two steps before inference.
ANTS_DIR          = Path(os.environ.get("ANTS_DIR", "/opt/ANTs/bin"))
ANTS_SYN_SCRIPT   = ANTS_DIR / "antsRegistrationSyN.sh"
ATLAS_PATH        = BASE_DIR / "app" / "atlas" / "SRI24_atlas.nii"

# ─── nnU-Net (segmentation of TBI lesions) ───────────────────────────────────
# Fine-tuned from Castaño Ledesma's TBI checkpoint on Dataset015_TCEC
# (3d_fullres, fold='all') with ADL v2 + ADS. Files expected in NNUNET_MODEL_DIR:
#   - checkpoint_final.pth  (~235 MB)
#   - plans.json
#   - dataset.json
#   - dataset_fingerprint.json  (OPTIONAL — only used for planning/training,
#     not read by initialize_from_trained_model_folder at inference time)
# nnUNet expects a specific folder structure when calling
# initialize_from_trained_model_folder — we build it at runtime with symlinks.
NNUNET_MODEL_DIR    = MODELS_DIR / "nnunet_ideas_fold_all"
NNUNET_DATASET_NAME = "Dataset015_TCEC"
NNUNET_TRAINER      = "nnUNetTrainer"
NNUNET_PLANS_NAME   = "nnUNetPlans"
NNUNET_CONFIG       = "3d_fullres"
NNUNET_FOLD         = "all"
NNUNET_CHECKPOINT   = "checkpoint_final.pth"

# Reported metrics — fine-tuned TBI model (ADL v2 + ADS, LR 1e-3,
# checkpoint_final) evaluated on the TCEC test set: 57 images with 230
# ground-truth lesions. A lesion counts as detected when IoU >= 0.1; a false
# positive is a predicted component that matches no ground-truth lesion.
# Size groups: small < 100 mm³, medium 100-1000 mm³, large > 1000 mm³.
NNUNET_METRICS = {
    "dsc_mean":        0.616,
    "iou_mean":        0.554,
    "det_small":       14 / 119,   # 14 of 119 small lesions detected
    "det_medium":      31 / 76,    # 31 of 76 medium lesions detected
    "det_large":       31 / 35,    # 31 of 35 large lesions detected
    "fp_proportion":   0.677,      # false positives / predicted lesions
    "fp_per_subject":  2.614,
}

# Size groups for the per-lesion list (same thresholds as the evaluation).
LESION_SMALL_MM3 = 100
LESION_LARGE_MM3 = 1000


# ─── API ─────────────────────────────────────────────────────────────────────
API_CONFIG = {
    "max_upload_mb":    500,
    "allowed_suffixes": [".nii", ".gz"],
    "job_timeout_sec":  900,
}

# ─── Hardware ────────────────────────────────────────────────────────────────
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# ─── Asset validation at startup ─────────────────────────────────────────────
def validate_assets() -> dict:
    checks = {
        "robex":              ROBEX_SCRIPT.exists(),
        "ants":               ANTS_SYN_SCRIPT.exists(),
        "atlas":              ATLAS_PATH.exists(),
        "nnunet_checkpoint":  (NNUNET_MODEL_DIR / NNUNET_CHECKPOINT).exists(),
        "nnunet_plans":       (NNUNET_MODEL_DIR / "plans.json").exists(),
        "nnunet_dataset":     (NNUNET_MODEL_DIR / "dataset.json").exists(),
    }
    # Informational only — nnUNet inference does not require this file.
    has_fingerprint = (NNUNET_MODEL_DIR / "dataset_fingerprint.json").exists()

    missing = [k for k, v in checks.items() if not v]
    if missing:
        print(f"[CONFIG] ADVERTENCIA — assets faltantes: {missing}")
    else:
        print(f"[CONFIG] Todos los assets verificados OK ({len(checks)} checks)")
    if not has_fingerprint:
        print("[CONFIG] dataset_fingerprint.json no presente (opcional, no bloquea inferencia)")
    return checks


if __name__ == "__main__":
    results = validate_assets()
    for asset, ok in results.items():
        print(f"  {'✓' if ok else '✗ FALTA'}  {asset}")
