"""
config.py — Central configuration for the VBM backend
All paths, parameters and system constants are defined here.

Current pipeline: deepmriprep (pure PyTorch) → CNN MedicalNet ResNet-18.
ROBEX remains as OPTIONAL skull-stripping before deepmriprep
(frontend toggle `use_robex` — OFF by default, since deepmriprep performs
brain extraction internally via deepbet).
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

# ─── CNN model (trained on mwp1 maps from deepmriprep) ───────────────────────
# The .pt is TorchScript serialized with torch.jit.SCRIPT (NOT trace).
# Fold 3 = best individual fold (AUC 0.7968 — the highest of the 5)
#
# HISTORY: the first version used torch.jit.trace, which introduced a
# systematic bias of ~0.062 in P(epi) due to bad interaction with
# `functools.partial` in the downsample blocks. Since the clinical threshold
# is 0.6875, the bias turned 50% of epilepsy predictions into "control"
# (P(epi) dropped from >0.69 to ~0.63). torch.jit.script analyzes the code
# statically and reproduces inference 1:1 with the original model
# (Δ = 0 across 30 test subjects).
CNN_MODEL_PATH = MODELS_DIR / "deepmriprep_cnn_fold3_script.pt"

# ─── VBM parameters (used by nifti_utils.extract_volumetric_features) ────────
# `gm_threshold`: standard threshold for the GM mask over modulated mwp1
#                 (same value as in the training notebook).
# `expected_shape`: MNI152 shape produced by deepmriprep, used as a QC tag.
VBM_PARAMS = {
    "gm_threshold":   0.1,
    "expected_shape": (113, 137, 113),   # deepmriprep MNI152 — differs from (121,145,121) produced by SPM12
}

# ─── nnU-Net (segmentation of epileptogenic zones) ───────────────────────────
# The model was trained on Colab with Dataset500_IDEAS_Epilepsy,
# nnUNetTrainer_250epochs, 3d_fullres, fold='all', transfer learning from
# Castaño's checkpoint (TBI model). Files expected in NNUNET_MODEL_DIR:
#   - checkpoint_best.pth   (~235 MB)
#   - plans.json
#   - dataset.json
#   - dataset_fingerprint.json
# nnUNet expects a specific folder structure when calling
# initialize_from_trained_model_folder — we build it at runtime with symlinks.
NNUNET_MODEL_DIR    = MODELS_DIR / "nnunet_ideas_fold_all"
NNUNET_DATASET_NAME = "Dataset500_IDEAS_Epilepsy"
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


CNN_CONFIG = {
    # CNN input shape after resample (same as during training)
    # target_affine = np.diag([1.9, 1.9, 1.9, 1]) → 96×96×96
    "input_shape":    (96, 96, 96),
    "target_affine":  [1.9, 1.9, 1.9],   # voxel size in mm of the resize
    "num_classes":    2,

    # Clinical threshold optimized on validation for Specificity >= 0.85
    # From fold 3: threshold=0.6875, Spec=0.884, Sens=0.558
    "clinical_threshold": 0.6875,
}

# ─── API ─────────────────────────────────────────────────────────────────────
API_CONFIG = {
    "max_upload_mb":    500,
    "allowed_suffixes": [".nii", ".gz"],
    "job_timeout_sec":  900,
}

# ─── Hardware ────────────────────────────────────────────────────────────────
# deepmriprep uses this same logic: no_gpu = not torch.cuda.is_available()
DEVICE = "cuda" if torch.cuda.is_available() else "cpu"

# ─── Asset validation at startup ─────────────────────────────────────────────
def validate_assets() -> dict:
    checks = {
        "cnn_model":          CNN_MODEL_PATH.exists(),
        "robex":              ROBEX_SCRIPT.exists(),
        "nnunet_checkpoint":  (NNUNET_MODEL_DIR / NNUNET_CHECKPOINT).exists(),
        "nnunet_plans":       (NNUNET_MODEL_DIR / "plans.json").exists(),
        "nnunet_dataset":     (NNUNET_MODEL_DIR / "dataset.json").exists(),
        "nnunet_fingerprint": (NNUNET_MODEL_DIR / "dataset_fingerprint.json").exists(),
    }

    missing = [k for k, v in checks.items() if not v]
    if missing:
        print(f"[CONFIG] ADVERTENCIA — assets faltantes: {missing}")
    else:
        print(f"[CONFIG] Todos los assets verificados OK ({len(checks)} checks)")
    return checks


if __name__ == "__main__":
    results = validate_assets()
    for asset, ok in results.items():
        print(f"  {'✓' if ok else '✗ FALTA'}  {asset}")
