"""
main.py — FastAPI entrypoint
Starts the server, registers routes and verifies assets on startup.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager

from app.config import validate_assets, DEVICE
from app.api.routes import router


# ─── Lifespan: runs at startup and shutdown ──────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup ──────────────────────────────────────────────────────────────
    print("=" * 50)
    print("  VBM App — Backend iniciando")
    print(f"  Dispositivo: {DEVICE.upper()}")
    print("=" * 50)

    results = validate_assets()
    missing = [k for k, v in results.items() if not v]
    if missing:
        print(f"\n  [ADVERTENCIA] Assets faltantes al arrancar: {missing}")
        print("  El servidor arranca pero los endpoints afectados fallarán.\n")

    yield  # server runs here

    # ── Shutdown ─────────────────────────────────────────────────────────────
    print("\n  VBM App — Backend cerrando")


# ─── FastAPI application ─────────────────────────────────────────────────────
app = FastAPI(
    title="VBM App — Backend",
    description=(
        "API para análisis de morfometría basada en vóxeles (VBM) "
        "en imágenes T1 de resonancia magnética. "
        "Soporta SPM12/DARTEL, Modelo Híbrido y nnUNet."
    ),
    version="1.0.0",
    lifespan=lifespan,
)

# ─── CORS ────────────────────────────────────────────────────────────────────
# In production replace ["*"] with the real frontend domain
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routes ──────────────────────────────────────────────────────────────────
app.include_router(router, prefix="/api/v1")


# ─── Health check ────────────────────────────────────────────────────────────
@app.get("/health")
def health():
    return {
        "status": "ok",
        "device": DEVICE,
    }