# ─────────────────────────────────────────────────────────────────────────────
# TBI App — Backend Dockerfile
# Base: Ubuntu 22.04 LTS
# Pipeline: 3D nnU-Net (segmentación de zonas epileptogénicas)
#
# Preprocesamiento opcional (toggle del frontend `preprocess`, por defecto OFF):
# ROBEX (skull stripping) + registro ANTs SyN al atlas SRI24, los mismos pasos
# que tuvieron las imágenes de entrenamiento. Se activa para T1 crudas; las T1
# ya preprocesadas pasan directo a nnU-Net.
#
# CPU por defecto. Si el host tiene GPU NVIDIA y nvidia-container-toolkit
# instalado, nnUNetPredictor detecta GPU automáticamente vía
# torch.cuda.is_available().
# ─────────────────────────────────────────────────────────────────────────────
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive
ENV TZ=America/Bogota
ENV PYTHONUNBUFFERED=1

# ─── Dependencias del sistema ─────────────────────────────────────────────────
RUN apt-get update && apt-get install -y --no-install-recommends \
    # Herramientas base
    wget curl unzip ca-certificates \
    # Para NIfTI / nibabel
    zlib1g \
    # Python 3.11
    python3.11 python3.11-dev python3-pip \
    # ROBEX y antsRegistrationSyN.sh usan bc
    bc \
    # Librerías requeridas por PyTorch/nnU-Net
    libgomp1 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Python por defecto → python3.11
RUN ln -sf /usr/bin/python3.11 /usr/bin/python3 \
 && ln -sf /usr/bin/python3.11 /usr/bin/python

# ─── ROBEX (skull stripping opcional) ─────────────────────────────────────────
# Binario distribuido por NITRC detrás de una página de "agreement" — el zip
# se incluye manualmente en backend/vendor/ROBEXv12.linux64.tar.gz
# (https://www.nitrc.org/projects/robex/)
ENV ROBEX_DIR=/opt/ROBEX

COPY vendor/ROBEXv12.linux64.tar.gz /tmp/robex.tar.gz
RUN tar -xzf /tmp/robex.tar.gz -C /opt && \
    chmod +x ${ROBEX_DIR}/runROBEX.sh && \
    chmod +x ${ROBEX_DIR}/ROBEX && \
    rm /tmp/robex.tar.gz

# ─── ANTs (registro SyN al atlas SRI24) ───────────────────────────────────────
# Binarios precompilados oficiales para Ubuntu 22.04. Incluyen
# antsRegistrationSyN.sh, el mismo script usado para preparar los datos de
# entrenamiento. El atlas va en app/atlas/SRI24_atlas.nii (se copia con app/).
ARG ANTS_VERSION=2.5.4
ENV ANTS_DIR=/opt/ANTs/bin
ENV ANTSPATH=/opt/ANTs/bin/
ENV PATH="${ANTS_DIR}:${PATH}"

RUN wget -q -O /tmp/ants.zip \
      "https://github.com/ANTsX/ANTs/releases/download/v${ANTS_VERSION}/ants-${ANTS_VERSION}-ubuntu-22.04-X64-gcc.zip" && \
    unzip -q /tmp/ants.zip -d /opt/ants_tmp && \
    SYN="$(find /opt/ants_tmp -name antsRegistrationSyN.sh | head -n 1)" && \
    mv "$(dirname "$(dirname "$SYN")")" /opt/ANTs && \
    rm -rf /opt/ants_tmp && \
    chmod +x ${ANTS_DIR}/* && \
    rm /tmp/ants.zip

# ─── Python: instalar dependencias ───────────────────────────────────────────
WORKDIR /app
COPY requirements.txt .

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ─── Código de la aplicación ──────────────────────────────────────────────────
COPY app/ ./app/

# Modelos de nnU-Net: se montan como volumen en docker-compose.yml
# (checkpoint_final.pth, plans.json, dataset.json — ver app/config.py)

# ─── Directorio temporal de procesamiento ─────────────────────────────────────
RUN mkdir -p /app/tmp && chmod 777 /app/tmp

# ─── Entrypoint ───────────────────────────────────────────────────────────────
EXPOSE 8000

# --workers 1: el predictor nnU-Net tiene estado (modelo cargado en memoria)
#              y el polling JOBS dict es in-memory
# --timeout-keep-alive 300: jobs pueden tardar varios minutos
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--timeout-keep-alive", "300"]
