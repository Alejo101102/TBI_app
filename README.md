# TBI App

TBI App is a diagnostic support tool for identifying trauma-related injuries on T1 MRI images. It implements a 3D segmentation model (nnU-Net) that localizes areas affected by trauma.

Developed by **Alejandro Guerrero** (Systems Engineering, Universidad del Valle) at the **Multimedia and Computer Vision Laboratory**, Cali, Colombia. This application is based on [VBM App](https://github.com/Kvel12/VBM_App.git), developed by **Kevin Velez**.

---

## Table of contents

1. [What it does](#what-it-does)
2. [Models included](#models-included)
3. [Architecture](#architecture)
4. [Technology stack](#technology-stack)
5. [System requirements](#system-requirements)
6. [Getting the trained models](#getting-the-trained-models)
7. [Preprocessing: ROBEX + SRI24 registration](#preprocessing-robex--sri24-registration)
8. [First-time setup](#first-time-setup)
9. [Running the application](#running-the-application)
10. [Project structure](#project-structure)
11. [Usage notes](#usage-notes)
12. [Limitations and clinical disclaimer](#limitations-and-clinical-disclaimer)
13. [Contact](#contact)

---

## What it does

The user uploads a single T1-weighted brain MRI in NIfTI format (`.nii` or `.nii.gz`), optionally preprocesses it (ROBEX + registration to the SRI24 atlas), runs the pre-trained nnU-Net segmentation model, and receives:

- A verdict: **lesion detected** vs **no findings**, depending on whether the mask is empty.
- A binary 3D mask of the suspected traumatic lesions, with cluster statistics (total volume, number of connected components, size of the largest cluster).
- An interactive 2D viewer (axial, coronal, sagittal) with the mask overlaid on the T1.
- A downloadable plain-text report with the list of lesions (volume, size group, axial slices, centroid), a summary by size, notices that depend on the result, and the model metrics.
- The mask as a `.nii.gz` file ready to load in Mango, FSL, ITK-SNAP, etc.

The whole pipeline runs locally inside Docker containers; no MRI data leaves the host.

---

## Models included

| ID            | Type           | Backbone                                  | Reported metric          | Notes                                                                                       |
| ------------- | -------------- | ----------------------------------------- | ------------------------ | ------------------------------------------------------------------------------------------- |
| `nnunet`      | Segmentation   | nnU-Net v2 3D fullres (PlainConvUNet, 6 stages) | DSC 61.6%, IoU 55.4%; lesion detection: small 11.8%, medium 40.8%, large 88.6%; FP proportion 67.7% | Fine-tuned from the TBI segmentation model of Castaño Ledesma with an adaptive Dice loss (ADL v2) and adaptive sampling (ADS), learning rate 10⁻³, final checkpoint (epoch 200). Evaluated on the TCEC test set (57 images, 230 lesions). |

Size groups: small < 100 mm³, medium 100–1000 mm³, large > 1000 mm³. A lesion counts as detected when IoU ≥ 0.1; the FP proportion is the fraction of predicted lesions that match no ground-truth lesion.

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
- nibabel, NumPy, SciPy
- nnunetv2 2.5.1 + SimpleITK
- intensity-normalization 2.2.4 (KDE normalization used by the checkpoint)
- ROBEX v1.2 + ANTs 2.5.4 (`antsRegistrationSyN.sh`) with the SRI24 atlas (optional preprocessing of raw T1s, off by default)

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
- **Disk space**: 10 GB free (Docker images ~3 GB + trained model ~235 MB + ANTs ~2 GB + intermediate files)
- **CPU**: any modern x86-64 (Intel/AMD); nnU-Net inference on CPU takes a few minutes per case, and the optional preprocessing adds roughly 15–35 minutes
- **Network**: required only for the first build (pulling base images and Python/Node packages)

Optional (much faster inference):

- NVIDIA GPU with CUDA 12-compatible driver and `nvidia-container-toolkit`; uncomment the `deploy.resources` block in `docker-compose.yml`. nnU-Net detects the GPU automatically and inference becomes much faster (ROBEX and ANTs still run on CPU).

---

## Getting the trained models

The trained model weights are not included in this repository because of their size (around 235 MB) and licensing context. To request them, please send an email to the author:

**alejandro.cano@correounivalle.edu.co**

You will receive a zip with the following files, to be placed under `backend/models/`:

```
backend/models/
└── nnunet_ideas_fold_all/
    ├── checkpoint_final.pth                 (nnU-Net weights, ~235 MB)
    ├── plans.json
    ├── dataset.json
    └── dataset_fingerprint.json
```

The backend validates these files on startup and prints a clear error if any are missing.

---

## Preprocessing: ROBEX + SRI24 registration

The segmentation model was trained on T1 images that went through two steps before nnU-Net:

1. **Skull stripping with ROBEX** (removes skull, scalp, neck and eyes).
2. **Nonlinear registration to the SRI24 atlas with ANTs SyN** (`antsRegistrationSyN.sh -d 3 -f SRI24_atlas.nii -m <brain> -o <prefix>`, default rigid + affine + SyN transform). The result is a 240×240×155 volume at 1 mm, RAS orientation.

The upload screen has a single toggle, **"Preprocess the T1 (ROBEX + registration to the SRI24 atlas)"**, that runs both steps in that order:

| Input T1 | Toggle | What happens |
| -------- | ------ | ------------ |
| Already skull-stripped and registered to SRI24 (e.g. the TCEC test images `TCEC_xxxx_0000.nii.gz`) | Off (default) | The T1 goes directly to nnU-Net. |
| Raw (skull, scalp, neck, any orientation or field of view) | On | ROBEX → ANTs SyN to SRI24 → nnU-Net. |

Notes:

- With the toggle on, the mask stays in SRI24 space and the viewer shows it over the **registered** T1, not over the original upload.
- On CPU, ROBEX takes about 2–5 min and the SyN registration about 10–30 min per subject, on top of the nnU-Net inference.
- If ROBEX or the registration fails, the job stops with an error instead of sending an unprocessed T1 to the model.
- Required files:
  - ROBEX: `backend/vendor/ROBEXv12.linux64.tar.gz` (download from [NITRC](https://www.nitrc.org/projects/robex) after accepting its license).
  - ANTs: downloaded automatically during `docker compose build` (official Ubuntu 22.04 binaries, ~750 MB zip, installed in `/opt/ANTs`).
  - SRI24 atlas: `backend/app/atlas/SRI24_atlas.nii` (brain-only T1 template, 240×240×155, 1 mm). It is copied into the image together with `app/`.
- `GET /api/v1/assets` reports `preprocess.ready` and the list of missing pieces (`robex`, `ants`, `atlas`); the frontend disables the toggle if any is missing.

---

## First-time setup

1. Install [Docker Desktop](https://www.docker.com/products/docker-desktop) and start it.
   - On Windows/macOS, raise the memory limit: Docker Desktop → Settings → Resources → Memory → 6-8 GB.

2. Clone the repository and place the trained models you received via email:

   ```bash
   git clone https://github.com/Alejo101102/TBI_app.git
   cd TBI_app/tbi-app
   # copy the zip you received into backend/models/ and unzip it there
   ```

3. Check the preprocessing assets if you will analyze raw T1s: the ROBEX binary in `backend/vendor/ROBEXv12.linux64.tar.gz` and the atlas in `backend/app/atlas/SRI24_atlas.nii`. The atlas is not included in the repository (it is listed in `.gitignore`): download SRI24 separately or request it by email. ANTs is installed automatically during the build. Without them the app still works for T1s that are already skull-stripped and registered to SRI24 (see [Preprocessing](#preprocessing-robex--sri24-registration)).

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
docker logs -f tbi_backend
docker logs -f tbi_frontend
```

---

## Project structure

```
tbi-app/
├── docker-compose.yml
├── backend/
│   ├── Dockerfile
│   ├── requirements.txt
│   ├── models/                              # trained weights (received by email)
│   ├── tmp/                                 # job working directory (mounted volume)
│   └── app/
│       ├── main.py                          # FastAPI entrypoint
│       ├── config.py                        # paths (models, ROBEX, ANTs, atlas), model metrics
│       ├── api/
│       │   ├── routes.py                    # /analyze, /status, /report, /t1, /mask
│       │   └── schemas.py                   # Pydantic request/response models
│       ├── pipelines/
│       │   ├── nnunet.py                    # nnU-Net 3D fullres inference
│       │   └── nnunet_normalization.py      # KdeNormalization used by the checkpoint
│       ├── preprocessing/
│       │   ├── nifti_utils.py
│       │   ├── robex.py                     # ROBEX skull stripping
│       │   └── registration.py              # ANTs SyN registration to SRI24
│       └── atlas/
│           └── SRI24_atlas.nii              # SRI24 template (registration target)
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

- **Accepted input**: a single T1-weighted volume in NIfTI format, either already skull-stripped and registered to SRI24, or raw (with preprocessing enabled). Maximum upload size 500 MB.
- **Processing time on CPU**: a few minutes for the segmentation, plus roughly 15–35 minutes when preprocessing is enabled. The progress bar advances within each step.
- **Preprocessing (ROBEX + SRI24 registration)**: off by default. Enable it for raw T1s; leave it off for T1s that are already skull-stripped and registered to SRI24. See [Preprocessing](#preprocessing-robex--sri24-registration).
- **Viewer orientation**: anterior is at the top of the axial view and superior at the top of the coronal and sagittal views. Axial and coronal views use the radiological convention (patient's right on the left of the screen, marked with R/L labels), the same as Mango and most clinical viewers. The slice is scaled to fill the viewer.
- **Mask download**: the segmentation pipeline writes the mask to `backend/tmp/<job_id>/nnunet_out/subject.nii.gz`. The download button serves it via `/api/v1/mask/<job_id>`.
- **Job persistence**: the backend keeps a snapshot of job states in `backend/tmp/_jobs_snapshot.json`. If the container restarts during inference, the frontend will see an `error` status with a clear message instead of a generic 404.
- **Language**: the UI toggle (top-right) switches all text and the generated report between Spanish and English; the choice is stored in `localStorage`.

---

## Limitations and clinical disclaimer

This software is a **research prototype** developed for an undergraduate thesis. It must not be used for clinical decision-making. The model is a fine-tuned version of the TBI segmentation model of Castaño Ledesma, trained and evaluated on a single dataset (TCEC, T1 images skull-stripped with ROBEX and registered to SRI24), and has not been validated on independent populations, scanner manufacturers or acquisition protocols. Results must always be interpreted by a qualified neurologist or radiologist.

Key known limitations (test set: 57 images with 230 ground-truth lesions; a lesion counts as detected when IoU ≥ 0.1):

- **Small lesions are still the main challenge.** The deployed model (ADL v2 + ADS, learning rate 10⁻³) detects 14 of 119 small lesions (< 100 mm³), so most of them are still missed. Detection is much higher for large lesions (31 of 35, > 1000 mm³).
- **High false-positive rate.** About two out of three predicted lesions (67.7 %) do not match any ground-truth lesion, with an average of 2.6 false-positive components per subject. Many are small fragments, so every predicted region must be checked visually.
- **Moderate overlap.** The mean Dice is 61.6 % (IoU 55.4 %): the model localizes most medium and large lesions, but their borders do not match the reference exactly.
- **Input must match training.** The model expects T1 images skull-stripped and registered to SRI24. Raw T1s must go through the optional preprocessing (ROBEX + ANTs SyN), and its quality (failed skull stripping or misregistration) directly affects the result. With preprocessing enabled, the mask is shown in SRI24 space, not in the original space of the upload.
- **Inference settings differ slightly from the evaluation.** To keep CPU times reasonable the app runs nnU-Net without test-time mirroring, so its masks can differ slightly from those used to compute the reported metrics.

---

## Contact

For trained weights, atlas, dataset questions, or to report bugs:

**Alejandro Guerrero**
Systems Engineering, Universidad del Valle
Multimedia and Computer Vision Laboratory
alejandro.cano@correounivalle.edu.co
