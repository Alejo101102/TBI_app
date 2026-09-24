# ─────────────────────────────────────────────────────────────────────────────
# VBM App — Backend Dockerfile
# Base: Ubuntu 22.04 LTS
# Pipeline: 3D nnU-Net (segmentación de zonas epileptogénicas)
#
# ROBEX se mantiene como paso opcional (toggle del frontend `use_robex`) para
# usuarios que prefieren skull-stripping explícito antes de la inferencia.
# Por defecto OFF.
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
    # ROBEX (skull stripping opcional)
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

# ─── Python: instalar dependencias ───────────────────────────────────────────
WORKDIR /app
COPY requirements.txt .

RUN pip install --upgrade pip && \
    pip install --no-cache-dir -r requirements.txt

# ─── Código de la aplicación ──────────────────────────────────────────────────
COPY app/ ./app/

# Modelos de nnU-Net: se montan como volumen en docker-compose.yml
# (checkpoint_best.pth, plans.json, dataset.json — ver app/config.py)

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
