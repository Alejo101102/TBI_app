"""
nnunet_normalization.py — Custom nnU-Net normalization scheme required by the
current checkpoint (backend/models/nnunet_ideas_fold_all/).

nnU-Net resolves the normalization class named in plans.json's
`normalization_schemes` by scanning nnunetv2/preprocessing/normalization/ for
a class with that exact name (recursive_find_python_class). The checkpoint
here was trained with a custom "KdeNormalization" class — wrapping the KDE
(kernel density estimation) tissue-mode normalizer from the
`intensity-normalization` package — that nnunetv2 does not ship out of the
box. Without registering it, preprocessing fails with:
    RuntimeError: Unable to locate class 'KdeNormalization' for normalization

This is copied verbatim from the training pipeline (TCEC-Segmentation,
src/nnunetv2/preprocessing/normalization/default_normalization_schemes.py) so
inference preprocessing matches training exactly — a different KDE
implementation would silently degrade segmentation quality.
"""

import numpy as np
from nnunetv2.preprocessing.normalization.default_normalization_schemes import ImageNormalization


class KdeNormalization(ImageNormalization):
    leaves_pixels_outside_mask_at_zero_if_use_mask_for_norm_is_true = True

    def run(self, image: np.ndarray, seg: np.ndarray = None) -> np.ndarray:
        from intensity_normalization.normalize import kde

        image = image.astype(self.target_dtype, copy=False)

        if self.use_mask_for_norm is not None and self.use_mask_for_norm:
            mask = (seg >= 0).astype(np.uint8)

            kde_normalizer = kde.KDENormalize()
            normalized = kde_normalizer.normalize_image(image, mask)

            return normalized.astype(self.target_dtype, copy=False)
        else:
            return image.astype(self.target_dtype, copy=False)


def register():
    """
    Patch KdeNormalization into nnunetv2's own module namespace so its
    recursive_find_python_class() lookup finds it via hasattr(). Must run
    before any nnU-Net preprocessing (predictor init or inference).
    """
    import nnunetv2.preprocessing.normalization.default_normalization_schemes as _schemes
    _schemes.KdeNormalization = KdeNormalization
