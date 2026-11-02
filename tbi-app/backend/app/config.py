"""
config.py — Central configuration for the SAMIL backend
All paths, parameters and system constants are defined here.

Current pipeline: 3D nnU-Net segmentation of epileptogenic zones.
ROBEX remains as OPTIONAL skull-stripping before inference
(frontend toggle `use_robex` — OFF by default).
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

# ─── nnU-Net (segmentation of epileptogenic zones) ───────────────────────────
# The model was trained on Colab with Dataset500_IDEAS_Epilepsy,
# nnUNetTrainer_250epochs, 3d_fullres, fold='all', transfer learning from
# Castaño's checkpoint (TBI model). Files expected in NNUNET_MODEL_DIR:
#   - checkpoint_best.pth   (~235 MB)
#   - plans.json
#   - dataset.json
#   - dataset_fingerprint.json  (OPTIONAL — only used for planning/training,
#     not read by initialize_from_trained_model_folder at inference time)
# nnUNet expects a specific folder structure when calling
# initialize_from_trained_model_folder — we build it at runtime with symlinks.
NNUNET_MODEL_DIR    = MODELS_DIR / "nnunet_ideas_fold_all"
NNUNET_DATASET_NAME = "Dataset015_TCEC"
NNUNET_TRAINER      = "nnUNetTrainer_250epochs"
NNUNET_PLANS_NAME   = "nnUNetPlans"
NNUNET_CONFIG       = "3d_fullres"
NNUNET_FOLD         = "all"
NNUNET_CHECKPOINT   = "checkpoint_best.pth"

# Reported metrics — evaluation over 778 subjects (432 patients + 346
# controls) from the IDEAS_Epilepsy dataset.
#
# DSC and HD95: MEDIAN values are used, not the mean. The distribution is
# bimodal — the model either segments well (DSC > 0.8) or fails completely
# (DSC ≈ 0) when the lesion is absent in the T1. The median reflects typical
# behavior.
#   DSC mean:    0.6320 ± 0.3325  (dragged down by outliers like sub-18 = 0.0001)
#   DSC median:  0.8248           ← reported
#   HD95 mean:   38.96 ± 40.21 mm
#   HD95 median: 9.37 mm          ← reported
#
# Sensitivity / Specificity: at the SUBJECT level (detection rate and rate
# of controls without false positives), which is what is clinically useful.
# Voxel-wise sensitivity (0.699) and voxel-wise precision (0.618) are kept
# as reference.
NNUNET_METRICS = {
    "dsc_mean":           0.8248,  # median over 432 patients
    "hausdorff_95":       9.37,    # mm — median
    "sensitivity":        0.9051,  # subject-level detection rate (391/432)
    "specificity":        0.7890,  # controls without FP (273/346)
    "voxel_sensitivity":  0.6990,
    "voxel_precision":    0.6175,
    "cluster_f1":         0.4135,
    "ppv":                0.8427,
    "npv":                0.8694,
    "fp_per_control":     0.79,
}


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
