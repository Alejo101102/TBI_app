# ─────────────────────────────────────────────────────────────────────────────
# VBM App — Backend Dockerfile
# Base: Ubuntu 22.04 LTS
# Pipeline: deepmriprep (PyTorch puro) + CNN MedicalNet ResNet-18
#
# CAMBIO HISTÓRICO: anteriormente se usaba SPM12 r7771 Standalone + MCR R2024b.
# Se descartó por irreproducibilidad cross-platform (~28k voxeles de diferencia
# en mwp1 entre macOS y Linux con el MISMO algoritmo SPM12). Ahora se usa
# deepmriprep, basado en redes neuronales PyTorch — bit-reproducible across OS.
#
# ROBEX se mantiene como paso opcional (toggle del frontend `use_robex`) para
# usuarios que prefieren skull-stripping explícito antes de deepmriprep
# (deepmriprep internamente ya hace brain extraction con deepbet, así que ROBEX
# es estrictamente opcional). Por defecto OFF.
#
# CPU por defecto. Si el host tiene GPU NVIDIA y nvidia-container-toolkit
# instalado, deepmriprep detecta GPU automáticamente vía torch.cuda.is_available()
# (no_gpu=not torch.cuda.is_available() en la llamada a run_preprocess).
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
    # Librerías que antspyx puede necesitar
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

# ─── Pre-cargar pesos de deepmriprep ──────────────────────────────────────────
# deepmriprep descarga sus modelos (deepbet, segmentación UNet 3D, sSYMNet) en
# el primer uso. Forzamos la descarga durante el build para que la primera
# inferencia no dependa de red y sea rápida.
RUN python -c "from deepmriprep.preprocess import Preprocess; Preprocess(no_gpu=True)" || \
    echo "WARN: pre-carga de modelos deepmriprep falló — descargarán en primer run"

# ─── Código de la aplicación ──────────────────────────────────────────────────
COPY app/ ./app/

# Modelos del CNN: se montan como volumen en docker-compose.yml
# - deepmriprep_cnn_fold3.pt (mejor fold, ver cnn_model.py para métricas)

# ─── Directorio temporal de procesamiento ─────────────────────────────────────
RUN mkdir -p /app/tmp && chmod 777 /app/tmp

# ─── Entrypoint ───────────────────────────────────────────────────────────────
EXPOSE 8000

# --workers 1: deepmriprep + CNN tienen estado (modelos cargados en memoria)
#              y el polling JOBS dict es in-memory
# --timeout-keep-alive 300: jobs pueden tardar varios minutos
CMD ["uvicorn", "app.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "1", \
     "--timeout-keep-alive", "300"]
