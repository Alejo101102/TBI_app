"""
nifti_utils.py — Validation and utilities for NIfTI files
Verifies that the T1 image is valid before entering the pipeline.
"""

import gzip
import shutil
from pathlib import Path

import nibabel as nib
import numpy as np

from app.config import TMP_DIR, VBM_PARAMS


# ─── Validation and loading ──────────────────────────────────────────────────

def validate_and_load(nii_path: Path) -> Path:
    """
    Validates that the file is a usable T1 NIfTI and decompresses it
    if it arrived as .nii.gz. Returns the path to the decompressed .nii.

    Checks:
    - The file exists and is non-empty
    - It is a valid NIfTI (nibabel can read it)
    - It is 3D (not 4D functional)
    - It has reasonable dimensions for a structural T1
    - Intensity values are not all zero

    Raises:
        ValueError: if any validation fails, with a descriptive message.
    """
    nii_path = Path(nii_path)

    if not nii_path.exists():
        raise ValueError(f"Archivo no encontrado: {nii_path.name}")
    if nii_path.stat().st_size == 0:
        raise ValueError(f"El archivo está vacío: {nii_path.name}")

    # Decompress .nii.gz if needed
    if nii_path.suffix == ".gz":
        nii_path = _decompress_gz(nii_path)

    # Try loading with nibabel
    try:
        img = nib.load(str(nii_path))
    except Exception as e:
        raise ValueError(f"No es un archivo NIfTI válido: {e}")

    shape = img.shape

    # Must be 3D
    if len(shape) < 3:
        raise ValueError(
            f"La imagen tiene {len(shape)} dimensiones. Se esperan 3 (T1 estructural)."
        )
    if len(shape) == 4 and shape[3] > 1:
        raise ValueError(
            f"La imagen es 4D ({shape}). Solo se aceptan imágenes T1 estructurales 3D."
        )

    # Minimum reasonable dimensions for a brain T1
    min_dim = 64
    if any(d < min_dim for d in shape[:3]):
        raise ValueError(
            f"Dimensiones demasiado pequeñas: {shape[:3]}. "
            f"Se esperan al menos {min_dim} vóxeles por eje."
        )

    # Maximum dimensions (avoid whole-body images or bad formatting)
    max_dim = 600
    if any(d > max_dim for d in shape[:3]):
        raise ValueError(
            f"Dimensiones inusualmente grandes: {shape[:3]}. "
            f"Verifica que sea una imagen T1 cerebral."
        )

    # Check that the image is not all zeros
    try:
        data = np.asarray(img.dataobj, dtype=np.float32)
        if np.max(np.abs(data)) < 1e-6:
            raise ValueError("La imagen no contiene datos de intensidad (todos los vóxeles son cero).")
    except MemoryError:
        # Very large image — we cannot validate the data, continue
        pass

    return nii_path


def _decompress_gz(gz_path: Path) -> Path:
    """
    Decompress a .nii.gz into the same directory and return the .nii path.
    If the .nii already exists (from a previous run), reuse it.
    """
    # Handle both sub.nii.gz and sub.nii (double extension)
    if gz_path.stem.endswith(".nii"):
        out_path = gz_path.parent / gz_path.stem   # strip .gz → .nii
    else:
        out_path = gz_path.parent / (gz_path.stem + ".nii")

    if out_path.exists():
        return out_path

    with gzip.open(gz_path, "rb") as f_in:
        with open(out_path, "wb") as f_out:
            shutil.copyfileobj(f_in, f_out)

    return out_path


# ─── Image info ──────────────────────────────────────────────────────────────

def get_image_info(nii_path: Path) -> dict:
    """
    Return a dict with basic info about the NIfTI image.
    Useful for logging and diagnostics.
    """
    img    = nib.load(str(nii_path))
    vox    = np.sqrt(np.sum(img.affine[:3, :3] ** 2, axis=0))
    return {
        "shape":      img.shape,
        "voxel_size": tuple(round(float(v), 3) for v in vox),
        "dtype":      str(img.get_data_dtype()),
        "affine_ok":  not np.allclose(img.affine, np.eye(4)),
    }


# ─── Volumetric features from mwp1 ───────────────────────────────────────────

def extract_volumetric_features(gm_map_path: Path) -> dict:
    """
    Extract scalar features from the modulated GM map (mwp1) produced by SPM12.
    These features feed the SVM in the hybrid pipeline.

    The 0.1 threshold is the same one used in the MATLAB training script
    (run_vbm_spm12_checkpoint.m, Phase 4).

    Returns:
        dict with gm_volume_mm3, gm_volume_cm3, gm_mean_density,
        gm_std_density, gm_voxels, percentiles and shape.
    """
    threshold = VBM_PARAMS["gm_threshold"]  # 0.1

    img  = nib.load(str(gm_map_path))
    data = np.asarray(img.dataobj, dtype=np.float32)

    # Voxel size in mm
    vox     = np.sqrt(np.sum(img.affine[:3, :3] ** 2, axis=0))
    vox_vol = float(np.prod(vox))

    # GM mask
    mask    = data > threshold
    n_vox   = int(np.sum(mask))

    if n_vox == 0:
        raise ValueError(
            f"No se encontraron vóxeles GM por encima del umbral {threshold}. "
            "Verifica que el mapa GM sea válido."
        )

    gm_vals   = data[mask]
    gm_vol    = n_vox * vox_vol

    features = {
        "gm_volume_mm3":    round(gm_vol, 2),
        "gm_volume_cm3":    round(gm_vol / 1000, 4),
        "gm_mean_density":  float(np.mean(gm_vals)),
        "gm_std_density":   float(np.std(gm_vals)),
        "gm_voxels":        n_vox,
        "gm_p10":           float(np.percentile(gm_vals, 10)),
        "gm_p25":           float(np.percentile(gm_vals, 25)),
        "gm_p50":           float(np.percentile(gm_vals, 50)),
        "gm_p75":           float(np.percentile(gm_vals, 75)),
        "gm_p90":           float(np.percentile(gm_vals, 90)),
        "gm_max":           float(np.max(gm_vals)),
        "shape":            data.shape,
        "voxel_size_mm":    tuple(round(float(v), 3) for v in vox),
    }

    # Verify the expected shape
    expected = tuple(VBM_PARAMS["expected_shape"])
    if data.shape != expected:
        # Not fatal — only a warning, may differ due to bb
        features["shape_warning"] = (
            f"Shape {data.shape} difiere del esperado {expected}. "
            "Verifica los parámetros de normalización."
        )

    return features
