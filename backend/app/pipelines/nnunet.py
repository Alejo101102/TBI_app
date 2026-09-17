"""
nnunet.py — 3D-nnU-Net segmentation pipeline for localizing epileptogenic
            zones.

Model: 3d_fullres, nnUNetTrainer_250epochs, fold=all, transfer learning from
Castaño's TBI checkpoint (2025). Trained on Dataset500 (IDEAS_Epilepsy) with
resection masks for patients + empty masks for controls.

Model ARCHITECTURE:
  - 3D PlainConvUNet, 6 stages, features [32, 64, 128, 256, 320, 320]
  - patch [128, 128, 128], batch 2, spacing [1.05, 1.0, 1.0]
  - Normalization: ZScoreNormalization
  - Output: binary mask (0=background, 1=putative epileptogenic zone)

Backend FLOW (ModelType.NNUNET):
  1. Loading T1 image              ← routes.py
  2. (Optional) ROBEX skull strip  ← routes.py (use_robex toggle)
  3. nnUNet segmentation           ← this module (3D inference)
  4. Mask analysis                 ← this module (clusters, volume)

PERFORMANCE:
  - NVIDIA GPU: <60s per subject
  - CPU: ~15-30 min per subject (acceptable for the deployable app)
"""

import time
import shutil
import gzip
from pathlib import Path
from typing import Callable

import numpy as np
import nibabel as nib
import torch

from app.config import (
    TMP_DIR, DEVICE,
    NNUNET_MODEL_DIR, NNUNET_FOLD, NNUNET_CHECKPOINT,
    NNUNET_METRICS,
)
from app.api.schemas import AnalysisResult, ModelType, StepStatus


# ─── Predictor singleton ─────────────────────────────────────────────────────
# nnU-Net loads ~235 MB of weights + plans — caching it across jobs saves a lot.
_predictor = None


def _setup_model_folder() -> Path:
    """
    nnU-Net expects a specific structure when calling
    initialize_from_trained_model_folder():

        <model_training_output_dir>/
          fold_all/checkpoint_best.pth
          dataset.json
          plans.json
          dataset_fingerprint.json

    The user dropped the 4 flat files in NNUNET_MODEL_DIR. Here we build the
    expected structure with symlinks (or copies, if symlinks fail) inside
    /app/tmp/_nnunet_setup/.
    """
    setup_dir = TMP_DIR / "_nnunet_setup"
    fold_dir  = setup_dir / f"fold_{NNUNET_FOLD}"

    setup_dir.mkdir(parents=True, exist_ok=True)
    fold_dir.mkdir(parents=True, exist_ok=True)

    pairs = [
        (NNUNET_MODEL_DIR / NNUNET_CHECKPOINT,  fold_dir / NNUNET_CHECKPOINT),
        (NNUNET_MODEL_DIR / "plans.json",       setup_dir / "plans.json"),
        (NNUNET_MODEL_DIR / "dataset.json",     setup_dir / "dataset.json"),
        (NNUNET_MODEL_DIR / "dataset_fingerprint.json",
                                                setup_dir / "dataset_fingerprint.json"),
    ]
    for src, dst in pairs:
        if dst.exists() or dst.is_symlink():
            continue
        if not src.exists():
            raise FileNotFoundError(f"Archivo nnUNet no encontrado: {src}")
        try:
            dst.symlink_to(src)
        except (OSError, NotImplementedError):
            shutil.copy2(str(src), str(dst))

    return setup_dir


def get_predictor():
    """
    Load the nnUNetPredictor singleton. First call takes ~30-60s
    (loads weights + builds the network). Subsequent calls reuse it.
    """
    global _predictor
    if _predictor is not None:
        return _predictor

    # Lazy import — nnunetv2 is heavy.
    from nnunetv2.inference.predict_from_raw_data import nnUNetPredictor

    setup_dir = _setup_model_folder()

    print(f"[nnUNet] Cargando predictor desde {setup_dir} → {DEVICE.upper()}")
    t0 = time.time()

    use_gpu = torch.cuda.is_available()
    # Configuration for CPU inference with low RAM (~2-4 GB in Docker):
    #  - tile_step_size=0.7  → fewer overlapping patches (was 0.5)
    #  - use_mirroring=False → disables flip-based TTA (4× less memory)
    # Expected loss in DSC: ~1-2 pts. Acceptable for an interactive app
    # in exchange for not dying from OOM.
    predictor = nnUNetPredictor(
        tile_step_size=0.7,
        use_gaussian=True,
        use_mirroring=False,
        perform_everything_on_device=use_gpu,
        device=torch.device(DEVICE),
        verbose=False,
        verbose_preprocessing=False,
        allow_tqdm=False,
    )
    predictor.initialize_from_trained_model_folder(
        str(setup_dir),
        use_folds=(NNUNET_FOLD,),
        checkpoint_name=NNUNET_CHECKPOINT,
    )

    print(f"[nnUNet] Predictor cargado OK en {time.time() - t0:.1f}s "
          f"(device={DEVICE}, GPU={'sí' if use_gpu else 'no'})")
    _predictor = predictor
    return predictor


# ─── Public pipeline ─────────────────────────────────────────────────────────

def run(brain_path: Path, job_id: str,
        update_step: Callable, metadata: dict) -> AnalysisResult:
    """
    Full nnUNet pipeline.

    Args:
        brain_path:  T1 (raw or post-ROBEX depending on the use_robex toggle).
        job_id:      Job ID.
        update_step: callback(job_id, step_num, StepStatus, msg=None)
        metadata:    dict with test_name, patient_name, notes.
    """
    brain_path = Path(brain_path)
    job_dir    = TMP_DIR / job_id
    job_dir.mkdir(parents=True, exist_ok=True)

    # ── Step 3: nnUNet inference ─────────────────────────────────────────────
    update_step(job_id, 3, StepStatus.IN_PROGRESS,
                f"Segmentación 3D nnU-Net ({'GPU' if torch.cuda.is_available() else 'CPU'})...")
    try:
        mask_path = _run_nnunet_inference(brain_path, job_dir)
    except Exception as e:
        update_step(job_id, 3, StepStatus.ERROR, str(e))
        raise RuntimeError(f"nnU-Net segmentación falló: {e}") from e

    update_step(job_id, 3, StepStatus.COMPLETED,
                f"máscara: {mask_path.name}")

    # ── Step 4: Mask analysis ────────────────────────────────────────────────
    update_step(job_id, 4, StepStatus.IN_PROGRESS,
                "Análisis de clusters y volumetría...")
    try:
        mask_stats = _analyze_mask(mask_path)
    except Exception as e:
        update_step(job_id, 4, StepStatus.ERROR, str(e))
        raise RuntimeError(f"Análisis de máscara falló: {e}") from e

    update_step(job_id, 4, StepStatus.COMPLETED,
                f"{mask_stats['n_clusters']} cluster(s), "
                f"{mask_stats['mask_volume_cm3']:.2f} cm³ totales")

    # ── Result ───────────────────────────────────────────────────────────────
    # So /t1/{job_id} can serve the file, we keep the T1 as `t1.nii.gz` in
    # job_dir. If it arrived without .gz we compress it on the fly so NiiVue
    # loads it uniformly.
    t1_dst_name = "t1.nii.gz"
    t1_dst      = job_dir / t1_dst_name
    if not t1_dst.exists():
        _copy_as_nii_gz(brain_path, t1_dst)

    # ── Classification derived from the mask ──────────────────────────────
    # Training notebook rule: any segmented voxel counts as
    # "epilepsy detected" (detection rate 0.9051). An empty mask classifies
    # as "control" (specificity 0.7890). We do NOT apply a minimum-volume
    # threshold — that would degrade the reported sensitivity.
    is_epi      = mask_stats["mask_voxels"] > 0
    prediction  = "epilepsy" if is_epi else "control"

    # "Confidence" = subject-level sensitivity/specificity of the model for
    # the predicted class. It is not a true Bayesian probability (nnUNet
    # does not produce one); it is the most honest metric we can attach
    # without making one up.
    confidence  = (NNUNET_METRICS["sensitivity"] if is_epi
                   else NNUNET_METRICS["specificity"])
    prob_epi    = NNUNET_METRICS["sensitivity"] if is_epi else (1 - NNUNET_METRICS["specificity"])
    prob_ctrl   = 1 - prob_epi

    return AnalysisResult(
        # Derived prediction
        prediction          = prediction,
        confidence          = confidence,
        prob_epilepsy       = prob_epi,
        prob_control        = prob_ctrl,
        # Segmentation
        mask_filename       = mask_path.name,
        t1_filename         = t1_dst_name,
        mask_voxels         = mask_stats["mask_voxels"],
        mask_volume_cm3     = mask_stats["mask_volume_cm3"],
        n_clusters          = mask_stats["n_clusters"],
        largest_cluster_cm3 = mask_stats["largest_cluster_cm3"],
        model_dsc               = NNUNET_METRICS.get("dsc_mean"),
        model_hd95              = NNUNET_METRICS.get("hausdorff_95"),
        model_seg_sensitivity   = NNUNET_METRICS.get("sensitivity"),
        model_seg_specificity   = NNUNET_METRICS.get("specificity"),
        model_seg_ppv           = NNUNET_METRICS.get("ppv"),
        model_seg_npv           = NNUNET_METRICS.get("npv"),
        model_used              = ModelType.NNUNET,
        test_name           = metadata.get("test_name", ""),
        patient_name        = metadata.get("patient_name"),
        notes               = metadata.get("notes"),
    )


# ─── Helpers ─────────────────────────────────────────────────────────────────

def _run_nnunet_inference(t1_path: Path, job_dir: Path) -> Path:
    """
    Call the predictor with a single T1 and return the path to the generated mask.

    nnU-Net expects input as a list of lists (multi-channel support):
        [[t1_path]]   — single channel T1
    Returns a .nii.gz with the binary mask (0/1).
    """
    predictor = get_predictor()

    out_dir = job_dir / "nnunet_out"
    out_dir.mkdir(parents=True, exist_ok=True)

    # Rename the T1 to the nnUNet format (<case>_0000.nii.gz) so the output
    # has a clean name (<case>.nii.gz).
    case_id     = "subject"
    case_input  = out_dir / f"{case_id}_0000.nii.gz"
    if not case_input.exists():
        _copy_as_nii_gz(t1_path, case_input)

    expected_output = out_dir / f"{case_id}.nii.gz"

    print(f"[nnUNet] Inferencia sobre {t1_path.name} → {expected_output.name}")
    t0 = time.time()

    # ── "Low-level" path without multiprocessing ───────────────────────────
    # predict_from_files (with or without _sequential) uses multiprocessing
    # workers internally for preprocess/export. When one of those workers
    # calls os._exit(0) (typical after exporting), it terminates the WHOLE
    # parent process → uvicorn dies → JOBS loses the job → 404.
    #
    # predict_single_npy_array is the in-process API: I hand it a np.ndarray
    # and it returns a np.ndarray. I handle I/O myself. ZERO multiprocessing.
    img      = nib.load(str(case_input))
    data     = np.asarray(img.dataobj, dtype=np.float32)
    affine   = img.affine
    # nnUNet expects shape (C, X, Y, Z) — add the channel dim
    input_4d = data[None, :, :, :]
    # `spacing`: voxel size in mm (X, Y, Z) — derived from the affine
    voxel_sz = tuple(float(s) for s in np.sqrt((affine[:3, :3] ** 2).sum(axis=0)))
    image_props = {"spacing": voxel_sz}

    seg = predictor.predict_single_npy_array(
        input_image       = input_4d,
        image_properties  = image_props,
        segmentation_previous_stage = None,
        output_file_truncated       = None,   # returns the array, does not write
        save_or_return_probabilities= False,
    )
    # seg is a np.ndarray (X, Y, Z) with the binary mask
    seg_img = nib.Nifti1Image(seg.astype(np.uint8), affine, header=img.header)
    seg_img.set_data_dtype(np.uint8)
    nib.save(seg_img, str(expected_output))

    elapsed = time.time() - t0
    print(f"[nnUNet] Inferencia completada en {elapsed:.1f}s "
          f"(camino in-process, sin workers)")

    if not expected_output.exists():
        raise RuntimeError(
            f"nnUNet no generó la máscara esperada {expected_output}."
        )
    return expected_output


def _analyze_mask(mask_path: Path) -> dict:
    """
    Post-segmentation analysis: voxel count, volume, connected clusters.
    """
    img  = nib.load(str(mask_path))
    data = np.asarray(img.dataobj, dtype=np.uint8)

    # Voxel volume in mm³
    vox     = np.sqrt((img.affine[:3, :3] ** 2).sum(axis=0))
    vox_vol = float(np.prod(vox))   # mm³ per voxel

    mask    = data > 0
    n_vox   = int(mask.sum())
    vol_cm3 = (n_vox * vox_vol) / 1000.0

    n_clusters          = 0
    largest_cluster_cm3 = 0.0
    if n_vox > 0:
        try:
            from scipy.ndimage import label
            structure = np.ones((3, 3, 3), dtype=np.uint8)  # 26-connectivity
            labeled, n_clusters = label(mask, structure=structure)
            if n_clusters > 0:
                sizes = np.bincount(labeled.ravel())[1:]  # ignore background
                largest_cluster_cm3 = round(float(sizes.max() * vox_vol / 1000.0), 4)
        except Exception as e:
            print(f"[nnUNet] Análisis de clusters falló (no crítico): {e}")
            n_clusters = -1

    return {
        "mask_voxels":         n_vox,
        "mask_volume_cm3":     round(vol_cm3, 4),
        "n_clusters":          int(n_clusters),
        "largest_cluster_cm3": largest_cluster_cm3,
    }


def _copy_as_nii_gz(src: Path, dst: Path) -> None:
    """
    Copy a .nii or .nii.gz to a .nii.gz destination (compress if needed).
    Idempotent: if dst already exists, do nothing.
    """
    if dst.exists():
        return
    src = Path(src)
    if src.suffix == ".gz":
        shutil.copy2(str(src), str(dst))
        return
    with open(src, "rb") as f_in, gzip.open(str(dst), "wb", compresslevel=6) as f_out:
        shutil.copyfileobj(f_in, f_out)
