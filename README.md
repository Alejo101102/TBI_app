# VBM App

Web application for assisted detection of epileptogenic lesions on structural T1-weighted MRI, using two complementary deep-learning pipelines: a 3D convolutional classifier on Voxel-Based Morphometry (VBM) maps and an nnU-Net segmentation network.

Developed as the undergraduate thesis project of **Kevin Velez** (Systems Engineering, Universidad del Valle) at the **Multimedia and Computer Vision Laboratory**, Cali, Colombia.

---

## Table of contents

1. [What it does](#what-it-does)
2. [Models included](#models-included)
3. [Architecture](#architecture)
4. [Technology stack](#technology-stack)
5. [System requirements](#system-requirements)
6. [Getting the trained models](#getting-the-trained-models)
7. [First-time setup](#first-time-setup)
8. [Running the application](#running-the-application)
9. [Project structure](#project-structure)
10. [Usage notes](#usage-notes)
11. [Limitations and clinical disclaimer](#limitations-and-clinical-disclaimer)
12. [Contact](#contact)

---

## What it does

The user uploads a single T1-weighted brain MRI in NIfTI format (`.nii` or `.nii.gz`), selects one of two pre-trained models, and receives:

- A binary verdict: **possible epilepsy** vs **control** (no findings).
- For the classification pipeline: probability scores plus volumetric features of gray matter.
- For the segmentation pipeline: a binary 3D mask localizing the suspected epileptogenic zone, with cluster statistics (total volume, number of connected components, size of the largest cluster).
- An interactive 2D viewer (axial, coronal, sagittal) with the mask overlaid on the T1.
- A downloadable plain-text report and, for the segmentation model, the mask as a `.nii.gz` file ready to load in FSL, MRIcroGL, ITK-SNAP, etc.

The whole pipeline runs locally inside Docker containers; no MRI data leaves the host.

---

## Models included

| ID            | Type           | Backbone                                  | Reported metric          | Notes                                                                                       |
| ------------- | -------------- | ----------------------------------------- | ------------------------ | ------------------------------------------------------------------------------------------- |
| `deepmriprep` | Classification | MedicalNet ResNet-18 3D on modulated GM maps | AUC-ROC 79.7%, Sens 55.8%, Spec 88.4% | Preprocessing fully in PyTorch (deepmriprep): brain extraction, tissue segmentation, MNI registration, modulation. Cross-platform reproducible. |
| `nnunet`      | Segmentation   | nnU-Net v2 3D fullres (PlainConvUNet, 6 stages) | DSC median 82.5%, HD95 9.4 mm, Sens 90.5%, Spec 78.9% | Transfer-learning from the TBI segmentation model of Castaño (2025). Trained on 432 epilepsy patients with resection masks plus 346 controls with empty masks. |

The classification model was originally trained on SPM12+DARTEL GM maps. We migrated to deepmriprep after detecting non-reproducible voxel counts between macOS (training) and Linux Docker (inference) with SPM12 r7771 — a documented finding of the thesis.

A hybrid (CNN + SVM on volumetric features) was evaluated and discarded: the optimal fusion weight collapsed to `w_CNN = 1.00`, showing the volumetric features did not add discriminative signal on deepmriprep maps.

---

## Architecture

```
+----------------+        HTTP        +-----------------+
|   Frontend     | <----------------> |     Backend     |
|  React + Vite  |   /api/v1/...      |   FastAPI       |
|  served by     |                    |   PyTorch +     |
|  Nginx :3000   |                    |   nnUNetv2      |
+----------------+                    +-----------------+
                                            |
                                            v
                              +-----------------------------+
                              |  backend/models  (mounted)  |
                              |   deepmriprep_cnn_*.pt      |
                              |   nnunet_ideas_fold_all/    |
                              +-----------------------------+
```

- **Frontend**: single-page React app, no SSR, talks to the backend via `/api/v1/*` (proxied by Nginx in production, by Vite in development).
- **Backend**: FastAPI exposes `POST /analyze`, `GET /status/{job_id}`, `GET /report/{job_id}`, `GET /t1/{job_id}`, `GET /mask/{job_id}`. Jobs run in a background thread; the frontend polls status every 1.5 s. Job state is persisted to a JSON snapshot so it survives container restarts.
- **Viewer**: pure 2D canvas (no WebGL), `nifti-reader-js` + `pako` decode the NIfTI client-side. Reliable across browsers, no large 3D viewer dependency.

---

## Technology stack

**Backend (Python 3.11):**

- FastAPI + Uvicorn
- PyTorch 2.3.1 (CPU build by default)
- nibabel, nilearn, NumPy, SciPy
- deepmriprep 0.2.0 (PyTorch port of SPM-style VBM preprocessing)
- nnunetv2 2.5.1 + SimpleITK
- ROBEX (optional skull-stripping, off by default)

**Frontend (Node 20):**

- React 18 + Vite 6
- nifti-reader-js + pako (NIfTI parser for the viewer)
- No external UI framework; CSS variables and hand-rolled components

**Infrastructure:**

- Docker + Docker Compose
- Multi-stage build for the frontend (Vite build then Nginx)

---

## System requirements

Minimum (CPU-only, recommended for the thesis demo):

- **OS**: Windows 10/11, macOS 12+, or Linux with Docker support
- **Docker Desktop**: 4.20 or newer
- **RAM allocated to Docker**: 6 GB (8 GB recommended for nnU-Net inference)
- **Disk space**: 10 GB free (Docker images ~3 GB + trained models ~600 MB + intermediate files)
- **CPU**: any modern x86-64 (Intel/AMD); inference on CPU takes 5-7 minutes per case
- **Network**: required only for the first build (pulling base images and Python/Node packages)

Optional (much faster inference):

- NVIDIA GPU with CUDA 12-compatible driver and `nvidia-container-toolkit`; uncomment the `deploy.resources` block in `docker-compose.yml`. Inference drops to under 60 seconds per case.

---

## Getting the trained models

The trained model weights are not included in this repository because of their size (around 600 MB combined) and licensing context. To request them, please send an email to the author:

**kevin.alejandro.velez@correounivalle.edu.co**

You will receive a zip with the following files, to be placed under `backend/models/`:

```
backend/models/
├── deepmriprep_cnn_fold3_script.pt          (CNN classifier, ~130 MB)
└── nnunet_ideas_fold_all/
    ├── checkpoint_best.pth                  (nnU-Net weights, ~235 MB)
    ├── plans.json
    ├── dataset.json
    └── dataset_fingerprint.json
```

The backend validates these files on startup and prints a clear error if any are missing.

---

## First-time setup

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop) and start it.
   - On Windows/macOS, raise the memory limit: Docker Desktop → Settings → Resources → Memory → 6-8 GB.

2. Clone the repository and place the trained models you received via email:

   ```bash
   git clone <repo-url>
   cd vbm-app
   # copy the zip you received into backend/models/ and unzip it there
   ```

3. (Optional) Place the ROBEX binary in `backend/vendor/ROBEXv12.linux64.tar.gz` if you intend to enable the optional skull-stripping toggle. The pipeline runs fine without it (deepmriprep performs brain extraction internally).

4. Build the images (this may take 10-15 minutes the first time, mainly downloading PyTorch and nnU-Net dependencies):

   ```bash
   docker compose build
   ```

---

## Running the application

Start the services in the background:

```bash
docker compose up -d
```

Then open `http://localhost:3000` in any modern browser (Chrome, Firefox, Edge — Safari should also work).

Stop the services:

```bash
docker compose down
```

Rebuild after editing code:

```bash
docker compose up -d --build backend     # backend changes
docker compose up -d --build frontend    # frontend changes
```

View live logs:

```bash
docker logs -f vbm_backend
docker logs -f vbm_frontend
```

---

## Project structure

```
vbm-app/
├── docker-compose.yml
├── README.md
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── models/                              # trained weights (received by email)
│   ├── tmp/                                 # job working directory (mounted volume)
│   └── app/
│       ├── main.py                          # FastAPI entrypoint
│       ├── config.py                        # paths, model metrics, thresholds
│       ├── api/
│       │   ├── routes.py                    # /analyze, /status, /report, /t1, /mask
│       │   └── schemas.py                   # Pydantic request/response models
│       ├── pipelines/
│       │   ├── deepmriprep_pipeline.py      # VBM preprocessing + CNN inference
│       │   └── nnunet.py                    # nnU-Net 3D fullres inference
│       ├── classifiers/
│       │   └── cnn_model.py                 # 3D CNN loader + preprocessing
│       └── preprocessing/
│           ├── nifti_utils.py
│           └── robex.py
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── vite.config.js
    └── src/
        ├── App.jsx
        ├── main.jsx
        ├── index.css
        ├── api/client.js                    # fetch wrappers for the FastAPI endpoints
        ├── components/
        │   ├── NiiVueViewer.jsx             # 2D canvas viewer (T1 + mask overlay)
        │   ├── DropZone.jsx
        │   ├── Brain.jsx
        │   ├── Gauge.jsx
        │   ├── Spinner.jsx
        │   ├── Footer.jsx
        │   └── LanguageToggle.jsx
        ├── data/models.js                   # static metadata of available models
        ├── i18n/                            # Spanish / English translations
        └── screens/
            ├── HomeScreen.jsx
            ├── UploadScreen.jsx
            ├── ProcessingScreen.jsx
            ├── ResultsScreen.jsx
            └── AboutScreen.jsx
```

---

## Usage notes

- **Accepted input**: a single skull-on (or skull-stripped) T1-weighted volume in NIfTI format. Maximum upload size 500 MB.
- **Processing time on CPU**: classification pipeline ~3-5 minutes, segmentation pipeline ~5-7 minutes. The progress bar advances within each step.
- **Skull stripping**: off by default. Deepmriprep performs brain extraction internally (via deepbet). Enable the ROBEX toggle only if your T1 is already skull-stripped or you specifically want classical morphological extraction.
- **Mask download**: the segmentation pipeline writes the mask to `backend/tmp/<job_id>/nnunet_out/subject.nii.gz`. The download button serves it via `/api/v1/mask/<job_id>`.
- **Job persistence**: the backend keeps a snapshot of job states in `backend/tmp/_jobs_snapshot.json`. If the container restarts during inference, the frontend will see an `error` status with a clear message instead of a generic 404.
- **Language**: the UI toggle (top-right) switches all text and the generated report between Spanish and English; the choice is stored in `localStorage`.

---

## Limitations and clinical disclaimer

This software is a **research prototype** developed for an undergraduate thesis. It must not be used for clinical decision-making. The models were trained on a single open dataset (IDEAS Epilepsy) and have not been validated on independent populations or scanner manufacturers. Results must always be interpreted by a qualified neurologist or epileptologist.

Key known limitations:

- The classification CNN tends to output probabilities concentrated near the clinical threshold (0.6875), which limits the discriminative margin for borderline cases.
- The segmentation model has a strongly bimodal Dice distribution: many cases segment well (median DSC > 0.82) but a fraction fail almost completely when the lesion is not visible on the T1. The reported sensitivity (90.5%) is per-subject (any prediction counts as a detection), not per-voxel.
- Cross-platform reproducibility was the driver for migrating away from SPM12+MATLAB Runtime. The current PyTorch-based preprocessing is bit-reproducible between macOS, Linux, and Windows hosts.

---

## Contact

For trained weights, dataset questions, or to report bugs:

**Kevin Velez**
Systems Engineering, Universidad del Valle
Multimedia and Computer Vision Laboratory
kevin.alejandro.velez@correounivalle.edu.co
