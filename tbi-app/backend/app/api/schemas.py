"""
schemas.py — Pydantic models for API request/response
"""

from pydantic import BaseModel, ConfigDict, Field
from typing import Optional, Literal
from enum import Enum


class ModelType(str, Enum):
    NNUNET = "nnunet"   # 3D nnU-Net segmentation (transfer learning from the TBI model)


# ─── Request (multipart, the .nii/.gz arrives as UploadFile in the route) ────
class AnalysisMetadata(BaseModel):
    """Optional metadata the user enters in the form."""
    test_name:    str            = Field(..., description="Nombre de la prueba")
    patient_name: Optional[str] = Field(None, description="Nombre del paciente")
    notes:        Optional[str] = Field(None, description="Notas clínicas")
    model:        ModelType     = Field(..., description="Pipeline a ejecutar")
    preprocess:   bool          = Field(False, description=(
        "Aplicar ROBEX + registro ANTs SyN al atlas SRI24 antes de la "
        "inferencia. Por defecto False. Activar si la T1 es cruda (con "
        "cráneo o sin registrar al SRI24)."
    ))


# ─── Job creation response ───────────────────────────────────────────────────
class JobCreatedResponse(BaseModel):
    job_id:  str
    message: str = "Job creado exitosamente"


# ─── Job status ──────────────────────────────────────────────────────────────
class StepStatus(str, Enum):
    PENDING    = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED  = "completed"
    ERROR      = "error"


class ProcessStep(BaseModel):
    step:    int
    name:    str
    status:  StepStatus
    message: Optional[str] = None


class JobStatusResponse(BaseModel):
    job_id:   str
    status:   Literal["pending", "running", "completed", "error"]
    progress: int = Field(ge=0, le=100, description="Porcentaje 0-100")
    steps:    list[ProcessStep]
    result:   Optional["AnalysisResult"] = None
    error:    Optional[str] = None


# ─── One connected component of the predicted mask ──────────────────────────
class LesionInfo(BaseModel):
    """Measured in the mask's space (SRI24). Sorted by volume, largest first."""
    volume_mm3:   float
    category:     Literal["small", "medium", "large"]   # < 100, 100-1000, > 1000 mm³
    slice_min:    int            # first axial slice (viewer slider index)
    slice_max:    int            # last axial slice
    centroid_vox: list[int]      # voxel indices (x, y, z)
    centroid_mm:  list[float]    # world coordinates in mm


# ─── Final result ────────────────────────────────────────────────────────────
class AnalysisResult(BaseModel):
    # The model_* fields collide with Pydantic v2's protected namespace
    # ("model_*" is usually reserved). Without this, every startup prints warnings.
    model_config = ConfigDict(protected_namespaces=())

    # ── Prediction derived from the segmentation mask ─────────────────────────
    prediction:        Optional[Literal["epilepsy", "control"]] = None
    confidence:        Optional[float] = Field(None, ge=0.0, le=1.0)
    prob_epilepsy:     Optional[float] = Field(None, ge=0.0, le=1.0)
    prob_control:      Optional[float] = Field(None, ge=0.0, le=1.0)

    # ── SEGMENTATION output (nnUNet) ─────────────────────────────────────────
    # mask_filename: name of the .nii.gz inside tmp/<job_id>/nnunet_out/
    #                the frontend loads it via GET /mask/{job_id}
    # t1_filename:   name of the T1 passed to nnUNet (for the viewer)
    mask_filename:     Optional[str]   = None
    t1_filename:       Optional[str]   = None
    mask_voxels:       Optional[int]   = None
    mask_volume_cm3:   Optional[float] = None
    n_clusters:        Optional[int]   = None   # connected clusters in the mask
    largest_cluster_cm3: Optional[float] = None
    lesions:           Optional[list[LesionInfo]] = None
    preprocessed:      Optional[bool]  = None   # ROBEX + SRI24 registration applied

    # ── Segmentation model metrics (constants, TCEC test set: 57 images) ─────
    # See NNUNET_METRICS in config.py for the definitions.
    model_dsc:                Optional[float] = None
    model_iou:                Optional[float] = None
    model_det_small:          Optional[float] = None   # detection rate, < 100 mm³
    model_det_medium:         Optional[float] = None   # detection rate, 100-1000 mm³
    model_det_large:          Optional[float] = None   # detection rate, > 1000 mm³
    model_fp_proportion:      Optional[float] = None   # FP / predicted lesions
    model_fp_per_subject:     Optional[float] = None

    # ── Analysis metadata ────────────────────────────────────────────────────
    model_used:        ModelType
    test_name:         str
    patient_name:      Optional[str] = None
    notes:             Optional[str] = None
    processing_time_s: Optional[float] = None


# Required for the forward reference in JobStatusResponse
JobStatusResponse.model_rebuild()


# ─── Anatomical viewer telemetry ─────────────────────────────────────────────
# The 2D viewer (frontend/src/components/NiiVueViewer.jsx) renders on the
# CLIENT's CPU with canvas2d — no WebGL, no GPU. The container never sees that
# work, so the browser measures it with performance.now() and POSTs it here;
# the route only prints it, so the numbers land in `docker logs tbi_backend`.
#
# Every field is Optional because the two phases ("load" and "render") share
# this one model: a load report fills the volume/load fields, a render report
# fills the stats/per_view fields.


class ViewerVolumeInfo(BaseModel):
    """Shape of a loaded volume — gives the timings their units."""
    dims:          list[int]   = Field(..., description="[nx, ny, nz] en vóxeles")
    voxels:        int         = Field(..., description="nx·ny·nz")
    voxel_size_mm: Optional[list[float]] = Field(None, description="pixDims[1..3]")
    datatype:      Optional[str] = Field(None, description="float32, int16, uint8…")


class ViewerLoadTimings(BaseModel):
    """One-off cost of opening the viewer, in milliseconds."""
    # T1 and mask are fetched concurrently via Promise.all, so these two
    # download times OVERLAP — the wall clock is not their sum.
    t1_download_ms:    Optional[float] = None
    t1_inflate_ms:     Optional[float] = None
    t1_parse_ms:       Optional[float] = None
    t1_bytes:          Optional[int]   = None   # compressed size on the wire
    mask_download_ms:  Optional[float] = None
    mask_inflate_ms:   Optional[float] = None
    mask_parse_ms:     Optional[float] = None
    mask_bytes:        Optional[int]   = None
    bbox_ms:           Optional[float] = None   # computeBoundingBox, O(nx·ny·nz)
    range_ms:          Optional[float] = None   # computeIntensityRange, 50k sample
    to_first_frame_ms: Optional[float] = None   # mount → first painted slice


class ViewerRenderStats(BaseModel):
    """Aggregate of a set of per-slice render samples, in milliseconds."""
    n:      int
    min_ms: float
    p50_ms: float
    p95_ms: float
    max_ms: float
    mean_ms: float


class ViewerClientInfo(BaseModel):
    """Client hardware — the point of the whole exercise is comparing machines."""
    cores:            Optional[int]   = Field(None, description="navigator.hardwareConcurrency")
    device_memory_gb: Optional[float] = Field(None, description="navigator.deviceMemory (solo Chromium)")
    dpr:              Optional[float] = Field(None, description="window.devicePixelRatio")
    user_agent:       Optional[str]   = None


class ViewerMetrics(BaseModel):
    phase: Literal["load", "render"]

    # ── phase == "load" ──────────────────────────────────────────────────────
    t1:     Optional[ViewerVolumeInfo]   = None
    mask:   Optional[ViewerVolumeInfo]   = None
    load:   Optional[ViewerLoadTimings]  = None

    # ── phase == "render" ────────────────────────────────────────────────────
    # `total` is the whole JS frame (slice + crop + draw); the others break it
    # down. `to_paint` is measured in a requestAnimationFrame after the render,
    # so it includes the compositor.
    total:    Optional[ViewerRenderStats] = None
    slice_:   Optional[ViewerRenderStats] = Field(None, alias="slice")
    crop:     Optional[ViewerRenderStats] = None
    draw:     Optional[ViewerRenderStats] = None
    to_paint: Optional[ViewerRenderStats] = None
    # Same aggregate split per anatomical view — axial reads contiguous memory,
    # coronal/sagittal read strided, so they are expected to differ.
    per_view: Optional[dict[str, ViewerRenderStats]] = None
    # Raw per-frame totals, capped so a long session cannot blow up the payload.
    # Logged as one compact JSON line for offline stats.
    samples:  Optional[list[float]] = Field(None, max_length=2000)

    client: Optional[ViewerClientInfo] = None

    # `slice` is a Python builtin, hence the slice_/alias pair above.
    model_config = ConfigDict(populate_by_name=True)
